"""Meccanica condivisa di lettura: catena di scenari annidati, materializzazione
del base (`TSOP_DEMAND`/`TSOP_OPS`) a grana di slice, applicazione degli
overlay in ordine radice -> foglia, e l'impronta di contenuto del base usata
da `promote()` per rilevare una base mossa (AC16).

Nessuna funzione qui apre una connessione propria (`con` è sempre ricevuto,
mai `ibp.db.connect()` — stesso contratto di `ibp.semantic`).
"""
from __future__ import annotations

import hashlib
from collections import defaultdict

from ..domain.scenario import Scenario
from .errors import (
    NonAdditiveMeasureError,
    UnknownMeasureError,
    UnknownScenarioError,
    UnknownVersionError,
)
from .models import CellKey, ScenarioStack

_MEASURE_TABLE = {"demand": "DMEASURE_DEMAND", "ops": "DMEASURE_OPS"}

_SCENARIO_COLUMNS = (
    "scenario_id, name, base_version_key, base_snapshot_id, parent_scenario_id, "
    "owner, state, created_at"
)


def load_scenario(con, scenario_id: str) -> Scenario:
    row = con.execute(
        f"SELECT {_SCENARIO_COLUMNS} FROM scenario WHERE scenario_id = ?", [scenario_id]
    ).fetchone()
    if row is None:
        raise UnknownScenarioError(scenario_id)
    return Scenario(*row)


def version_exists(con, version_key: int) -> str:
    """Ritorna `version_name` se `version_key` esiste in `DVERSIONS`,
    altrimenti solleva `UnknownVersionError`."""
    row = con.execute(
        "SELECT version_name FROM DVERSIONS WHERE version_key = ?", [version_key]
    ).fetchone()
    if row is None:
        raise UnknownVersionError(version_key)
    return row[0]


def scenario_chain(con, scenario_id: str) -> list[Scenario]:
    """Catena di scenari da radice a foglia (`scenario_id` incluso), seguendo
    `parent_scenario_id`. Solleva `UnknownScenarioError` se un antenato
    citato non esiste, e `ScenarioError` se la catena è ciclica (dato
    corrotto: non deve mai risultare in un loop infinito silenzioso)."""
    chain: list[Scenario] = []
    seen: set[str] = set()
    current_id: str | None = scenario_id
    while current_id is not None:
        if current_id in seen:
            from .errors import ScenarioError

            raise ScenarioError(
                f"catena di scenari ciclica rilevata a partire da {scenario_id!r} "
                f"(ripetizione di {current_id!r})"
            )
        seen.add(current_id)
        scenario = load_scenario(con, current_id)
        chain.append(scenario)
        current_id = scenario.parent_scenario_id
    chain.reverse()
    return chain


def stack_of(con, ref: int | str) -> ScenarioStack:
    """La chiave di isolamento (AC15) per `ref`: `base_version_key` più la
    catena ordinata radice -> foglia degli `scenario_id` coinvolti (`()` per
    una versione pura)."""
    if isinstance(ref, str):
        chain = scenario_chain(con, ref)
        return ScenarioStack(
            base_version_key=chain[-1].base_version_key,
            chain=tuple(s.scenario_id for s in chain),
        )
    if isinstance(ref, int):
        version_exists(con, ref)
        return ScenarioStack(base_version_key=ref, chain=())
    raise TypeError(f"ref deve essere int (version_key) o str (scenario_id), non {type(ref)!r}")


def additive_measure_keys(con, side: str) -> frozenset[int]:
    """`measure_key` con `agg_method='sum'` nel catalogo di `side`
    (`DMEASURE_DEMAND`/`DMEASURE_OPS`) — le uniche misure che questo modulo
    sa combinare sulle coordinate che `overlay` non traccia (AC12: min/max/
    ratio/avg/count si ricalcolano sul gruppo, non si sommano)."""
    table = _MEASURE_TABLE[side]
    rows = con.execute(f"SELECT measure_key FROM {table} WHERE agg_method = 'sum'").fetchall()
    return frozenset(r[0] for r in rows)


