"""Portfolio item lifecycle (D2/A9, schema `portfolio_item.lifecycle_state`).

Stati e transizioni identici a quelli seedati da `db/seed/process.py` /
vincolati dal CHECK di `db/schema.sql`: 'Concept', 'Development', 'Launch',
'Mature', 'Decline', 'Retired'. Un item di portfolio può essere ritirato da
qualunque stato non terminale (`Retire` è uno dei quattro
`portfolio_decision.decision_type`), ma non può saltare stadi in avanti né
tornare indietro: il ciclo di vita è quello standard NPI/phase-out.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from .state_machine import StateMachine, Transitions

LIFECYCLE_TRANSITIONS: Transitions = {
    "Concept": ("Development", "Retired"),
    "Development": ("Launch", "Retired"),
    "Launch": ("Mature", "Retired"),
    "Mature": ("Decline", "Retired"),
    "Decline": ("Retired",),
    "Retired": (),
}

PORTFOLIO_ITEM_LIFECYCLE = StateMachine("portfolio_item.lifecycle_state", LIFECYCLE_TRANSITIONS)


@dataclass(frozen=True)
class PortfolioItem:
    """Rispecchia `portfolio_item` (db/schema.sql). `product_key` è NULL
    pre-lancio (nessun planning model ancora emesso in `item`)."""

    item_id: int
    product_key: int | None
    name: str
    lifecycle_state: str

    def transition_to(self, new_state: str) -> "PortfolioItem":
        """Ritorna una nuova istanza nello stato richiesto, o solleva
        `InvalidTransitionError`/`UnknownStateError` (vedi `domain.errors`)."""
        PORTFOLIO_ITEM_LIFECYCLE.validate(self.lifecycle_state, new_state)
        return dataclasses.replace(self, lifecycle_state=new_state)
