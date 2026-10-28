"""Scenari (T4): branch, overlay sparso con tombstone esplicito, confronto
(`compare`) fra versioni e scenari indifferentemente, promozione a nuova
istanza `DVERSIONS`.

Contratto: ogni funzione qui riceve una connessione DuckDB (`ibp.db` è
l'unico punto che la apre, T2 done_when #5) — nessuna funzione di questo
package ne apre una propria. Nessuna dipendenza da `ibp.engine` (T3, in
sviluppo concorrente): dove servirebbe ricalcolare, questo package espone
solo il seam (`mark_evaluated`) — la valutazione resta compito del motore.

Punto d'ingresso comodo: `ScenarioRegistry(con)` (stesso pattern di
`ibp.semantic.registry.SemanticRegistry`). Le funzioni pure dei singoli
moduli (`branch`, `edits`, `compare`, `promote`, `overlay`) restano
importabili direttamente.
"""
from __future__ import annotations

from .branch import branch, discard, mark_evaluated
from .compare import compare
from .edits import delete_cell, increment_cell, resolve_cell, set_cell
from .errors import (
    CellVersionMismatchError,
    DuplicateVersionError,
    InvalidCellKeyError,
    MismatchedBaseVersionError,
    NonAdditiveMeasureError,
    PromotionConflictError,
    ScenarioError,
    ScenarioWriteRejectedError,
    SideMismatchError,
    UnknownMeasureError,
    UnknownScenarioError,
    UnknownVersionError,
    UnmaterializableCellError,
)
from .models import CellKey, CompareRow, PromotionResult, ResolvedCell, Scenario, ScenarioStack
from .overlay import stack_of
from .promote import promote
from .registry import ScenarioRegistry

__all__ = [
    "ScenarioRegistry",
    # ciclo di vita
    "branch",
    "mark_evaluated",
    "discard",
    # scrittura sparsa
    "set_cell",
    "increment_cell",
    "delete_cell",
    # lettura / confronto / promozione
    "resolve_cell",
    "stack_of",
    "compare",
    "promote",
    # valori di dominio
    "Scenario",
    "CellKey",
    "ResolvedCell",
    "CompareRow",
    "ScenarioStack",
    "PromotionResult",
    # eccezioni
    "ScenarioError",
    "UnknownVersionError",
    "UnknownScenarioError",
    "UnknownMeasureError",
    "InvalidCellKeyError",
    "NonAdditiveMeasureError",
    "MismatchedBaseVersionError",
    "CellVersionMismatchError",
    "SideMismatchError",
    "ScenarioWriteRejectedError",
    "DuplicateVersionError",
    "PromotionConflictError",
    "UnmaterializableCellError",
]
