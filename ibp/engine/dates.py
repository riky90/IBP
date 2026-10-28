"""Aritmetica sui `date_key` (INTEGER, formato `YYYYMM` — vedi `DIM_DATE` in
db/schema.sql). Nessuna dipendenza da `db/seed/common.py` (fuori da `ibp`,
strumento di build): stessa formula (`year * 100 + month`), reimplementata
qui perché il motore deve restare autosufficiente dentro il package.

Nota su AC2: `100` e `12` qui non sono soglie di capacità (max slot,
granularità, layout) — sono la codifica del calendario (`YYYYMM`, 12 mesi
l'anno), la stessa distinzione che README.md fa esplicitamente per
`encoding="utf-8"`.
"""
from __future__ import annotations

import datetime as dt


def shift_date_key(date_key: int, months: int) -> int:
    """`date_key` spostato di `months` mesi (positivo = avanti, negativo =
    indietro), restando in formato YYYYMM."""
    year, month = divmod(date_key, 100)
    idx = year * 12 + (month - 1) + months
    new_year, new_month = idx // 12, idx % 12 + 1
    return new_year * 100 + new_month


def date_key_to_date(date_key: int) -> dt.date:
    """Primo giorno del mese rappresentato da `date_key` — coerente con
    `DIM_DATE.date` (db/schema.sql)."""
    year, month = divmod(date_key, 100)
    return dt.date(year, month, 1)
