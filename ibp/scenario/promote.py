"""`promote(scenario)`: materializza una **nuova** istanza `DVERSIONS`
(nome `SOP_YYYY_MM_{DEMAND|SUPPLY}_{P|R|A|C}`, AC13) dallo stato risolto
dello scenario (base + intera catena di overlay, AC15), porta lo scenario a
`Promoted` (la transizione è quella di `ibp.domain.scenario`, non una
seconda macchina a stati), e rifiuta:

- di scrivere su un'istanza `DVERSIONS` già esistente con lo stesso nome
  (il chiamante sceglie `cycle_year`/`cycle_month`/`status` — `side` invece
  è vincolato a `DVERSIONS.side` della base, vedi `SideMismatchError`; se
  le coordinate risultanti sono occupate, `DuplicateVersionError`, mai
  sovrascrittura);
- una base mossa dal branch time (AC16, `PromotionConflictError`), rilevata
  ricalcolando l'impronta di contenuto e confrontandola con
  `base_snapshot_id` registrato da `branch()` — solo per gli scenari il cui
  `base_snapshot_id` è nel formato che `branch()` produce; vedi
  `_base_moved()` per gli scenari (tipicamente seed, pre-T4) in un formato
  diverso, per i quali il confronto non è verificabile.

Limite di grana dichiarato (non nascosto): `overlay` non porta
`division_key`/`region`/`manufact_key` (vedi `overlay.py`). Quando una
slice overlay-ata (`product_key`/`plant_key` + `date_key` + `measure_key`)
copre **più righe piene** in base (più division per lo stesso
product/date/measure, il caso comune sul dato reale), il nuovo valore
assoluto viene **proratato sul mix osservato in base** — stessa logica
già in uso altrove nello schema per `item_link.quota_source =
'observed_history'` (`db/schema.sql`): non è una scelta arbitraria di
questo modulo, è la stessa risposta che il resto del sistema dà quando una
quota va ricostruita senza un'anagrafica esplicita. Se tutte le righe
originali della slice sono `0.0` (nessun mix da cui proratare), la
distribuzione è equa fra le righe. Una slice con overlay ma **senza
alcuna riga base corrispondente** resta invece non materializzabile (non
c'è `division_key`/`region` da cui ereditare): `UnmaterializableCellError`,
mai una riga inventata.
"""
from __future__ import annotations

import re
from collections import defaultdict

from .errors import (
    DuplicateVersionError,
    PromotionConflictError,
    SideMismatchError,
    UnmaterializableCellError,
)
from .models import PromotionResult
from .overlay import additive_measure_keys, base_content_digest, load_scenario, overlay_touched_slices

_SIDES = frozenset({"DEMAND", "SUPPLY"})
_STATUSES = frozenset({"P", "R", "A", "C"})

# Formato canonico di `base_snapshot_id` prodotto da `branch()`:
# `SNAP_{version_key}_{sha256 esadecimale}`. Un `base_snapshot_id` che non
# combacia (es. il formato del seed pre-T4, `SNAP_{version_name}_{iso_ts}`,
# db/seed/scenario.py) non è un'impronta di contenuto: non c'è un digest da
# confrontare, quindi non è verificabile — vedi `_base_moved()`.
_SNAPSHOT_RE = re.compile(r"^SNAP_(-?\d+)_([0-9a-f]{64})$")


def _version_name(cycle_year: int, cycle_month: int, side: str, status: str) -> str:
    if side not in _SIDES:
        raise ValueError(f"side sconosciuto: {side!r} (atteso uno tra {sorted(_SIDES)})")
    if status not in _STATUSES:
        raise ValueError(f"status sconosciuto: {status!r} (atteso uno tra {sorted(_STATUSES)})")
    return f"SOP_{cycle_year:04d}_{cycle_month:02d}_{side}_{status}"


