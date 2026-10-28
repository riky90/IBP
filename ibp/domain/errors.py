"""Eccezioni di dominio. Una transizione illegale deve sollevare un tipo
specifico e riconoscibile, non un `ValueError` generico né, peggio, restare
silenziosa (vedi T2 done_when #1)."""
from __future__ import annotations


class DomainError(Exception):
    """Base per tutte le eccezioni di dominio del package `ibp.domain`."""


class UnknownStateError(DomainError):
    """Lo stato citato non fa parte del dominio dichiarato della macchina a
    stati — tipicamente un refuso o un dato non seedato correttamente."""

    def __init__(self, machine: str, state: str):
        super().__init__(f"{machine}: stato sconosciuto {state!r}")
        self.machine = machine
        self.state = state


class InvalidTransitionError(DomainError):
    """La transizione `from_state -> to_state` non è fra quelle dichiarate
    per la macchina a stati: viene rifiutata, non silenziosamente accettata."""

    def __init__(self, machine: str, from_state: str, to_state: str):
        super().__init__(f"{machine}: transizione illegale {from_state!r} -> {to_state!r}")
        self.machine = machine
        self.from_state = from_state
        self.to_state = to_state


class PhaseClosedError(DomainError):
    """AC4: un tentativo di scrivere su una `cycle_phase` in STAT_03 (chiusa)
    è rifiutato — non è una transizione di stato, è un vincolo di scrittura
    sullo stato corrente."""

    def __init__(self, phase_name: str, stat_state: str):
        super().__init__(
            f"cycle_phase {phase_name!r} è {stat_state} (chiusa): scrittura rifiutata"
        )
        self.phase_name = phase_name
        self.stat_state = stat_state
