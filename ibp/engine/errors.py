"""Eccezioni del motore di ricalcolo. Stesso stile di `ibp/domain/errors.py`:
un tipo specifico e riconoscibile invece di un `ValueError` generico o, peggio,
un fallimento silenzioso."""
from __future__ import annotations


class EngineError(Exception):
    """Base per tutte le eccezioni di `ibp.engine`."""


class UnknownCellEditError(EngineError):
    """`recalculate()` accetta solo `RequestedProductionEdit` e
    `ConfirmedProductionEdit` (ibp/engine/cells.py): sono gli unici due punti
    di ingresso di un edit nel DAG dichiarato da T2, uno per ciascuno dei due
    nodi sorgente (`requested_production`, `confirmed_production` —
    `MEASURE_DAG`, `ibp/semantic/measures.py`, entrambi `depends_on=()`).
    Qualunque altro tipo è un errore del chiamante, non un edit da ignorare
    in silenzio."""

    def __init__(self, edit_type: type):
        super().__init__(f"tipo di edit sconosciuto: {edit_type!r}")
        self.edit_type = edit_type
