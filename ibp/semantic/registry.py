"""Facciata del semantic layer: un solo oggetto (`SemanticRegistry`) che
espone dimensioni, misure (catalogo + DAG dichiarato) e overlay a grafo
sopra una connessione DuckDB fornita dal chiamante (`ibp.db`) — non ne apre
di proprie (T2 done_when #5).

Le funzioni pure di `dimensions.py`/`measures.py`/`graph.py` restano
utilizzabili direttamente (es. per un test che vuole una sola query); questa
classe è solo comodità per chi vuole un punto d'ingresso unico, come lo
smoke script o un futuro router API.
"""
from __future__ import annotations

import datetime as dt

from ..domain.cycle import PhaseDef, StateMachine, build_phase_sequence_machine
from . import dimensions as _dimensions
from . import graph as _graph
from . import measures as _measures


class SemanticRegistry:
    def __init__(self, con):
        self._con = con

    # -- dimensioni ----------------------------------------------------
    def dimensions(self) -> list[_dimensions.Dimension]:
        return _dimensions.list_dimensions(self._con)

    def plants(self) -> list[_dimensions.PlantCapacity]:
        return _dimensions.list_plants(self._con)

    def plant_capacity(self, plant_key: int) -> _dimensions.PlantCapacity:
        return _dimensions.get_plant_capacity(self._con, plant_key)

    def item_factors(self, item_key: int) -> _dimensions.ItemFactors:
        return _dimensions.get_item_factors(self._con, item_key)

    def list_item_factors(self, role: str | None = None) -> list[_dimensions.ItemFactors]:
        return _dimensions.list_item_factors(self._con, role=role)

    # -- misure ----------------------------------------------------------
    def measures(self, side: str | None = None) -> list[_measures.MeasureDef]:
        return _measures.list_measures(self._con, side=side)

    def measure_dag_nodes(self) -> dict[str, _measures.MeasureNode]:
        return _measures.nodes()

    def measure_dag_edges(self) -> list[tuple[str, str]]:
        return _measures.edges()

    def measure_dag_order(self) -> list[str]:
        return _measures.topological_order()

    def measure_dirty_set(self, changed_measure: str) -> set[str]:
        return _measures.dirty_set(changed_measure)

    # -- ciclo/fasi (dato, usato da ibp.domain.cycle per costruire la
    #    state machine dell'ordine fasi) ----------------------------------
    def cycle_phases(self, cycle_id: int) -> list[PhaseDef]:
        rows = self._con.execute(
            "SELECT phase_id, cycle_id, phase_no, name, day_start, day_end, "
            "stat_state, gate FROM cycle_phase WHERE cycle_id = ? ORDER BY phase_no",
            [cycle_id],
        ).fetchall()
        if not rows:
            raise KeyError(f"nessuna cycle_phase per cycle_id={cycle_id}")
        return [PhaseDef(*r) for r in rows]

    def cycle_phase_machine(self, cycle_id: int) -> StateMachine:
        return build_phase_sequence_machine(self.cycle_phases(cycle_id))

    # -- overlay a grafo ---------------------------------------------------
    def neighbors(
        self,
        node_type: str,
        node_key: str,
        rel_type: str | None = None,
        *,
        direction: str = "out",
        as_of: dt.date | None = None,
    ) -> list[_graph.Edge]:
        return _graph.neighbors(
            self._con, node_type, node_key, rel_type, direction=direction, as_of=as_of
        )

    def resolve_manufacturing_items(
        self, product_key: int, as_of: dt.date | None = None
    ) -> list[_graph.ManufacturingRealisation]:
        return _graph.resolve_manufacturing_items(self._con, product_key, as_of=as_of)

    def resolve_identity(self, item_key: int, as_of: dt.date | None = None) -> _graph.ItemIdentity:
        return _graph.resolve_identity(self._con, item_key, as_of=as_of)