def _measure_agg_method(con, side: str, measure_key: int) -> str | None:
    table = _MEASURE_TABLE[side]
    row = con.execute(
        f"SELECT agg_method FROM {table} WHERE measure_key = ?", [measure_key]
    ).fetchone()
    return row[0] if row is not None else None


def require_additive_measure(con, cell: CellKey) -> None:
    """Guardia esplicita (AC12): solleva `UnknownMeasureError` se
    `cell.measure_key` non esiste nel catalogo del lato di `cell`,
    `NonAdditiveMeasureError` se il suo `agg_method` non è `'sum'`. Chiamata
    da `resolve_cell()` (quindi anche da ogni scrittura, che vi passa
    attraverso) prima di qualunque somma — mai dopo aver già restituito o
    scritto un numero."""
    agg_method = _measure_agg_method(con, cell.side, cell.measure_key)
    if agg_method is None:
        raise UnknownMeasureError(cell.side, cell.measure_key)
    if agg_method != "sum":
        raise NonAdditiveMeasureError(cell.measure_key, agg_method)


def materialize_version(con, version_key: int) -> dict[tuple, float]:
    """Righe base per `version_key`, aggregate (somma) alla grana di slice di
    `overlay` (`product_key|None, plant_key|None, date_key, measure_key`):
    `TSOP_DEMAND` non porta `division_key`/`region` nella chiave risultante,
    `TSOP_OPS` non porta `manufact_key`/`product_key`/`division_key`/`region`
    — sono le coordinate che `overlay` stesso non traccia (vedi `CellKey`:
    una cella lato ops è identificata solo da `plant_key`, non anche da
    `product_key`, esattamente come una riga di `overlay` con `plant_key`
    valorizzato e `product_key` NULL). Una `version_key` compare
    tipicamente in una sola delle due tabelle (side DEMAND vs SUPPLY,
    `db/seed/facts.py`); interrogare entrambe evita di dover conoscere
    `DVERSIONS.side` qui.

    Nota su determinismo (bug reale trovato dal tester): la somma **non**
    viene fatta con `SUM(...) GROUP BY` lato SQL. Su una base con 100k+
    righe, `SUM` parallelo di DuckDB non garantisce lo stesso ordine di
    riduzione fra due esecuzioni dello stesso piano — due chiamate su dato
    identico possono differire nell'ultimo bit (~1e-13), che `compare()`
    (due chiamate indipendenti, una per lato) leggerebbe come migliaia di
    celle "cambiate" che nessuno ha mai toccato. Qui si scarica un
    `ORDER BY` sulla chiave primaria (ordine totale, dato `version_key`
    fisso) e si somma in Python in quell'ordine fisso: la stessa sequenza
    di addizioni float, nello stesso ordine, dà sempre lo stesso bit
    pattern — determinismo alla fonte, non un epsilon che nasconde il
    rumore a valle.

    Solo le misure `agg_method='sum'` entrano nel risultato (AC12):
    `CAPACITY_UTIL` (ratio), `SLOTS_AVAILABLE` (max) e le altre misure non
    additive non si combinano sommando righe che `overlay` non distingue
    (division/region/manufact_key) — sommarle produrrebbe un numero
    plausibile ma privo di senso (una somma di percentuali di utilizzo,
    invece della loro ricombinazione corretta, che `ibp.scenario` non
    conosce). Sono semplicemente escluse da questa aggregazione: non è un
    errore silenzioso, perché nessun valore sbagliato viene calcolato — una
    richiesta esplicita su una cella non additiva passa invece da
    `resolve_cell()`, che la rifiuta con `NonAdditiveMeasureError`."""
    additive_demand = additive_measure_keys(con, "demand")
    additive_ops = additive_measure_keys(con, "ops")
    out: dict[tuple, float] = defaultdict(float)
    for product_key, date_key, measure_key, value in con.execute(
        "SELECT product_key, date_key, measure_key, value FROM TSOP_DEMAND "
        "WHERE version_key = ? ORDER BY product_key, date_key, measure_key, division_key",
        [version_key],
    ).fetchall():
        if measure_key not in additive_demand:
            continue
        out[(product_key, None, date_key, measure_key)] += float(value)
    for plant_key, date_key, measure_key, value in con.execute(
        "SELECT plant_key, date_key, measure_key, value FROM TSOP_OPS "
        "WHERE version_key = ? "
        "ORDER BY plant_key, date_key, measure_key, manufact_key, product_key, division_key",
        [version_key],
    ).fetchall():
        if measure_key not in additive_ops:
            continue
        out[(None, plant_key, date_key, measure_key)] += float(value)
    return dict(out)


