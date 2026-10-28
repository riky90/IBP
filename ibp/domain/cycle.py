"""Ciclo e fase (A9, tabelle `cycle` e `cycle_phase`).

Due macchine a stati distinte, entrambe richieste dal task:

1. `CYCLE_PHASE_STAT_MACHINE` — la progressione STAT_01 -> STAT_02 -> STAT_03
   di una singola fase. È dichiarata come costante perché gli stati
   `stat_state` sono un CHECK chiuso in `db/schema.sql` (non cambiano
   aggiungendo dato), a differenza dei nomi di fase sotto.
2. la state machine dell'ordine delle fasi (`cycle.current_phase`), che
   invece **non** è una costante Python: la costruiamo da
   `SemanticRegistry.cycle_phases(cycle_id)`, cioè dalle righe
   `cycle_phase` effettivamente seedate (ordinate per `phase_no`), lette da
   `db/seed/data/process_phases.json` a monte. Aggiungere/riordinare una
   fase resta un cambio di dato (master data + seed), non di codice Python
   — stesso principio AC2 applicato al processo invece che a `DPLANT`.

`CyclePhase.assert_writable()` è il punto AC4: un tentativo di scrivere su
una fase STAT_03 è rifiutato con `PhaseClosedError`, non con una transizione
di stato (non è "andare da uno stato all'altro", è un vincolo sullo stato
corrente).
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Sequence

from .errors import PhaseClosedError
from .state_machine import StateMachine, Transitions

STAT_TRANSITIONS: Transitions = {
    "STAT_01": ("STAT_02",),
    "STAT_02": ("STAT_03",),
    "STAT_03": (),
}

CYCLE_PHASE_STAT_MACHINE = StateMachine("cycle_phase.stat_state", STAT_TRANSITIONS)


@dataclass(frozen=True)
class PhaseDef:
    """Una riga `cycle_phase` così come letta dal DB (day range, stat_state,
    gate — mai literal in Python, vedi README.md AC2)."""

    phase_id: int
    cycle_id: int
    phase_no: int
    name: str
    day_start: int
    day_end: int
    stat_state: str
    gate: str | None


@dataclass(frozen=True)
class CyclePhase:
    """Value object di dominio su `PhaseDef`, con la guardia di scrittura e
    l'avanzamento di `stat_state`."""

    phase_id: int
    cycle_id: int
    phase_no: int
    name: str
    day_start: int
    day_end: int
    stat_state: str
    gate: str | None

    @classmethod
    def from_def(cls, d: PhaseDef) -> "CyclePhase":
        return cls(**dataclasses.asdict(d))

    def assert_writable(self) -> None:
        """AC4: solleva `PhaseClosedError` se la fase è STAT_03."""
        if self.stat_state == "STAT_03":
            raise PhaseClosedError(self.name, self.stat_state)

    def advance_stat(self) -> "CyclePhase":
        """Avanza allo stat_state successivo dichiarato in
        `CYCLE_PHASE_STAT_MACHINE`. Solleva `PhaseClosedError` se la fase è
        già STAT_03 (nessuno stato successivo possibile)."""
        allowed = CYCLE_PHASE_STAT_MACHINE.allowed_from(self.stat_state)
        if not allowed:
            raise PhaseClosedError(self.name, self.stat_state)
        return dataclasses.replace(self, stat_state=allowed[0])


def build_phase_sequence_machine(phases: Sequence[PhaseDef]) -> StateMachine:
    """Costruisce la state machine di `cycle.current_phase` dalle righe
    `cycle_phase` di un ciclo, ordinate per `phase_no`: `phase[i]` può
    transitare solo a `phase[i + 1]`, l'ultima fase è terminale. Nessun nome
    di fase è hardcoded qui — vengono dal dato passato dal chiamante
    (`ibp.semantic.SemanticRegistry.cycle_phases`), che a sua volta li legge
    dal DB seedato da `process_phases.json`."""
    ordered = sorted(phases, key=lambda p: p.phase_no)
    transitions: dict[str, tuple[str, ...]] = {}
    for i, p in enumerate(ordered):
        nxt = (ordered[i + 1].name,) if i + 1 < len(ordered) else ()
        # Più fasi con lo stesso nome (impossibile su un singolo ciclo, ma la
        # funzione è generica) unificano le transizioni osservate invece di
        # sovrascriversi silenziosamente.
        transitions[p.name] = tuple(set(transitions.get(p.name, ())) | set(nxt))
    return StateMachine("cycle.current_phase", transitions)


@dataclass(frozen=True)
class Cycle:
    """Rispecchia `cycle` (db/schema.sql)."""

    cycle_id: int
    cycle_year: int
    cycle_month: int
    name: str
    current_phase: str

    def transition_phase(self, to_phase: str, machine: StateMachine) -> "Cycle":
        """`machine` va costruita per questo `cycle_id` (vedi
        `build_phase_sequence_machine`) e passata esplicitamente: il ciclo
        stesso non conosce le proprie fasi, le riceve da chi ha già
        interrogato il DB — coerente con "ibp.db è l'unico punto di
        accesso a DuckDB"."""
        machine.validate(self.current_phase, to_phase)
        return dataclasses.replace(self, current_phase=to_phase)
