"""Facciata di comodo su `ibp.scenario`, stesso pattern di
`ibp.semantic.registry.SemanticRegistry`: un solo oggetto che incapsula la
connessione (ricevuta, mai aperta qui) ed espone branch/scrittura/lettura/
confronto/promozione come metodi. Le funzioni pure dei singoli moduli
restano usabili direttamente — questa classe non aggiunge comportamento,
solo un punto d'ingresso unico per chi non vuole importare modulo per
modulo (T10, l'API HTTP; T3, l'engine, per il seam `mark_evaluated`)."""
from __future__ import annotations

import datetime as dt

from .branch import branch as _do_branch
from .branch import discard as _do_discard
from .branch import mark_evaluated as _do_mark_evaluated
from .compare import compare as _do_compare
from .edits import delete_cell as _do_delete_cell
from .edits import increment_cell as _do_increment_cell
from .edits import resolve_cell as _do_resolve_cell
from .edits import set_cell as _do_set_cell
from .models import CellKey, CompareRow, PromotionResult, ResolvedCell, Scenario, ScenarioStack
from .overlay import stack_of as _do_stack_of
from .promote import promote as _do_promote


class ScenarioRegistry:
    def __init__(self, con):
        self._con = con

    # -- ciclo di vita --------------------------------------------------
    def branch(
        self,
        *,
        name: str,
        base_version_key: int,
        owner: str,
        parent_scenario_id: str | None = None,
        scenario_id: str | None = None,
        created_at: dt.datetime | None = None,
    ) -> Scenario:
        return _do_branch(
            self._con, name=name, base_version_key=base_version_key, owner=owner,
            parent_scenario_id=parent_scenario_id, scenario_id=scenario_id, created_at=created_at,
        )

    def mark_evaluated(self, scenario_id: str) -> Scenario:
        return _do_mark_evaluated(self._con, scenario_id)

    def discard(self, scenario_id: str) -> Scenario:
        return _do_discard(self._con, scenario_id)

    # -- scrittura sparsa -------------------------------------------------
    def set_cell(self, scenario_id: str, cell: CellKey, value: float, *, user: str) -> None:
        _do_set_cell(self._con, scenario_id, cell, value, user=user)

    def increment_cell(self, scenario_id: str, cell: CellKey, delta: float, *, user: str) -> None:
        _do_increment_cell(self._con, scenario_id, cell, delta, user=user)

    def delete_cell(self, scenario_id: str, cell: CellKey, *, user: str) -> None:
        _do_delete_cell(self._con, scenario_id, cell, user=user)

    # -- lettura ------------------------------------------------------------
    def resolve_cell(self, ref: int | str, cell: CellKey) -> ResolvedCell:
        return _do_resolve_cell(self._con, ref, cell)

    def stack_of(self, ref: int | str) -> ScenarioStack:
        """Chiave di isolamento (AC15) per `ref` — vedi `ScenarioStack`."""
        return _do_stack_of(self._con, ref)

    # -- confronto e promozione ---------------------------------------------
    def compare(self, ref_a: int | str, ref_b: int | str) -> list[CompareRow]:
        return _do_compare(self._con, ref_a, ref_b)

    def promote(
        self, scenario_id: str, *, cycle_year: int, cycle_month: int, side: str, status: str, user: str,
    ) -> PromotionResult:
        return _do_promote(
            self._con, scenario_id, cycle_year=cycle_year, cycle_month=cycle_month,
            side=side, status=status, user=user,
        )
