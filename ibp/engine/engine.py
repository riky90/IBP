"""Motore di ricalcolo (T3, A5): esegue il DAG dichiarato da
`ibp/semantic/measures.py` (`requested_production -> derived_manufacturing_demand
-> slots_requested -> gap_req_conf -> value_gap`, con `confirmed_production`
secondo nodo sorgente che alimenta direttamente `gap_req_conf`) con semantica
di *concurrent planning* stile Kinaxis — ogni input ripropaga subito nel
sottografo a valle, senza passate batch sequenziali (A5, done_when #2).

Cosa NON fa (per esplicita correzione di scope rispetto al `plan.md` stale):
nessuna allocazione multi-plant (`AllocationStrategy`, T7), nessuna
`financialize(plan, rate_card)` completa con margine (T8), nessuna
valutazione di `exception_rule` (T8). `value_gap` qui è la sola
finanziarizzazione che il DAG dichiarato richiede: gap in unità * tariffa da
`rate_card`, un'unica moltiplicazione — non la funzione più ricca che T7/T8
costruiranno sopra il piano allocato.

Granularità e scelte di dominio (nessuna scoperta a sorpresa più sotto):

- **`confirmed_production`** è il secondo nodo sorgente del DAG dichiarato
  (`ibp/semantic/measures.py`, `MEASURE_DAG["confirmed_production"]`,
  `depends_on=()`): legge da TSOP_OPS (`SLOTS_CURRENT_MONTH +
  SLOTS_PREVIOUS_MONTH`, per `(manufact_key, plant_key, date_key)`) e
  alimenta `gap_req_conf` direttamente, senza passare da
  `derived_manufacturing_demand`/`slots_requested`. Round T3 precedente: era
  eseguito dal motore come root ma assente da `MEASURE_DAG` — un buco nel
  contratto dichiarato (un consumatore che si fidasse solo del DAG per
  sapere cosa alimenta un gap non lo vedeva). Ora è dichiarato lì; il motore
  non porta più un'altezza iniettata privatamente (vedi `_node_heights`).
- **`derived_manufacturing_demand`** aggrega su `(manufact_key, date_key)`,
  sommando `requested_production` su tutte le division che vi contribuiscono
  via `resolve_manufacturing_items()` (produces/aggregates/splits, F7);
  `dependent_demand` resta fuori per costruzione — è un salto successivo
  della rete (il semilavorato tirato dal finito), non parte di questa
  risoluzione vendita->produzione, ed è quello che `resolve_manufacturing_items`
  già esclude.
- **Sito di produzione per lo spread degli slot**: per ogni `manufact_key` si
  usa il plant eleggibile a priorità minima (`production_eligibility.priority`,
  master data F8) — non un'allocazione multi-plant (quella soppesa capacità
  e vincoli, è T7), solo "dove questa domanda consumerebbe capacità se
  prodotta al sito preferito". Un `manufact_key` senza eleggibilità nota non
  produce celle `slots_requested` (buco dichiarato, non un errore: la rete
  produttiva è sparsa per costruzione, vedi `graph.py`).
- **Spread a due mesi**: `weeks_production` è letto da `TWSC_PAR_CALWEEK`
  (master data, non da un valore inventato), mediato sulle settimane di
  calendario del mese target con `aggregate.combine(agg_method, ...)`
  (`agg_method` letto da `DMEASURE_OPS`, non hardcoded a `"avg"`). La quota
  che eccede la granularità del plant (`slot_granularity_factor`, DPLANT)
  trabocca sul mese **precedente** — occorre iniziare a produrre in anticipo
  quando il tempo di attraversamento supera una finestra di granularità.
  Nessun `manufact_key`/mese con `weeks_production` mancante contribuisce
  (cella non calcolabile, non zero fabbricato).
- **`value_gap`**: `rate_card` (F… Integrated Reconciliation) copre solo 4
  delle 14 `manufacturing_category` nel seed — una cella `gap_req_conf` senza
  tariffa applicabile non produce una cella `value_gap` (sparso, non `0.0`
  fabbricato). Ai fini di `CutoffStats` (AC11) questo caso conta come
  `cutoff`, non `computed` né un `visited` "perso": vedi il docstring di
  `CutoffStats` (`cells.py`) e di `full_recalculate()` sotto.

Correttezza di AC10 per costruzione: ogni cella di ogni nodo derivato ha
**una sola** funzione `_compute_*_cell()` che la ricalcola per intero dal
proprio stato a monte corrente. `full_recalculate()` e `recalculate()`
chiamano la stessa funzione per la stessa chiave — non due percorsi che
potrebbero divergere per ordine di somma in virgola mobile o per una
differenza di formula dimenticata in uno dei due. L'unica differenza fra i
due è **quali** chiavi vengono visitate: tutte (`full_recalculate`) o solo
quelle raggiungibili dal sottografo a valle delle celle cambiate, con early
cutoff quando una cella ricalcolata risulta invariata (`recalculate`, AC11).
"""
from __future__ import annotations

