"""Registry delle misure: catalogo (dal DB) + DAG dichiarato delle misure
calcolate (D4/A5).

Due concetti distinti, deliberatamente nello stesso modulo perché il task
li chiama entrambi "registry delle misure":

1. `MeasureDef`/`list_measures`/`get_measure` — il catalogo delle misure
   *sorgente* del cubo, righe di `DMEASURE_DEMAND`/`DMEASURE_OPS` lette dal
   DB (mai literal: se il seed aggiunge una misura, compare qui senza
   toccare Python).
2. `MEASURE_DAG`/`nodes`/`edges`/`topological_order`/`dirty_set` — il DAG
   delle misure *calcolate* a valle (la catena `requested_production ->
   derived_manufacturing_demand -> slots_requested -> gap_req_conf ->
   value_gap` di D4), dichiarato come dato Python perché non ha una
   controparte a riga nel cubo dEPM: è la pipeline di derivazione che T3
   eseguirà. **Qui non si calcola nulla** — nessuna funzione di questo
   modulo legge `TSOP_DEMAND`/`TSOP_OPS` o produce un valore; l'esecuzione è
   `ibp/engine` (T3), fuori scope di T2.

   `gap_req_conf` ha **due** dipendenze, non una sola: `slots_requested`
   (il lato Requested, in fondo alla catena sopra) e `confirmed_production`
   (il lato Confirmed, un secondo nodo sorgente indipendente che legge
   TSOP_OPS). Chi consuma questo DAG per sapere "cosa alimenta un gap"
   (T4/T7/T10) deve vedere entrambi qui, non solo la catena principale —
   round T3: `confirmed_production` mancava da questo registry pur essendo
   già eseguita come root dal motore, un buco nel contratto dichiarato.
"""
from __future__ import annotations

import graphlib
from collections import defaultdict
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# 1. Catalogo misure (dal DB)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MeasureDef:
    measure_key: int
    measure_code: str
    measure_name: str
    uom: str
    agg_method: str
    side: str  # 'demand' | 'ops'


_SIDE_TABLES = {"demand": "DMEASURE_DEMAND", "ops": "DMEASURE_OPS"}


def list_measures(con, side: str | None = None) -> list[MeasureDef]:
    """`side=None` ritorna entrambi i cataloghi (demand + ops)."""
    if side is not None and side not in _SIDE_TABLES:
        raise ValueError(f"side sconosciuto: {side!r} (atteso 'demand' o 'ops')")
    sides = (side,) if side is not None else tuple(_SIDE_TABLES)
    out: list[MeasureDef] = []
    for s in sides:
        table = _SIDE_TABLES[s]
        rows = con.execute(
            f"SELECT measure_key, measure_code, measure_name, uom, agg_method "
            f"FROM {table} ORDER BY measure_key"
        ).fetchall()
        out.extend(MeasureDef(*r, side=s) for r in rows)
    return out


def get_measure(con, measure_code: str) -> MeasureDef:
    for m in list_measures(con):
        if m.measure_code == measure_code:
            return m
    raise KeyError(f"measure_code sconosciuto: {measure_code}")


# ---------------------------------------------------------------------------
# 2. DAG dichiarato delle misure calcolate (D4) — dato, non esecuzione.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MeasureNode:
    name: str
    depends_on: tuple[str, ...]
    description: str


MEASURE_DAG: dict[str, MeasureNode] = {
    "requested_production": MeasureNode(
        "requested_production", (),
        "Domanda richiesta al planning model (TSOP_DEMAND, misura REQ_PROD)."),
    "confirmed_production": MeasureNode(
        "confirmed_production", (),
        "Produzione confermata sul lato supply (TSOP_OPS, SLOTS_CURRENT_MONTH + "
        "SLOTS_PREVIOUS_MONTH) — secondo nodo sorgente del DAG, indipendente da "
        "requested_production: un edit qui ripropaga direttamente in "
        "gap_req_conf senza passare da derived_manufacturing_demand/"
        "slots_requested (round T3: la sua assenza da MEASURE_DAG era un buco "
        "nel contratto dichiarato, non una scelta del motore — T3 lo eseguiva "
        "comunque come root esogena; ora è dichiarato qui e dirty_set()/"
        "edges() lo sanno)."),
    "derived_manufacturing_demand": MeasureNode(
        "derived_manufacturing_demand", ("requested_production",),
        "Domanda derivata a manufacturing key via item_link "
        "('produces'/'aggregates'/'splits', F7)."),
    "slots_requested": MeasureNode(
        "slots_requested", ("derived_manufacturing_demand",),
        "Slot richiesti = domanda derivata * slot_equivalence_factor, spalmati "
        "su due mesi secondo weeks_production (TWSC_PAR_CALWEEK)."),
    "gap_req_conf": MeasureNode(
        "gap_req_conf", ("slots_requested", "confirmed_production"),
        "Gap fra Requested (slots_requested) e Confirmed (confirmed_production) "
        "dopo l'allocazione vincolata (A)."),
    "value_gap": MeasureNode(
        "value_gap", ("gap_req_conf",),
        "Finanziarizzazione del gap in unità via rate_card (Integrated Reconciliation)."),
}


def nodes() -> dict[str, MeasureNode]:
    """Copia difensiva: il chiamante non deve poter mutare il registry."""
    return dict(MEASURE_DAG)


def edges() -> list[tuple[str, str]]:
    """Archi (dipendenza -> misura dipendente): è il verso in cui un edit si
    propaga (dirty a valle), non quello di lettura delle dipendenze."""
    return [(dep, name) for name, node in MEASURE_DAG.items() for dep in node.depends_on]


def topological_order() -> list[str]:
    """Un ordine di calcolo valido: ogni misura appare dopo tutte le sue
    dipendenze. `graphlib.TopologicalSorter` (stdlib, coerente con A5) valida
    anche l'aciclicità, sollevando `graphlib.CycleError` se il DAG dichiarato
    non lo fosse — un bug di dichiarazione qui si scopre subito, non a runtime
    nel motore."""
    ts = graphlib.TopologicalSorter({name: node.depends_on for name, node in MEASURE_DAG.items()})
    return list(ts.static_order())


def dirty_set(changed_measure: str) -> set[str]:
    """Il sottografo a valle di `changed_measure` (se stessa inclusa): le
    misure che un cambio di quella misura sporca. T3 userà questo insieme per
    ricalcolare solo il sottografo (AC8/D4) — qui è puro dato, nessun valore
    viene letto o calcolato."""
    if changed_measure not in MEASURE_DAG:
        raise KeyError(f"misura sconosciuta nel DAG dichiarato: {changed_measure}")
    downstream: dict[str, list[str]] = defaultdict(list)
    for name, node in MEASURE_DAG.items():
        for dep in node.depends_on:
            downstream[dep].append(name)

    seen = {changed_measure}
    stack = [changed_measure]
    while stack:
        current = stack.pop()
        for nxt in downstream.get(current, ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen
