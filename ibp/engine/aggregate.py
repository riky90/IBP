"""Combinazione di un gruppo di valori secondo `agg_method` (A5, AC12).

La trappola che A5 nomina esplicitamente: "*delta-update solo sum/count.
Min/max/ratio/media pesata sono non invertibili -> ricalcolo sul gruppo*".
Un delta-update di un max è sbagliato nel momento esatto in cui il valore
che cambia (in calo) era il max precedente — l'errore è silenzioso perché il
nuovo max "sembra" ancora valido finché qualcuno non lo confronta col
ricalcolo pieno. Questo modulo esiste per non poter sbagliare quella
distinzione per disattenzione: `combine()` ricalcola sempre sul gruppo
intero (non mantiene stato fra chiamate), e `is_delta_safe()` è la sola
funzione che dichiara quali `agg_method` **potrebbero** in linea di
principio essere aggiornati per delta — nessun chiamante di questo modulo lo
fa comunque (vedi `engine.py`: ogni cella si ricalcola sempre per intero dal
suo stato corrente), ma la distinzione resta esposta perché un'ottimizzazione
futura (T7/T10) la deve poter interrogare invece di re-inventarla.
"""
from __future__ import annotations

from collections.abc import Sequence

# agg_method che *in linea di principio* si potrebbero aggiornare per delta
# (sum: aggiungere il delta; count: aggiungere 1/-1). Min/max/avg/ratio no:
# richiedono il gruppo intero (A5). Dichiarato come dato, non un `if` sparso.
_DELTA_SAFE_AGG_METHODS = frozenset({"sum", "count"})


def is_delta_safe(agg_method: str) -> bool:
    return agg_method in _DELTA_SAFE_AGG_METHODS


def combine(agg_method: str, values: Sequence[float]) -> float:
    """Ricalcola `agg_method` sull'intero gruppo `values` (mai un
    aggiornamento incrementale rispetto a un valore precedente — AC12).
    Solleva `ValueError` su gruppo vuoto o `agg_method` sconosciuto: un
    gruppo vuoto silenziosamente ridotto a `0.0` nasconderebbe "nessun dato"
    dietro un valore che sembra un dato vero."""
    if not values:
        raise ValueError("combine: gruppo vuoto, nessun valore da aggregare")
    if agg_method == "sum":
        return float(sum(values))
    if agg_method == "count":
        return float(len(values))
    if agg_method == "min":
        return float(min(values))
    if agg_method == "max":
        return float(max(values))
    if agg_method == "avg":
        return float(sum(values)) / len(values)
    raise ValueError(
        f"agg_method {agg_method!r} non gestito da combine() "
        "(per 'ratio' vedi combine_ratio: un rapporto non si riduce da una "
        "sola lista di valori, servono numeratore e denominatore)"
    )


def combine_ratio(pairs: Sequence[tuple[float, float]]) -> float:
    """Ricalcola una misura `ratio` (es. `CAPACITY_UTIL`, `ORDER_COVERAGE`)
    come somma dei numeratori sulla somma dei denominatori dell'intero
    gruppo — mai un rapporto di rapporti, e mai aggiornato per delta (AC12).
    `0.0` se il denominatore aggregato è zero: un gruppo senza capacità
    disponibile ha un ratio dichiaratamente nullo, non un `ZeroDivisionError`
    che il chiamante deve prevedere caso per caso."""
    if not pairs:
        raise ValueError("combine_ratio: gruppo vuoto, nessuna coppia da aggregare")
    numerator = sum(n for n, _ in pairs)
    denominator = sum(d for _, d in pairs)
    if denominator == 0:
        return 0.0
    return float(numerator) / float(denominator)