import heapq
import itertools
import math
from collections.abc import Callable, Iterable, Sequence

from ..semantic import dimensions, graph, measures
from . import aggregate, dates
from .cells import (
    CellKey,
    CellValues,
    ConfirmedProductionEdit,
    CutoffStats,
    RecalcResult,
    RequestedProductionEdit,
)
from .errors import UnknownCellEditError

CellEdit = RequestedProductionEdit | ConfirmedProductionEdit

# Nodi calcolati che il motore sa ricalcolare per cella (esclude le due
# sorgenti, che si scrivono con un edit, non si "ricalcolano").
_COMPUTED_NODES = (
    "derived_manufacturing_demand",
    "slots_requested",
    "gap_req_conf",
    "value_gap",
)


def _node_heights() -> dict[str, int]:
    """Height di ogni nodo del DAG dichiarato (1 + max height delle
    dipendenze) — `requested_production` e `confirmed_production` sono
    entrambi sorgenti (`depends_on=()`) e restano a height 0 per
    costruzione, direttamente da `measures.nodes()`: nessuna altezza
    iniettata privatamente dal motore (round T3: `confirmed_production` era
    un'eccezione qui perché mancava da `MEASURE_DAG` — ora non lo è più, la
    dichiarazione del DAG è l'unica fonte di verità sull'altezza). Il
    min-heap di `recalculate()` processa in questo ordine: un nodo non si
    ricalcola finché tutti i suoi input non sono finali — è ciò che elimina
    il glitch del diamante (A5 punto 2): una cella raggiunta da due percorsi
    si ricalcola una sola volta. `gap_req_conf` ha due dipendenze
    (`slots_requested`, `confirmed_production`) e la sua height (3) resta
    corretta con la formula generica: `1 + max(height(dep) per ogni dep)`."""
    nodes = measures.nodes()
    heights: dict[str, int] = {}

    def height(name: str) -> int:
        if name in heights:
            return heights[name]
        depends_on = nodes[name].depends_on
        h = 0 if not depends_on else 1 + max(height(dep) for dep in depends_on)
        heights[name] = h
        return h

    for name in nodes:
        height(name)
    return heights


