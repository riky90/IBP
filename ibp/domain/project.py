"""Project Master Plan (D2/A9, schema `project.state`).

Stati identici al CHECK di `db/schema.sql`: 'Proposed', 'Assessed',
'Resourced', 'Approved', 'InExecution', 'Closed'. `Resourced` è lo stadio in
cui esiste almeno una riga di `project_resource_demand` (è ciò che rende il
piano "risorsato", non un attributo separato — vedi README/D2). Come per il
portfolio item, `Closed` è raggiungibile da ogni stadio non terminale
(`Retire`/`Defer` su un progetto già proposto non devono attraversare tutti
gli stadi intermedi), ma non si torna indietro né si salta in avanti oltre
`Closed`.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from dataclasses import dataclass

from .state_machine import StateMachine, Transitions

PROJECT_TRANSITIONS: Transitions = {
    "Proposed": ("Assessed", "Closed"),
    "Assessed": ("Resourced", "Closed"),
    "Resourced": ("Approved", "Closed"),
    "Approved": ("InExecution", "Closed"),
    "InExecution": ("Closed",),
    "Closed": (),
}

PROJECT_STATE = StateMachine("project.state", PROJECT_TRANSITIONS)


@dataclass(frozen=True)
class Project:
    """Rispecchia `project` (db/schema.sql)."""

    project_id: int
    portfolio_item_id: int
    name: str
    state: str
    target_launch_date: dt.date | None = None

    def transition_to(self, new_state: str) -> "Project":
        PROJECT_STATE.validate(self.state, new_state)
        return dataclasses.replace(self, state=new_state)
