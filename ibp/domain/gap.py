"""Gap dell'Integrated Reconciliation (D2/A9, schema `gap.status`).

Stati identici al CHECK di `db/schema.sql`: 'Open', 'Proposed', 'Filtered',
'Escalated', 'Closed'. La pipeline descritta in `docs/01-plan-m1.md` (D2) è
`Open -> Proposed -> Filtered -> Escalated -> Closed`, ma un gap urgente può
essere escalato direttamente da `Open`/`Proposed` (non ogni gap passa per un
filtro), e `Closed` è raggiungibile da qualunque stato non terminale: una
decisione può chiudere il gap prima che finisca l'intera pipeline.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from .state_machine import StateMachine, Transitions

GAP_TRANSITIONS: Transitions = {
    "Open": ("Proposed", "Escalated", "Closed"),
    "Proposed": ("Filtered", "Escalated", "Closed"),
    "Filtered": ("Escalated", "Closed"),
    "Escalated": ("Closed",),
    "Closed": (),
}

GAP_STATUS = StateMachine("gap.status", GAP_TRANSITIONS)


@dataclass(frozen=True)
class Gap:
    """Rispecchia `gap` (db/schema.sql). `dimension_slice_json` resta una
    stringa JSON grezza: non è compito di T2 definirne lo schema interno."""

    gap_id: int
    cycle_id: int
    scope: str
    dimension_slice_json: str
    measure_key: int | None
    plan_value: float
    target_value: float
    delta_units: float
    delta_value: float
    owner: str
    category: str
    status: str

    def transition_to(self, new_state: str) -> "Gap":
        GAP_STATUS.validate(self.status, new_state)
        return dataclasses.replace(self, status=new_state)