class RecalcEngine:
    """Stato vivo di un ricalcolo su una coppia di versioni (demand/ops) —
    non apre connessioni proprie (`con` è del chiamante, coerente con
    `ibp/db.py`). Costruito, carica le celle sorgente e converge subito con
    un `full_recalculate()`: da lì in poi `recalculate(changed_cells)` tiene
    lo stato allineato per via incrementale."""

    def __init__(self, con, *, demand_version_key: int, ops_version_key: int):
        self._con = con
        self._demand_version_key = demand_version_key
        self._ops_version_key = ops_version_key

        weeks_measure = measures.get_measure(con, "WEEKS_PRODUCTION")
        self._weeks_measure_key = weeks_measure.measure_key
        self._weeks_agg_method = weeks_measure.agg_method

        self._heights = _node_heights()

        # Cache di master data (item/plant/eleggibilità/weeks/rate_card):
        # letture ripetute sulla stessa chiave non devono ritornare al DB.
        self._item_factor_cache: dict[int, dimensions.ItemFactors] = {}
        self._plant_capacity_cache: dict[int, dimensions.PlantCapacity] = {}
        self._eligible_plant_cache: dict[int, int | None] = {}
        self._weeks_cache: dict[tuple[int, int, int], float | None] = {}
        self._rate_cache: dict[tuple[str, int], float | None] = {}

        # Risoluzione item_link, cache + indice inverso (vedi
        # `_ensure_rp_targets`): il DAG dichiarato non cambia a un edit di
        # valore, solo lo stato delle celle — l'indice si costruisce una
        # volta per (product_key, date_key) e si estende, non si ricostruisce.
        self._rp_targets: dict[tuple[int, int], dict[tuple[int, int], float]] = {}
        self._dmd_reverse: dict[tuple[int, int], set[tuple[int, int]]] = {}

        self._load_requested_production()
        self._load_confirmed_production()

        self._values: dict[str, dict[CellKey, float]] = {n: {} for n in _COMPUTED_NODES}
        self.full_recalculate()

    # -- caricamento sorgenti ---------------------------------------------

    def _load_requested_production(self) -> None:
        measure_key = measures.get_measure(self._con, "REQ_PROD").measure_key
        rows = self._con.execute(
            "SELECT product_key, division_key, date_key, value FROM TSOP_DEMAND "
            "WHERE version_key = ? AND measure_key = ?",
            [self._demand_version_key, measure_key],
        ).fetchall()
        self._requested_production: dict[tuple[int, int, int], float] = {}
        self._rp_by_product_date: dict[tuple[int, int], set[int]] = {}
        for product_key, division_key, date_key, value in rows:
            self._requested_production[(product_key, division_key, date_key)] = float(value)
            self._rp_by_product_date.setdefault((product_key, date_key), set()).add(division_key)

    def _load_confirmed_production(self) -> None:
        current_key = measures.get_measure(self._con, "SLOTS_CURRENT_MONTH").measure_key
        previous_key = measures.get_measure(self._con, "SLOTS_PREVIOUS_MONTH").measure_key
        rows = self._con.execute(
            "SELECT manufact_key, plant_key, date_key, SUM(value) FROM TSOP_OPS "
            "WHERE version_key = ? AND measure_key IN (?, ?) "
            "GROUP BY manufact_key, plant_key, date_key",
            [self._ops_version_key, current_key, previous_key],
        ).fetchall()
        self._confirmed_production: dict[tuple[int, int, int], float] = {
            (manufact_key, plant_key, date_key): float(value)
            for manufact_key, plant_key, date_key, value in rows
        }

    # -- master data (cache) ------------------------------------------------

    def _item_factor(self, item_key: int) -> dimensions.ItemFactors:
        if item_key not in self._item_factor_cache:
            self._item_factor_cache[item_key] = dimensions.get_item_factors(self._con, item_key)
        return self._item_factor_cache[item_key]

    def _plant_capacity(self, plant_key: int) -> dimensions.PlantCapacity:
        if plant_key not in self._plant_capacity_cache:
            self._plant_capacity_cache[plant_key] = dimensions.get_plant_capacity(self._con, plant_key)
        return self._plant_capacity_cache[plant_key]

    def _eligible_plant_for(self, manufact_key: int, date_key: int) -> int | None:
        """Plant a priorità minima eleggibile per `manufact_key`
        (`production_eligibility`, F8) — cache per `manufact_key`: nel seed
        `valid_to` è sempre `NULL` (eleggibilità stabile nell'orizzonte),
        quindi non si ricalcola per ogni data; `date_key` resta usato per il
        filtro di validità alla prima risoluzione."""
        if manufact_key in self._eligible_plant_cache:
            return self._eligible_plant_cache[manufact_key]
        as_of = dates.date_key_to_date(date_key)
        row = self._con.execute(
            "SELECT plant FROM production_eligibility WHERE manufacturing_key = ? "
            "AND valid_from <= ? AND (valid_to IS NULL OR valid_to > ?) "
            "ORDER BY priority ASC, plant ASC LIMIT 1",
            [manufact_key, as_of, as_of],
        ).fetchone()
        plant = int(row[0]) if row else None
        self._eligible_plant_cache[manufact_key] = plant
        return plant

    def _weeks_production(self, manufact_key: int, plant_key: int, date_key: int) -> float | None:
        """Media (`agg_method` di WEEKS_PRODUCTION, letto dal catalogo — non
        hardcoded) delle settimane di calendario di `TWSC_PAR_CALWEEK` che
        cadono nel mese di `date_key`. `None` se non c'è nessuna settimana
        nota per quella combinazione: master data mancante, non zero."""
        cache_key = (manufact_key, plant_key, date_key)
        if cache_key in self._weeks_cache:
            return self._weeks_cache[cache_key]
        month_start = dates.date_key_to_date(date_key)
        month_end = dates.date_key_to_date(dates.shift_date_key(date_key, 1))
        rows = self._con.execute(
            "SELECT value FROM TWSC_PAR_CALWEEK WHERE version_key = ? AND manufact_key = ? "
            "AND plant_key = ? AND measure_key = ? AND calweek_date >= ? AND calweek_date < ?",
            [self._ops_version_key, manufact_key, plant_key, self._weeks_measure_key, month_start, month_end],
        ).fetchall()
        if not rows:
            result = None
        else:
            result = aggregate.combine(self._weeks_agg_method, [float(r[0]) for r in rows])
        self._weeks_cache[cache_key] = result
        return result

    def _rate_for(self, manufacturing_category: str | None, date_key: int) -> float | None:
        """Tariffa (`avg_revenue_per_unit`) applicabile: riga `rate_card` con
        `manufacturing_category` corrispondente e `period` più recente
        `<= date_key` (stesso pattern "ultimo periodo valido" di
        `resolve_manufacturing_items`). `None` se la categoria non ha
        copertura in `rate_card` (nel seed solo 4 categorie su 14 — è un
        buco reale della master data, non un difetto del motore) o se
        `manufacturing_category` è `None`."""
        if manufacturing_category is None:
            return None
        cache_key = (manufacturing_category, date_key)
        if cache_key in self._rate_cache:
            return self._rate_cache[cache_key]
        target = dates.date_key_to_date(date_key)
        row = self._con.execute(
            "SELECT avg_revenue_per_unit FROM rate_card WHERE manufacturing_category = ? "
            "AND period <= ? ORDER BY period DESC LIMIT 1",
            [manufacturing_category, target],
        ).fetchone()
        result = float(row[0]) if row else None
        self._rate_cache[cache_key] = result
        return result

    # -- risoluzione item_link (requested_production -> manufacturing) -----

    def _ensure_rp_targets(self, product_key: int, date_key: int) -> dict[tuple[int, int], float]:
        """Mappa `(product_key, date_key) -> {(to_item, target_date_key): quota_fraction}`
        via `resolve_manufacturing_items()` (F7, produces/aggregates/splits —
        `dependent_demand` resta fuori per costruzione di quella funzione).
        Cache per `(product_key, date_key)`: la struttura della rete non
        cambia a un edit di valore, solo lo stato delle celle. Effetto
        collaterale dichiarato: popola/estende `self._dmd_reverse`, l'indice
        inverso che permette di ricalcolare per intero **una sola** cella
        `derived_manufacturing_demand` senza scandire tutte le
        `requested_production`."""
        cache_key = (product_key, date_key)
        if cache_key in self._rp_targets:
            return self._rp_targets[cache_key]
        as_of = dates.date_key_to_date(date_key)
        realisations = graph.resolve_manufacturing_items(self._con, product_key, as_of=as_of)
        targets: dict[tuple[int, int], float] = {}
        for r in realisations:
            target_date = dates.shift_date_key(date_key, r.offset_months)
            target_key = (r.to_item, target_date)
            targets[target_key] = targets.get(target_key, 0.0) + r.quota / 100.0
            self._dmd_reverse.setdefault(target_key, set()).add((product_key, date_key))
        self._rp_targets[cache_key] = targets
        return targets

    # -- validazione batch (recalculate(), fase 1) --------------------------
    #
    # Round critic T3 (secondo passaggio): la prima correzione validava solo
    # `RequestedProductionEdit` per tipo esplicito (`isinstance`) e assumeva
    # — a parole, nel docstring di `recalculate()` — che `ConfirmedProductionEdit`
    # non avesse nulla da risolvere. Falso: `manufact_key` non è verificato
    # da nessuna parte finché la propagazione non arriva a `value_gap`
    # (`_item_factor` -> `KeyError` per un `manufact_key` inesistente in
    # `item`), cioè **dopo** che la fase 2 ha già scritto
    # `_confirmed_production`. Stesso difetto della prima correzione, attraverso
    # l'altro tipo di edit: batch parzialmente applicato, indice/stato
    # avvelenato, ogni `full_recalculate()` successivo rotto per sempre.
    #
    # La correzione non è "aggiungere un altro ramo isinstance" (lo stesso
    # errore si ripeterebbe al prossimo tipo di edit che qualcuno aggiunge):
    # ogni tipo di edit registra qui il proprio validatore, e la fase 1 lo
    # invoca per `type(edit)` senza sapere nulla del tipo specifico. Un tipo
    # di edit senza validatore registrato non passa silenziosamente — cade
    # nel ramo "nessun validatore trovato" e solleva `UnknownCellEditError`,
    # esattamente come un tipo sconosciuto. Aggiungere un tipo di edit senza
    # aggiungere anche il suo validatore qui non è più possibile in silenzio.
    def _validate_requested_production_edit(self, edit: RequestedProductionEdit) -> None:
        """Risolve `product_key` via item_link (F7) — solleva se non è un
        `planning_model` risolvibile (es. una manufacturing key passata per
        errore). Cache-safe: la fase 2 richiama `_ensure_rp_targets` sulla
        stessa chiave a costo zero (cache hit)."""
        self._ensure_rp_targets(edit.product_key, edit.date_key)

    def _validate_confirmed_production_edit(self, edit: ConfirmedProductionEdit) -> None:
        """Risolve `manufact_key` via `_item_factor()` — solleva `KeyError`
        se non esiste in `item`. È esattamente il lookup che
        `_compute_value_gap_cell` farebbe comunque, ma spostato **prima**
        di qualunque mutazione invece che durante la propagazione (dove un
        fallimento arriverebbe a batch già applicato). Cache-safe: ogni
        chiamata successiva sulla stessa `manufact_key` (fase 2, propagazione,
        prossime chiamate) è una cache hit."""
        self._item_factor(edit.manufact_key)

    # Dispatch per tipo esatto di edit -> validatore. Unica fonte di verità
    # su "quali tipi di edit esistono e come si validano": `recalculate()`
    # non contiene più un `isinstance` per tipo, guarda solo questa mappa.
    _EDIT_VALIDATORS: dict[type, Callable[["RecalcEngine", CellEdit], None]] = {
        RequestedProductionEdit: _validate_requested_production_edit,
        ConfirmedProductionEdit: _validate_confirmed_production_edit,
    }

    # -- calcolo per cella (una sola versione per nodo, vedi docstring modulo) --

    def _compute_dmd_cell(self, key: tuple[int, int]) -> float:
        """Somma su `sorted(...)`, non sull'iterazione diretta di
        `self._dmd_reverse`/`self._rp_by_product_date` (entrambi `set`):
        l'ordine di iterazione di un `set` non è garantito stabile fra una
        cache costruita incrementalmente (edit dopo edit) e una ricostruita
        da zero, anche a parità di contenuto finale — la somma in virgola
        mobile non è associativa, quindi ordini diversi potevano produrre
        l'ultimo bit diverso fra `recalculate()` e `full_recalculate()`
        (round critic T3: 8 batch su 120 differivano di 1 ulp). Un ordine
        totale esplicito elimina la sorgente di non determinismo alla radice
        invece di tollerarla con `math.isclose` più a valle."""
        total = 0.0
        for product_key, source_date in sorted(self._dmd_reverse.get(key, ())):
            quota_fraction = self._rp_targets.get((product_key, source_date), {}).get(key)
            if quota_fraction is None:
                continue
            for division_key in sorted(self._rp_by_product_date.get((product_key, source_date), ())):
                value = self._requested_production.get((product_key, division_key, source_date), 0.0)
                total += value * quota_fraction
        return total

    def _compute_slots_cell(self, key: tuple[int, int, int]) -> float:
        manufact_key, plant_key, date_key = key
        if self._eligible_plant_for(manufact_key, date_key) != plant_key:
            return 0.0
        factor = self._item_factor(manufact_key).slot_equivalence_factor
        granularity = self._plant_capacity(plant_key).slot_granularity_factor
        total = 0.0

        dmd_here = self._values["derived_manufacturing_demand"].get((manufact_key, date_key))
        if dmd_here is not None:
            weeks = self._weeks_production(manufact_key, plant_key, date_key)
            if weeks is not None:
                current_share = min(1.0, weeks / granularity)
                total += dmd_here * factor * current_share

        next_date = dates.shift_date_key(date_key, 1)
        dmd_next = self._values["derived_manufacturing_demand"].get((manufact_key, next_date))
        if dmd_next is not None:
            weeks_next = self._weeks_production(manufact_key, plant_key, next_date)
            if weeks_next is not None:
                previous_share = max(0.0, (weeks_next - granularity) / granularity)
                total += dmd_next * factor * previous_share

        return total

    def _compute_gap_cell(self, key: tuple[int, int, int]) -> float:
        slots = self._values["slots_requested"].get(key, 0.0)
        confirmed = self._confirmed_production.get(key, 0.0)
        return slots - confirmed

    def _compute_value_gap_cell(self, key: tuple[int, int, int]) -> float | None:
        manufact_key, _plant_key, date_key = key
        gap = self._values["gap_req_conf"].get(key)
        if gap is None:
            return None
        category = self._item_factor(manufact_key).manufacturing_category
        rate = self._rate_for(category, date_key)
        if rate is None:
            return None
        return gap * rate

    def _compute_cell(self, node: str, key: CellKey) -> float | None:
        if node == "derived_manufacturing_demand":
            return self._compute_dmd_cell(key)
        if node == "slots_requested":
            return self._compute_slots_cell(key)
        if node == "gap_req_conf":
            return self._compute_gap_cell(key)
        if node == "value_gap":
            return self._compute_value_gap_cell(key)
        raise ValueError(f"nodo non ricalcolabile per cella: {node!r}")

    def _downstream(self, node: str, key: CellKey) -> Iterable[tuple[str, CellKey]]:
        """Celle a valle direttamente sporcate da un cambio di `(node, key)`
        — il verso in cui un edit si propaga, non quello di lettura delle
        dipendenze (stesso verso di `measures.edges()`)."""
        if node == "derived_manufacturing_demand":
            manufact_key, date_key = key
            plant = self._eligible_plant_for(manufact_key, date_key)
            if plant is None:
                return
            yield ("slots_requested", (manufact_key, plant, date_key))
            yield ("slots_requested", (manufact_key, plant, dates.shift_date_key(date_key, -1)))
        elif node == "slots_requested":
            yield ("gap_req_conf", key)
        elif node == "gap_req_conf":
            yield ("value_gap", key)
        elif node == "value_gap":
            return
        else:
            raise ValueError(f"nodo senza downstream dichiarato: {node!r}")

    @staticmethod
    def _classify_cell(old: float | None, new: float | None) -> str:
        """Classifica l'esito del ricalcolo di una cella in uno dei tre
        contatori di `CutoffStats` (AC11): `"absent"` se non c'era e non
        c'è (`None -> None`: nessun dato, nessuna propagazione, non un
        cutoff — round critic T3, vedi `cells.py::CutoffStats`); `"cutoff"`
        se c'era un valore e il ricalcolo produce lo stesso valore (entro
        tolleranza — due `float` che differiscono solo per rumore in
        virgola mobile non devono sporcare i dipendenti, altrimenti il
        cutoff non taglierebbe mai nulla in pratica); `"computed"` per
        qualunque altro caso (valore nuovo, valore cambiato, o valore
        rimosso — uno stato che passa da presente ad assente è comunque un
        cambio di stato memorizzato, non un `"absent"`)."""
        if old is None and new is None:
            return "absent"
        if old is None or new is None:
            return "computed"
        if math.isclose(old, new, rel_tol=1e-9, abs_tol=1e-9):
            return "cutoff"
        return "computed"

    def _snapshot(self) -> CellValues:
        return {
            "requested_production": dict(self._requested_production),
            "confirmed_production": dict(self._confirmed_production),
            **{node: dict(self._values[node]) for node in _COMPUTED_NODES},
        }

    # -- API pubblica ---------------------------------------------------------

    def full_recalculate(self) -> RecalcResult:
        """Ricalcolo completo: ogni cella di ogni nodo calcolato, senza
        propagazione (non c'è un sottografo da attraversare selettivamente,
        si visita tutto). È il riferimento contro cui `recalculate()` si
        misura (AC10): stessa funzione `_compute_*_cell()` per chiave, quindi
        nessuna divergenza possibile per un percorso di calcolo diverso fra i
        due metodi.

        `stats.absent` **non** è sempre `0` qui: per `value_gap`, una cella
        `gap_req_conf` la cui `manufacturing_category` non ha copertura in
        `rate_card` (F… Integrated Reconciliation, sparsa per costruzione nel
        seed) produce `_compute_value_gap_cell() is None` — nessun valore da
        salvare, cella assente sia prima sia dopo (`_classify_cell(None,
        None) == "absent"`, vedi `cells.py::CutoffStats`). Non è un
        `"cutoff"`: non c'è mai stata propagazione da tagliare, `value_gap`
        è una foglia e la cella non ha mai avuto un valore da cui "non
        cambiare". Le altre tre passate (dmd/slots/gap_req_conf) producono
        sempre un valore reale, quindi restano interamente `computed`,
        `cutoff == 0` e `absent == 0`."""
        stats = CutoffStats()
        self._values = {n: {} for n in _COMPUTED_NODES}

        dmd_keys: set[tuple[int, int]] = set()
        for product_key, date_key in self._rp_by_product_date:
            targets = self._ensure_rp_targets(product_key, date_key)
            dmd_keys.update(targets.keys())
        for key in dmd_keys:
            stats.visited += 1
            stats.computed += 1
            self._values["derived_manufacturing_demand"][key] = self._compute_dmd_cell(key)

        slot_keys: set[tuple[int, int, int]] = set()
        for manufact_key, date_key in dmd_keys:
            plant = self._eligible_plant_for(manufact_key, date_key)
            if plant is None:
                continue
            slot_keys.add((manufact_key, plant, date_key))
            slot_keys.add((manufact_key, plant, dates.shift_date_key(date_key, -1)))
        for key in slot_keys:
            stats.visited += 1
            stats.computed += 1
            self._values["slots_requested"][key] = self._compute_slots_cell(key)

        gap_keys = slot_keys | set(self._confirmed_production.keys())
        for key in gap_keys:
            stats.visited += 1
            stats.computed += 1
            self._values["gap_req_conf"][key] = self._compute_gap_cell(key)

        for key in gap_keys:
            stats.visited += 1
            value = self._compute_value_gap_cell(key)
            if value is None:
                # Nessuna copertura rate_card per questa manufacturing_category:
                # esaminata, nessun valore da salvare -> absent (vedi docstring
                # di questo metodo), non un caso silenziosamente non contato,
                # e non un cutoff (nessuna propagazione interrotta: la cella
                # non ha mai avuto un valore).
                stats.absent += 1
                continue
            stats.computed += 1
            self._values["value_gap"][key] = value

        return RecalcResult(values=self._snapshot(), stats=stats)

    def recalculate(self, changed_cells: Sequence[CellEdit]) -> RecalcResult:
        """Applica `changed_cells` (un batch di `RequestedProductionEdit` /
        `ConfirmedProductionEdit`) e ripropaga **solo** il sottografo a
        valle, in ordine di height (min-heap — A5 punto 2): un nodo si
        ricalcola quando i suoi input sono finali, una volta sola anche se
        raggiunto da più percorsi (il diamante `slots_requested ->
        gap_req_conf` non lo ricalcola due volte). Early cutoff (AC11): una
        cella ricalcolata e trovata invariata non sporca i suoi dipendenti —
        `RecalcResult.stats` conta `visited`/`computed`/`cutoff`/`absent` per
        questa chiamata (vedi `cells.py::CutoffStats`). Il risultato
        (`RecalcResult.values`) è lo stato completo corrente di ogni nodo:
        identico, per costruzione (vedi docstring di modulo), a quello di un
        `full_recalculate()` sullo stesso stato sorgente (AC10).

        Il batch è **tutto o niente** (round critic T3, corretto due volte):
        ogni edit è validato **prima** che una qualunque mutazione sia
        applicata, tramite `_EDIT_VALIDATORS` — un dispatch per `type(edit)`
        a un validatore che risolve la chiave dell'edit (item_link per
        `RequestedProductionEdit`, `item`/`_item_factor` per
        `ConfirmedProductionEdit`) esattamente come farebbe comunque la
        propagazione più a valle, ma **prima** di scrivere qualunque stato.
        Un tipo di edit senza validatore registrato in `_EDIT_VALIDATORS`
        solleva `UnknownCellEditError` invece di procedere non validato: la
        prima correzione di questo round validava `RequestedProductionEdit`
        per `isinstance` esplicito e **assumeva**, scorrettamente, che
        `ConfirmedProductionEdit` non avesse nulla da risolvere — falso
        (`manufact_key` non verificato da nessuna parte finché la
        propagazione non arrivava a `value_gap` via `_item_factor`, *dopo*
        che la fase 2 aveva già scritto `_confirmed_production`: stesso
        difetto della prima correzione, attraverso l'altro tipo di edit).
        Il dispatch per tipo, non per `isinstance` sparso, esiste apposta
        perché un nuovo tipo di edit senza un validatore registrato qui non
        passa silenziosamente: cade nello stesso ramo di un tipo sconosciuto.
        Senza questa validazione, un edit successivo malformato lascerebbe
        gli edit precedenti già scritti ma mai ripropagati (AC10 rotto) e,
        peggio, lascerebbe una chiave avvelenata nello stato (`_rp_by_product_date`
        per un `product_key` invalido, `_confirmed_production` per un
        `manufact_key` invalido) che rompe ogni `full_recalculate()`
        successivo per sempre — un singolo batch HTTP malformato blocca il
        motore in modo permanente. Con la validazione a monte, se un edit
        fallisce il motore resta esattamente nello stato in cui si trovava
        prima della chiamata."""
        stats = CutoffStats()
        heap: list[tuple[int, int, str, CellKey]] = []
        pending: set[tuple[str, CellKey]] = set()
        counter = itertools.count()

        def enqueue(node: str, key: CellKey) -> None:
            tag = (node, key)
            if tag in pending:
                return
            pending.add(tag)
            heapq.heappush(heap, (self._heights[node], next(counter), node, key))

        # Fase 1 — valida, senza mutare alcuno stato osservabile
        # dall'esterno: per ogni edit, dispatch su `type(edit)` a
        # `_EDIT_VALIDATORS` (nessun `isinstance` per tipo qui — vedi
        # docstring). I validatori sono cache-safe anche se il batch viene
        # poi rifiutato per un edit successivo: risolvono solo fatti
        # strutturali (item_link per un product_key/date, `item` per un
        # manufact_key), mai un valore di cella, quindi restano validi a
        # prescindere da come il batch finisce.
        for edit in changed_cells:
            validator = self._EDIT_VALIDATORS.get(type(edit))
            if validator is None:
                raise UnknownCellEditError(type(edit))
            validator(self, edit)

        # Fase 2 — applica. Da qui in avanti nessuna chiamata di questo
        # metodo può più sollevare per un edit malformato: è già stato
        # validato sopra, il batch procede per intero. `_ensure_rp_targets`/
        # `_item_factor` sono cache hit qui (già risolti in fase 1).
        for edit in changed_cells:
            if isinstance(edit, RequestedProductionEdit):
                key = (edit.product_key, edit.division_key, edit.date_key)
                self._requested_production[key] = edit.new_value
                self._rp_by_product_date.setdefault(
                    (edit.product_key, edit.date_key), set()
                ).add(edit.division_key)
                for target_key in self._ensure_rp_targets(edit.product_key, edit.date_key):
                    enqueue("derived_manufacturing_demand", target_key)
            else:  # ConfirmedProductionEdit, già validato in fase 1
                key = (edit.manufact_key, edit.plant_key, edit.date_key)
                self._confirmed_production[key] = edit.new_value
                enqueue("gap_req_conf", key)

        while heap:
            _, _, node, key = heapq.heappop(heap)
            tag = (node, key)
            if tag not in pending:
                continue  # già processata in questo giro (diamante)
            pending.discard(tag)
            stats.visited += 1
            new_value = self._compute_cell(node, key)
            old_value = self._values[node].get(key)
            outcome = self._classify_cell(old_value, new_value)
            if outcome == "computed":
                stats.computed += 1
                if new_value is None:
                    self._values[node].pop(key, None)
                else:
                    self._values[node][key] = new_value
                for downstream_node, downstream_key in self._downstream(node, key):
                    enqueue(downstream_node, downstream_key)
            elif outcome == "cutoff":
                stats.cutoff += 1
            else:  # "absent"
                stats.absent += 1

        return RecalcResult(values=self._snapshot(), stats=stats)