def _bulk_insert(con, table: str, columns: tuple[str, ...], rows: list[list], chunk_size: int = 2000) -> None:
    """Inserisce `rows` in `table` a blocchi con un solo statement
    `INSERT ... VALUES (?, ...), (?, ...), ...` per blocco: una versione
    promossa può portare decine di migliaia di righe (grana piena di
    `TSOP_DEMAND`/`TSOP_OPS`), e uno statement per riga (o anche
    `executemany`, che internamente resta un giro per riga) è impraticabile
    a quella scala. Il chunking evita anche un singolo statement enorme per
    le versioni più dense."""
    if not rows:
        return
    col_list = ", ".join(columns)
    row_placeholder = f"({', '.join('?' for _ in columns)})"
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start:start + chunk_size]
        values_sql = ", ".join(row_placeholder for _ in chunk)
        flat_params = [v for row in chunk for v in row]
        con.execute(f"INSERT INTO {table} ({col_list}) VALUES {values_sql}", flat_params)


def _version_name_exists(con, version_name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM DVERSIONS WHERE version_name = ?", [version_name]
    ).fetchone()
    return row is not None


def _base_demand_rows(con, version_key: int) -> list[tuple]:
    """`ORDER BY` esplicito (ordine totale, dato `version_key` fisso):
    stessa ragione di determinismo di `overlay.materialize_version` — le
    somme di riparto (`_shares`) fatte in Python su queste righe devono
    dare lo stesso risultato a ogni chiamata, non dipendere dall'ordine di
    scan che DuckDB sceglie internamente."""
    return con.execute(
        "SELECT product_key, division_key, region, date_key, measure_key, value "
        "FROM TSOP_DEMAND WHERE version_key = ? "
        "ORDER BY product_key, date_key, measure_key, division_key",
        [version_key],
    ).fetchall()


def _base_ops_rows(con, version_key: int) -> list[tuple]:
    return con.execute(
        "SELECT manufact_key, plant_key, product_key, division_key, region, date_key, "
        "measure_key, value FROM TSOP_OPS WHERE version_key = ? "
        "ORDER BY plant_key, date_key, measure_key, manufact_key, product_key, division_key",
        [version_key],
    ).fetchall()


def _shares(values: list[float]) -> list[float]:
    """Quote di riparto di `target` sulle righe originali di una slice: il
    mix osservato (`value / sum(values)`), o una distribuzione equa se non
    c'è un mix utilizzabile da cui proratare — vedi docstring di modulo.

    La guardia è su `sum(abs(v) for v in values)` (la **grandezza** delle
    righe), non su `sum(values)` (la loro somma con segno). Bug reale
    trovato dal critico: il seed non ha fatti negativi, quindi `sum(values)`
    e la grandezza coincidevano e il caso non si vedeva. Ma se due righe si
    cancellano quasi esattamente (es. `[1e6, -999999.9999]`, somma
    `≈0.0001`), `sum(values)` non è "vicino a zero" in valore assoluto
    (l'`abs_tol` che aveva senso per un target dell'ordine delle centinaia
    è minuscolo rispetto a `1e6`) e la vecchia guardia non scattava: dividere
    per quella somma quasi nulla produceva quote dell'ordine di `1e9`,
    "esplose" rispetto sia al target sia alle righe originali. Confrontare
    la somma con segno contro la grandezza totale (`abs(total) < eps *
    magnitude`) rileva la cancellazione a prescindere dalla scala assoluta
    dei valori, e la riduce allo stesso, sicuro riparto equo."""
    total = sum(values)
    magnitude = sum(abs(v) for v in values)
    if magnitude == 0.0 or abs(total) < 1e-9 * magnitude:
        return [1.0 / len(values)] * len(values)
    return [v / total for v in values]


