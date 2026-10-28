"""Tipi di dato pubblici del motore: gli edit che `RecalcEngine.recalculate()`
accetta, il risultato che restituisce, e i contatori dell'early cutoff
(AC11).

Granularità delle chiavi di cella (tuple semplici, non dataclass, per essere
direttamente hashable e confrontabili in un test `incrementale == completo`
senza cerimonie):
  - `requested_production` / `confirmed_production` (entrambi nodi sorgente
    del DAG dichiarato, `ibp/semantic/measures.py`, `depends_on=()`):
                                        (product_key, division_key, date_key)
                                        (manufact_key, plant_key, date_key)
  - `derived_manufacturing_demand`:    (manufact_key, date_key)
  - `slots_requested` / `gap_req_conf` / `value_gap`:
                                        (manufact_key, plant_key, date_key)
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RequestedProductionEdit:
    """Un edit sulla misura sorgente del DAG dichiarato (`requested_production`,
    TSOP_DEMAND/REQ_PROD). `new_value` è il valore assoluto della cella dopo
    l'edit (semantica 'set', non un delta) — coerente con la pianificazione
    concorrente: l'utente scrive un numero, non un incremento."""

    product_key: int
    division_key: int
    date_key: int
    new_value: float


@dataclass(frozen=True)
class ConfirmedProductionEdit:
    """Un edit sul secondo nodo sorgente del DAG dichiarato
    (`MEASURE_DAG["confirmed_production"]`, `ibp/semantic/measures.py`,
    `depends_on=()`), che legge da TSOP_OPS (SLOTS_CURRENT_MONTH +
    SLOTS_PREVIOUS_MONTH, la conferma di produzione già frozen sul lato
    supply) e alimenta `gap_req_conf` direttamente, indipendentemente da
    `requested_production`. Il motore lo tratta con la stessa macchina di
    propagazione/cutoff usata per `requested_production`, non con un
    percorso a parte — coerente con l'essere entrambi radici dello stesso
    DAG, non una radice "vera" e una scorciatoia del motore."""

    manufact_key: int
    plant_key: int
    date_key: int
    new_value: float


@dataclass
class CutoffStats:
    """Contatori dell'early cutoff (AC11) per **una** chiamata a
    `recalculate()` o `full_recalculate()`. `visited` conta ogni cella
    esaminata (nodo ricalcolato per verificarne il valore), ripartita in
    **tre** sottoinsiemi disgiunti che sommano esattamente a `visited`:

      - `computed`: lo stato memorizzato è cambiato davvero (valore nuovo,
        valore diverso da quello precedente, o valore rimosso) — sporca i
        dipendenti, se ne ha.
      - `cutoff`: la cella **aveva già un valore** e il ricalcolo produce lo
        stesso valore (entro tolleranza, `_classify_cell`) — l'early cutoff
        propriamente detto (AC11): propagazione interrotta perché l'input
        non è cambiato abbastanza da contare.
      - `absent`: la cella **non aveva alcun valore prima e non ne ha uno
        dopo** — non c'è nulla da tagliare perché non c'era nulla da
        propagare fin da subito (es. `value_gap` senza copertura
        `rate_card`: sparsità della master data, non un edit che si
        ripropaga e trova un aggregato invariato).

    Round critic T3: prima esisteva solo `cutoff`, e in `full_recalculate()`
    **ogni** cella `value_gap` senza `rate_card` (2352 su un DB reale)
    finiva lì — un pannello che leggesse `cutoff` come "risparmio da
    ricalcolo incrementale" avrebbe riportato sparsità di master data come
    se fosse ottimizzazione di propagazione. Le due cose ora hanno contatori
    distinti: `cutoff` è vuoto (`0`) se e solo se nessuna cella esaminata
    aveva già un valore identico; `absent` è vuoto se e solo se ogni cella
    esaminata o ha un valore ora o ne aveva uno prima.

    Un cutoff che non si può misurare è una promessa, non una funzionalità —
    per questo l'invariante `visited == computed + cutoff + absent` è
    verificabile a runtime, non solo a parole, **su entrambi i metodi**."""

    visited: int = 0
    computed: int = 0
    cutoff: int = 0
    absent: int = 0


CellKey = tuple
CellValues = dict[str, dict[CellKey, float]]


@dataclass(frozen=True)
class RecalcResult:
    """`values` è lo stato **completo** e corrente di ogni nodo (non solo le
    celle toccate da questa chiamata): è ciò che rende `incrementale ==
    completo` un confronto diretto fra due `RecalcResult.values` (AC10), non
    un merge che il chiamante deve ricostruire a mano. Chiavi di `values`:
    `requested_production`, `confirmed_production`,
    `derived_manufacturing_demand`, `slots_requested`, `gap_req_conf`,
    `value_gap` — le prime due sono gli input (post-edit), le altre quattro
    il sottografo calcolato dal DAG dichiarato da T2."""

    values: CellValues = field(default_factory=dict)
    stats: CutoffStats = field(default_factory=CutoffStats)
