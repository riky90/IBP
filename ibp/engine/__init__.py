"""Motore di ricalcolo (T3): esegue il DAG dichiarato da
`ibp.semantic.measures` (`ibp/semantic/measures.py` dichiara, non calcola —
vedi il suo docstring di modulo). Punto d'ingresso: `RecalcEngine`, costruita
su una connessione DuckDB del chiamante (mai aperta qui, coerente con
`ibp/db.py`) e una coppia di versioni (demand/ops).

    from ibp import db
    from ibp.engine import RecalcEngine, RequestedProductionEdit

    with db.session(read_only=True) as con:
        engine = RecalcEngine(con, demand_version_key=..., ops_version_key=...)
        result = engine.recalculate([
            RequestedProductionEdit(product_key=1, division_key=2, date_key=202610, new_value=120.0),
        ])
        result.values["value_gap"]   # stato completo e corrente del nodo
        result.stats.visited/.computed/.cutoff   # AC11

Vedi `ibp/engine/engine.py` per la semantica completa (AC10/AC11/AC12) e le
scelte di dominio (sito di produzione per lo spread slot, sparsità di
`rate_card`, ecc.).
"""
from __future__ import annotations

from .cells import (
    CellKey,
    CellValues,
    ConfirmedProductionEdit,
    CutoffStats,
    RecalcResult,
    RequestedProductionEdit,
)
from .engine import CellEdit, RecalcEngine
from .errors import EngineError, UnknownCellEditError

__all__ = [
    "RecalcEngine",
    "CellEdit",
    "RequestedProductionEdit",
    "ConfirmedProductionEdit",
    "RecalcResult",
    "CutoffStats",
    "CellKey",
    "CellValues",
    "EngineError",
    "UnknownCellEditError",
]