def _materialize_demand(
    touched: dict, con, base_version_key: int, additive_measures: frozenset[int]
) -> list[tuple]:
    """Righe `TSOP_DEMAND` per la nuova versione.

    Una slice è copiata **invariata, riga per riga** dal base (bit-identica,
    non ricalcolata) a meno che non sia sia additiva (`agg_method='sum'`)
    sia effettivamente presente in `touched` (`overlay.overlay_touched_slices`
    — l'esito, per slice, di ciò che la catena dello scenario ha davvero
    scritto o cancellato). Bug reale trovato dal critico: usare la
    "presenza in `materialize_ref()`" come segnale di "slice toccata" non
    distingue una slice mai sfiorata da una slice il cui overlay-risolto
    coincide col base — e ricalcolare `sum(v) * (v / sum(v))` anche per la
    prima produce un valore che differisce dall'originale nell'ultimo bit
    (`21.939` -> `21.939000000000004`), cioè un `promote()` a zero edit che
    non è più bit-identico al base, con `compare()` che lo rilegge come
    migliaia di celle "cambiate" da nessuno.

    Una slice la cui misura **non** è additiva è sempre passata invariata:
    scriverci un what-if è già rifiutato a monte da `edits._apply_edit`
    (via `overlay.require_additive_measure`), quindi `touched` non può mai
    contenerla — non è un'assunzione ottimistica, è una garanzia dell'unico
    percorso di scrittura."""
    by_slice: dict[tuple, list[tuple]] = defaultdict(list)
    for product_key, division_key, region, date_key, measure_key, value in _base_demand_rows(
        con, base_version_key
    ):
        by_slice[(product_key, None, date_key, measure_key)].append(
            (division_key, region, float(value))
        )

    out: list[tuple] = []
    for slice_key, rows in by_slice.items():
        product_key, _, date_key, measure_key = slice_key
        if measure_key not in additive_measures or slice_key not in touched:
            for division_key, region, value in rows:
                out.append((product_key, division_key, region, date_key, measure_key, value))
            continue
        target, is_deleted = touched[slice_key]
        if is_deleted:
            continue  # tombstone in overlay: la riga non entra nella nuova versione (AC14)
        shares = _shares([v for _, _, v in rows])
        for (division_key, region, _), share in zip(rows, shares):
            out.append((product_key, division_key, region, date_key, measure_key, target * share))
    return out


def _materialize_ops(
    touched: dict, con, base_version_key: int, additive_measures: frozenset[int]
) -> list[tuple]:
    """Vedi `_materialize_demand`: stessa regola (passthrough bit-identico
    per ogni slice non toccata o non additiva, riparto solo per quelle
    davvero sovrascritte) sul lato `TSOP_OPS`."""
    by_slice: dict[tuple, list[tuple]] = defaultdict(list)
    for manufact_key, plant_key, product_key, division_key, region, date_key, measure_key, value in _base_ops_rows(
        con, base_version_key
    ):
        by_slice[(None, plant_key, date_key, measure_key)].append(
            (manufact_key, product_key, division_key, region, float(value))
        )

    out: list[tuple] = []
    for slice_key, rows in by_slice.items():
        _, plant_key, date_key, measure_key = slice_key
        if measure_key not in additive_measures or slice_key not in touched:
            for manufact_key, product_key, division_key, region, value in rows:
                out.append(
                    (manufact_key, plant_key, product_key, division_key, region, date_key, measure_key, value)
                )
            continue
        target, is_deleted = touched[slice_key]
        if is_deleted:
            continue
        shares = _shares([v for *_, v in rows])
        for (manufact_key, product_key, division_key, region, _), share in zip(rows, shares):
            out.append(
                (manufact_key, plant_key, product_key, division_key, region, date_key, measure_key, target * share)
            )
    return out


