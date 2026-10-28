"""Costanti e helper condivisi dai generatori di seed.

Un solo seed RNG (SEED) per l'intero build: rigenerare produce sempre la
stessa forma dei dati (idempotenza "a livello di contenuto", non di byte del
file DuckDB — vedi db/build_db.py).
"""
from __future__ import annotations

import hashlib
import random

# Solo stdlib: db/build_db.py deve girare con le sole dipendenze dichiarate in
# pyproject.toml (duckdb + polars + pyarrow bastano per il seed); numpy non è
# nell'elenco fissato da T1 e non viene introdotto qui per una comodità locale.
SEED = 42

# Finestra dimensionale (DIM_DATE, DVERSIONS). "Oggi" nel run è 2026-09.
CURRENT_CYCLE_YEAR = 2026
CURRENT_CYCLE_MONTH = 9
CURRENT_CYCLE_DAY = 10

DIM_DATE_START = (2019, 1)
DIM_DATE_END = (2028, 12)

# 114 cicli mensili (2019-01..2028-06) -> 456 versioni P/R/A/C + 10 SOP_BP -> 466,
# isomorfo al ~466 del vault. Vedi docs/01-plan-m1.md "Cosa dice il vault".
CYCLE_START = (2019, 1)
CYCLE_END = (2028, 6)
BUDGET_YEARS = list(range(2019, 2029))

# Finestra di popolamento per fatti/capacità/forecast: mesi indietro/avanti
# rispetto al ciclo corrente. Tenuta deliberatamente stretta (vedi A6: il
# vincolo è la latenza, non il volume — il seed non deve materializzare il
# cubo denso 1.700x52x24 per ogni versione storica).
CAPACITY_WINDOW_MONTHS_BACK = 11
CAPACITY_WINDOW_MONTHS_FWD = 15

CURRENT_CYCLE = (CURRENT_CYCLE_YEAR, CURRENT_CYCLE_MONTH)
HIST_CYCLE_COUNT = 4  # >= 4 cicli storici completi richiesti dal piano


def recent_closed_cycles(count: int = HIST_CYCLE_COUNT) -> list[tuple[int, int]]:
    """Gli ultimi `count` cicli mensili precedenti il ciclo corrente (chiusi:
    tutte e quattro le fasi P/R/A/C sono realizzate)."""
    return [month_add(CURRENT_CYCLE_YEAR, CURRENT_CYCLE_MONTH, -d) for d in range(count, 0, -1)]

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

REGIONS = ["APAC", "CIS", "EMEA", "LATAM", "NAM"]


def new_rng(stream: str) -> random.Random:
    """RNG deterministico ma indipendente per generatore (evita che l'ordine
    di chiamata tra moduli cambi i numeri estratti da un altro modulo).

    Usa hashlib, non l'`hash()` builtin: l'hash di stringa di Python è
    salato per processo (sicurezza) e cambierebbe la seed ad ogni run,
    rompendo l'idempotenza fra un `python db/build_db.py` e il successivo."""
    digest = hashlib.sha256(f"{SEED}:{stream}".encode("ascii")).hexdigest()
    return random.Random(int(digest[:16], 16))


def date_key(year: int, month: int) -> int:
    return year * 100 + month


def month_add(year: int, month: int, delta: int) -> tuple[int, int]:
    idx = (year * 12 + (month - 1)) + delta
    return idx // 12, idx % 12 + 1


def month_range(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
    """Range inclusivo di (year, month), in ordine cronologico."""
    sy, sm = start
    ey, em = end
    start_idx = sy * 12 + (sm - 1)
    end_idx = ey * 12 + (em - 1)
    out = []
    for idx in range(start_idx, end_idx + 1):
        out.append((idx // 12, idx % 12 + 1))
    return out


def apportion(total: int, weights: list[float]) -> list[int]:
    """Ripartisce `total` unità intere secondo `weights`, metodo dei resti
    più alti: la somma dei risultati è sempre esattamente `total`."""
    total_weight = sum(weights)
    raw = [w / total_weight * total for w in weights]
    floors = [int(r) for r in raw]  # troncamento verso zero, pesi >= 0
    remainder = int(total - sum(floors))
    frac = [r - f for r, f in zip(raw, floors)]
    order = sorted(range(len(weights)), key=lambda i: frac[i], reverse=True)
    for i in order[:remainder]:
        floors[i] += 1
    return floors
