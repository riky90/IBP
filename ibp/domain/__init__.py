"""Entità, macchine a stati e value object del dominio IBP (T2).

Confine ERP (AC10): nessuna entità ordine/BOM/MRP vive qui o altrove nel
package `ibp` — se un oggetto ha una controparte transazionale in SAP, in
questo dominio esiste solo come chiave e attributi di pianificazione.

Ogni entità con un ciclo di vita dichiara la propria mappa di transizioni
come dato (vedi `state_machine.StateMachine`) accanto alla propria
dataclass; una transizione non dichiarata solleva `InvalidTransitionError`
(o `UnknownStateError` se lo stato stesso non esiste), mai un fallimento
silenzioso.
"""
from __future__ import annotations

from .cycle import (
    CYCLE_PHASE_STAT_MACHINE,
    Cycle,
    CyclePhase,
    PhaseDef,
    build_phase_sequence_machine,
)
from .errors import DomainError, InvalidTransitionError, PhaseClosedError, UnknownStateError
from .gap import GAP_STATUS, Gap
from .portfolio_item import PORTFOLIO_ITEM_LIFECYCLE, PortfolioItem
from .project import PROJECT_STATE, Project
from .review import REVIEW_STATUS, ReviewInstance
from .scenario import SCENARIO_STATE, Scenario
from .state_machine import StateMachine, Transitions

__all__ = [
    "DomainError",
    "InvalidTransitionError",
    "UnknownStateError",
    "PhaseClosedError",
    "StateMachine",
    "Transitions",
    "PortfolioItem",
    "PORTFOLIO_ITEM_LIFECYCLE",
    "Project",
    "PROJECT_STATE",
    "Gap",
    "GAP_STATUS",
    "Scenario",
    "SCENARIO_STATE",
    "ReviewInstance",
    "REVIEW_STATUS",
    "Cycle",
    "CyclePhase",
    "PhaseDef",
    "CYCLE_PHASE_STAT_MACHINE",
    "build_phase_sequence_machine",
]
