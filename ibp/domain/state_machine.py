"""Macchina a stati generica: le transizioni valide sono dichiarate come
dato (`Mapping[str, tuple[str, ...]]`), non codificate in `if`/`elif` sparsi
per il dominio. Ogni entità di `ibp.domain` dichiara la propria mappa di
transizioni accanto alla propria dataclass e la usa attraverso questa
classe — vedi `portfolio_item.py`, `project.py`, `gap.py`, `scenario.py`,
`cycle.py`, `review.py`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .errors import InvalidTransitionError, UnknownStateError

Transitions = Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class StateMachine:
    """`name` è solo per messaggi d'errore leggibili (es.
    `"portfolio_item.lifecycle_state"`). `transitions` mappa ogni stato
    dichiarato alla tupla di stati raggiungibili da lì; uno stato terminale
    ha tupla vuota."""

    name: str
    transitions: Transitions

    @property
    def states(self) -> frozenset[str]:
        return frozenset(self.transitions)

    def allowed_from(self, state: str) -> tuple[str, ...]:
        """Stati raggiungibili da `state`. Solleva `UnknownStateError` se
        `state` non è fra quelli dichiarati — a differenza di una transizione
        illegale, qui il dato di partenza stesso non è valido."""
        try:
            return self.transitions[state]
        except KeyError:
            raise UnknownStateError(self.name, state) from None

    def validate(self, from_state: str, to_state: str) -> None:
        """Solleva `UnknownStateError` se uno dei due stati non è dichiarato,
        `InvalidTransitionError` se la coppia non è una transizione
        ammessa. Non ritorna nulla: è una guardia, non una query."""
        if to_state not in self.states:
            raise UnknownStateError(self.name, to_state)
        if to_state not in self.allowed_from(from_state):
            raise InvalidTransitionError(self.name, from_state, to_state)

    def transition(self, from_state: str, to_state: str) -> str:
        """Valida e ritorna `to_state` — comodo per un one-liner in chi
        assegna il nuovo stato dopo la validazione."""
        self.validate(from_state, to_state)
        return to_state