def _snapshot_check(con, scenario) -> tuple[bool, bool]:
    """AC16, tollerante al formato (bug reale trovato dal critico): il seed
    (`db/seed/scenario.py`, di competenza T1, non modificabile qui) scrive
    `base_snapshot_id` come `SNAP_{version_name}_{iso_ts}` — un'etichetta
    col nome della versione e l'orario del branch, non un'impronta di
    contenuto. Non è lo stesso formato prodotto da `branch()`
    (`SNAP_{version_key}_{sha256}`, vedi `_SNAPSHOT_RE`), e non c'è modo di
    ricavarne un digest: non è un valore "diverso" da quello attuale, è un
    valore **non verificabile**. Trattarlo come conflitto bloccherebbe per
    sempre l'unico scenario `Evaluated` che il seed spedisce (quello che la
    demo di T12 userà) su una base che nessuno ha mai toccato — un falso
    positivo, non una protezione.

    Ritorna `(verified, moved)`: `verified` è `True` solo se
    `base_snapshot_id` è nel formato prodotto da `branch()` (quindi il
    confronto è stato davvero eseguito); `moved` ha senso solo quando
    `verified` è `True` — con formato non riconosciuto la promozione deve
    poter procedere (`moved=False`), ma **senza spacciare quel passaggio
    per una verifica riuscita**: è compito del chiamante (`promote()`)
    riportare `verified` in `PromotionResult.base_verified`, non
    inghiottirlo qui — un `bool` solo (il vecchio `_base_moved`) non
    distingue "confermato immobile" da "non verificabile", ed è esattamente
    il buco che il critico ha trovato: un `PromotionResult` strutturalmente
    identico nei due casi."""
    match = _SNAPSHOT_RE.match(scenario.base_snapshot_id)
    if match is None:
        return False, False
    recorded_version_key, recorded_digest = match.group(1), match.group(2)
    if int(recorded_version_key) != scenario.base_version_key:
        return True, True
    current_digest = base_content_digest(con, scenario.base_version_key)
    return True, current_digest != recorded_digest


