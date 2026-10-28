"""Scenario what-if (A7, schema `scenario.state`).

Stati identici al CHECK di `db/schema.sql`: 'Draft', 'Evaluated',
'Promoted', 'Discarded'. `Evaluated -> Draft` è ammesso (un nuovo edit dopo
la valutazione lo rimette in lavorazione, coerente con l'early-cutoff di
A5); `Promoted` e `Discarded` sono terminali — una volta promosso (T4
materializza una nuova `DVERSIONS`) o scartato, lo scenario non si riapre.

Questo modulo dichiara solo lo stato e la transizione; la meccanica di
branch/delta/promozione è di `ibp.scenario` (T4), che dipende da qui.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from dataclasses import dataclass

from .state_machine import StateMachine, Transitions

SCENARIO_TRANSITIONS: Transitions = {
    "Draft": ("Evaluated", "Discarded"),
    "Evaluated": ("Draft", "Promoted", "Discarded"),
    "Promoted": (),
    "Discarded": (),
}

SCENARIO_STATE = StateMachine("scenario.state", SCENARIO_TRANSITIONS)


@dataclass(frozen=True)
class Scenario:
    """Rispecchia `scenario` (db/schema.sql)."""

    scenario_id: str
    name: str
    base_version_key: int
    base_snapshot_id: str
    parent_scenario_id: str | None
    owner: str
    state: str
    created_at: dt.datetime

    def transition_to(self, new_state: str) -> "Scenario":
        SCENARIO_STATE.validate(self.state, new_state)
        return dataclasses.replace(self, state=new_state)