def base_cell_value(con, version_key: int, cell: CellKey) -> float | None:
    """Valore base di una singola `CellKey` (somma sulle coordinate che
    `overlay` non traccia — vedi `materialize_version`): `None` se
    `version_key` non ha alcuna riga per quella slice (mai scritta, non
    `0.0` — la distinzione conta per `resolve_cell()`). Somma in Python su
    righe grezze ordinate deterministicamente, stesso motivo di
    `materialize_version`: niente `SUM` lato SQL su un possibile gruppo di
    più righe (più division per la stessa cella).

    Non verifica da sola l'`agg_method` di `cell.measure_key` (AC12): è
    compito del chiamante (`resolve_cell()`) farlo **prima** di arrivare
    qui, così la guardia vale per ogni fonte (overlay compreso), non solo
    per la lettura dal base."""
    if cell.product_key is not None:
        rows = con.execute(
            "SELECT value FROM TSOP_DEMAND "
            "WHERE version_key = ? AND product_key = ? AND date_key = ? AND measure_key = ? "
            "ORDER BY division_key",
            [version_key, cell.product_key, cell.date_key, cell.measure_key],
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT value FROM TSOP_OPS "
            "WHERE version_key = ? AND plant_key = ? AND date_key = ? AND measure_key = ? "
            "ORDER BY manufact_key, product_key, division_key",
            [version_key, cell.plant_key, cell.date_key, cell.measure_key],
        ).fetchall()
    if not rows:
        return None
    total = 0.0
    for (value,) in rows:
        total += float(value)
    return total


def overlay_rows(con, scenario_id: str, version_key: int) -> list[tuple]:
    """Righe grezze di `overlay` per uno scenario, **filtrate per
    `version_key`**: `(product_key, plant_key, date_key, measure_key,
    value, is_deleted)`.

    Il filtro su `version_key` è la difesa in profondità di AC15 (bug reale
    trovato dal critico): senza di esso, uno scenario che per qualunque
    motivo portasse righe di overlay scritte sotto un `version_key` diverso
    dalla base che si sta effettivamente risolvendo le vedrebbe comunque
    applicate — un edit registrato sotto la base v353 che riappare quando
    si legge una catena la cui base è v370. `overlay.UNIQUE` include già
    `version_key` nella sua chiave logica: ignorarlo qui era l'unico punto
    che non onorava quella chiave. La scrittura (`edits.py`) impedisce ora
    a monte che un simile disallineamento nasca, ma questo filtro resta
    corretto indipendentemente da quella garanzia."""
    return con.execute(
        "SELECT product_key, plant_key, date_key, measure_key, value, is_deleted "
        "FROM overlay WHERE scenario_id = ? AND version_key = ?",
        [scenario_id, version_key],
    ).fetchall()