def promote(
    con, scenario_id: str, *, cycle_year: int, cycle_month: int, side: str, status: str, user: str,
) -> PromotionResult:
    """Promuove `scenario_id` a una nuova istanza `DVERSIONS` per le
    coordinate indicate (`cycle_year`/`cycle_month`/`status` — la scelta di
    *quale* slot del calendario di piano diventa ufficiale è del chiamante,
    non di questo modulo; `side` invece **deve** combaciare con
    `DVERSIONS.side` della base dello scenario, vedi sotto). Solleva:

    - `UnknownScenarioError` se `scenario_id` non esiste;
    - `InvalidTransitionError`/`UnknownStateError` (`ibp.domain.errors`) se
      lo scenario non è `Evaluated` (unica transizione che ammette
      `Promoted`, vedi `SCENARIO_TRANSITIONS`);
    - `SideMismatchError` se `side` non combacia con `DVERSIONS.side` della
      base (bug reale trovato dal critico: promuovere un branch DEMAND con
      `side="SUPPLY"` produceva un'istanza `SOP_..._SUPPLY_*` piena di
      righe `TSOP_DEMAND` e nessuna `TSOP_OPS` — un nome che mente sul dato
      che contiene, esattamente ciò che la convenzione di naming non può
      permettersi);
    - `DuplicateVersionError` se il nome risultante esiste già in
      `DVERSIONS`;
    - `PromotionConflictError` (AC16) se la base si è mossa dal branch time
      (solo per scenari il cui `base_snapshot_id` è nel formato prodotto da
      `branch()` — vedi `_snapshot_check()`);
    - `UnmaterializableCellError` se una cella di overlay non è
      materializzabile senza ambiguità (vedi docstring di modulo).

    Il `PromotionResult` restituito porta `base_verified`: `False` quando
    `base_snapshot_id` non era nel formato verificabile e la promozione è
    passata senza che AC16 fosse davvero controllato — il chiamante non
    deve dover distinguere i due casi ri-analizzando `base_snapshot_id` da
    solo.
    """
    scenario = load_scenario(con, scenario_id)
    version_name = _version_name(cycle_year, cycle_month, side, status)

    base_side_row = con.execute(
        "SELECT side FROM DVERSIONS WHERE version_key = ?", [scenario.base_version_key]
    ).fetchone()
    base_side = base_side_row[0] if base_side_row is not None else None
    if base_side is not None and side != base_side:
        raise SideMismatchError(scenario.base_version_key, base_side, side)

    if _version_name_exists(con, version_name):
        raise DuplicateVersionError(version_name)

    # Valida la transizione di stato PRIMA di materializzare: fallire presto
    # su uno scenario non-Evaluated senza toccare il DB.
    promoted_scenario = scenario.transition_to("Promoted")

    # AC16: la base si è mossa dal branch time? (tollerante al formato, vedi _snapshot_check)
    base_verified, base_moved = _snapshot_check(con, scenario)
    if base_moved:
        current_digest = base_content_digest(con, scenario.base_version_key)
        expected_snapshot = f"SNAP_{scenario.base_version_key}_{current_digest}"
        raise PromotionConflictError(scenario.scenario_id, scenario.base_snapshot_id, expected_snapshot)

    additive_demand = additive_measure_keys(con, "demand")
    additive_ops = additive_measure_keys(con, "ops")
    touched = overlay_touched_slices(con, scenario_id)
    demand_rows = _materialize_demand(touched, con, scenario.base_version_key, additive_demand)
    ops_rows = _materialize_ops(touched, con, scenario.base_version_key, additive_ops)

    # Celle toccate (non cancellate) senza alcuna riga base corrispondente:
    # non materializzabili, `overlay` non porta division_key/region/
    # manufact_key da cui ereditarle (vedi docstring di modulo).
    covered = {(pk, None, dk, mk) for pk, _, _, dk, mk, _ in demand_rows}
    covered |= {(None, plk, dk, mk) for _, plk, _, _, _, dk, mk, _ in ops_rows}
    extra = sorted(
        (key for key, (_, is_deleted) in touched.items() if not is_deleted and key not in covered),
        key=repr,
    )
    if extra:
        raise UnmaterializableCellError(extra[0])

    con.execute("BEGIN TRANSACTION")
    try:
        if _version_name_exists(con, version_name):
            raise DuplicateVersionError(version_name)

        new_version_key = int(
            con.execute("SELECT COALESCE(MAX(version_key), 0) + 1 FROM DVERSIONS").fetchone()[0]
        )
        con.execute(
            "INSERT INTO DVERSIONS (version_key, version_name, cycle_year, cycle_month, side, "
            "status, is_budget, is_frozen, first_planning_year, first_planning_month, "
            "valid_budget_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                new_version_key, version_name, cycle_year, cycle_month, side, status,
                False, False, cycle_year, cycle_month, f"SOP_BP_{cycle_year}",
            ],
        )
        _bulk_insert(
            con, "TSOP_DEMAND",
            ("version_key", "product_key", "division_key", "region", "date_key", "measure_key", "value"),
            [
                [new_version_key, product_key, division_key, region, date_key, measure_key, value]
                for product_key, division_key, region, date_key, measure_key, value in demand_rows
            ],
        )
        _bulk_insert(
            con, "TSOP_OPS",
            (
                "version_key", "manufact_key", "plant_key", "product_key", "division_key", "region",
                "date_key", "measure_key", "value",
            ),
            [
                [
                    new_version_key, manufact_key, plant_key, product_key, division_key, region,
                    date_key, measure_key, value,
                ]
                for manufact_key, plant_key, product_key, division_key, region, date_key, measure_key, value in ops_rows
            ],
        )
        con.execute(
            "UPDATE scenario SET state = ? WHERE scenario_id = ?",
            [promoted_scenario.state, promoted_scenario.scenario_id],
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    return PromotionResult(
        version_key=new_version_key, version_name=version_name, scenario=promoted_scenario,
        base_verified=base_verified,
    )
