"""Review instance (A9, tabella `review_instance`).

`review_instance.status` non ha un CHECK nello schema (è VARCHAR libero),
ma il seed (`db/seed/process.py`, `_review_status`) scrive solo
'Scheduled', 'InProgress', 'Closed' — sono questi gli stati che questa
macchina dichiara. Le transizioni seguono l'avanzamento del calendario
della fase (day_start/day_end letti da `process_phases.json`): si può
saltare direttamente a `Closed` da `Scheduled` (una review non presidiata
si chiude comunque al giorno di fine fase), ma non si torna indietro.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from .state_machine import StateMachine, Transitions

REVIEW_STATUS_TRANSITIONS: Transitions = {
    "Scheduled": ("InProgress", "Closed"),
    "InProgress": ("Closed",),
    "Closed": (),
}

REVIEW_STATUS = StateMachine("review_instance.status", REVIEW_STATUS_TRANSITIONS)


@dataclass(frozen=True)
class ReviewInstance:
    """Rispecchia `review_instance` (db/schema.sql). `review_type` è vincolato
    dal CHECK dello schema ('Portfolio', 'Demand', 'GlobalDemandValidation',
    'Supply', 'IntegratedReconciliation', 'MBR'); qui non lo ridichiariamo
    per non duplicare il vincolo altrove."""

    review_id: int
    cycle_id: int
    review_type: str
    day_start: int
    day_end: int
    status: str
    gate: str | None

    def transition_to(self, new_state: str) -> "ReviewInstance":
        REVIEW_STATUS.validate(self.status, new_state)
        return dataclasses.replace(self, status=new_state)