def apply_overlay_layer(
    slices: dict[tuple, float], con, scenario_id: str, version_key: int
) -> dict[tuple, float]:
    """Applica l'overlay di un solo scenario (scoperto a `version_key`,
    vedi `overlay_rows`) sopra `slices` (in place su una copia): un valore
    non cancellato **sostituisce** (non somma) il valore della slice; un
    tombstone (`is_deleted=True`) la rimuove — non ricompare più dal base
    (AC14), anche se un layer precedente (più vicino alla radice) l'aveva
    valorizzata."""
    out = dict(slices)
    for product_key, plant_key, date_key, measure_key, value, is_deleted in overlay_rows(
        con, scenario_id, version_key
    ):
        key = (product_key, plant_key, date_key, measure_key)
        if is_deleted:
            out.pop(key, None)
        else:
            out[key] = float(value)
    return out


def overlay_touched_slices(con, scenario_id: str) -> dict[tuple, tuple[float | None, bool]]:
    """Le sole slice che la catena di scenari di `scenario_id` ha
    effettivamente scritto (`set`/`increment`) o cancellato (tombstone),
    radice -> foglia (la foglia vince), con il loro esito finale:
    `{slice_key: (value | None, is_deleted)}`. A differenza di
    `materialize_ref()` (che parte dal base e quindi non distingue "slice
    mai toccata" da "slice toccata ma con lo stesso valore del base"),
    questa funzione risponde esattamente alla domanda che `promote()` deve
    porsi per decidere se copiare una riga invariata o passarla dal riparto
    (bug reale trovato dal critico, AC13/AC14: un `promote()` a zero edit
    **deve** produrre righe bit-identiche al base, non `target * share`
    ricalcolato — `sum(v) * (v / sum(v))` non ritorna `v` esattamente in
    virgola mobile anche quando la slice non è mai stata sfiorata)."""
    chain = scenario_chain(con, scenario_id)
    base_version_key = chain[-1].base_version_key
    touched: dict[tuple, tuple[float | None, bool]] = {}
    for scenario in chain:
        for product_key, plant_key, date_key, measure_key, value, is_deleted in overlay_rows(
            con, scenario.scenario_id, base_version_key
        ):
            key = (product_key, plant_key, date_key, measure_key)
            touched[key] = (None if is_deleted else float(value), bool(is_deleted))
    return touched


def materialize_ref(con, ref: int | str) -> dict[tuple, float]:
    """Slice risolte per `ref` (versione pura o scenario, indifferentemente):
    base + overlay dell'intera catena, radice -> foglia (AC15: uno scenario
    annidato eredita gli edit degli antenati, salvo sovrascriverli/
    cancellarli lui stesso). Ogni layer della catena è risolto rispetto
    allo **stesso** `base_version_key` (`chain[-1]`, la foglia): `branch()`
    garantisce che uno scenario annidato condivida sempre la base del
    proprio antenato (`MismatchedBaseVersionError` altrimenti), quindi
    tutti gli elementi della catena hanno di fatto lo stesso
    `base_version_key`."""
    if isinstance(ref, int):
        version_exists(con, ref)
        return materialize_version(con, ref)
    if isinstance(ref, str):
        chain = scenario_chain(con, ref)
        base_version_key = chain[-1].base_version_key
        slices = materialize_version(con, base_version_key)
        for scenario in chain:
            slices = apply_overlay_layer(slices, con, scenario.scenario_id, base_version_key)
        return slices
    raise TypeError(f"ref deve essere int (version_key) o str (scenario_id), non {type(ref)!r}")


def base_content_digest(con, version_key: int) -> str:
    """Impronta di contenuto di `TSOP_DEMAND`/`TSOP_OPS` per `version_key`,
    deterministica (`hashlib.sha256`, non `hash()` — stesso motivo del RNG
    di seed in `db/seed/common.py`: l'hash builtin delle stringhe è salato
    per processo). Usata da `branch()` per registrare `base_snapshot_id` e
    da `promote()` per rilevare una base mossa dal branch time (AC16): due
    chiamate sullo stesso contenuto producono sempre la stessa stringa,
    indipendentemente da quando o da quale processo vengono eseguite."""
    digest = hashlib.sha256()
    demand_rows = con.execute(
        "SELECT product_key, division_key, date_key, measure_key, value FROM TSOP_DEMAND "
        "WHERE version_key = ? ORDER BY product_key, division_key, date_key, measure_key",
        [version_key],
    ).fetchall()
    for row in demand_rows:
        digest.update(repr(row).encode("utf-8"))
    digest.update(b"|OPS|")
    ops_rows = con.execute(
        "SELECT manufact_key, plant_key, product_key, division_key, date_key, measure_key, value "
        "FROM TSOP_OPS WHERE version_key = ? "
        "ORDER BY manufact_key, plant_key, product_key, division_key, date_key, measure_key",
        [version_key],
    ).fetchall()
    for row in ops_rows:
        digest.update(repr(row).encode("utf-8"))
    return digest.hexdigest()


def _find_overlay_row(con, scenario_id: str, cell: CellKey) -> tuple[float | None, bool] | None:
    """Riga di `overlay` per una `CellKey` esatta di uno scenario (non
    dell'intera catena): `None` se lo scenario non ha mai scritto quella
    cella. `product_key`/`plant_key` sono confrontati con `IS NOT DISTINCT
    FROM` (NULL-safe): uno dei due è sempre NULL per costruzione (`CellKey`
    è XOR), e il confronto standard `=` non farebbe mai match su NULL."""
    row = con.execute(
        "SELECT value, is_deleted FROM overlay WHERE scenario_id = ? AND version_key = ? "
        "AND date_key = ? AND measure_key = ? "
        "AND product_key IS NOT DISTINCT FROM ? AND plant_key IS NOT DISTINCT FROM ?",
        [
            scenario_id, cell.version_key, cell.date_key, cell.measure_key,
            cell.product_key, cell.plant_key,
        ],
    ).fetchone()
    if row is None:
        return None
    value, is_deleted = row
    return (float(value) if value is not None else None, bool(is_deleted))


def resolve_cell(con, ref: int | str, cell: CellKey) -> "ResolvedCell":
    """Risoluzione precisa di una singola cella (a differenza di
    `materialize_ref`, che aggrega l'intero base per il confronto):
    percorre la catena di scenari da **foglia a radice**, si ferma alla
    prima riga di `overlay` che ha scritto quella cella esatta (il layer
    più vicino alla foglia vince — coerente con `apply_overlay_layer`), e
    ne preserva il tombstone (`is_deleted=True`, `value=None`) invece di
    farlo sparire in un aggregato. Se nessun layer di scenario ha scritto
    la cella, risolve dal base di `chain[-1]` (o direttamente da `ref` se è
    una versione pura). Ritorna `source='none'` se la cella non esiste in
    nessuna delle due forme (mai scritta, nessuna riga base)."""
    from .models import ResolvedCell

    require_additive_measure(con, cell)

    if isinstance(ref, int):
        version_exists(con, ref)
        value = base_cell_value(con, ref, cell)
        if value is None:
            return ResolvedCell(cell=cell, value=None, is_deleted=False, source="none")
        return ResolvedCell(cell=cell, value=value, is_deleted=False, source="base")
    if isinstance(ref, str):
        chain = scenario_chain(con, ref)
        for scenario in reversed(chain):
            match = _find_overlay_row(con, scenario.scenario_id, cell)
            if match is not None:
                value, is_deleted = match
                return ResolvedCell(
                    cell=cell, value=None if is_deleted else value,
                    is_deleted=is_deleted, source="overlay",
                )
        base_version_key = chain[-1].base_version_key
        value = base_cell_value(con, base_version_key, cell)
        if value is None:
            return ResolvedCell(cell=cell, value=None, is_deleted=False, source="none")
        return ResolvedCell(cell=cell, value=value, is_deleted=False, source="base")
    raise TypeError(f"ref deve essere int (version_key) o str (scenario_id), non {type(ref)!r}")
