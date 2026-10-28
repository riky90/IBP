"""IBP platform — implementazione di riferimento (M1, ACMELIFT).

Questo package (`ibp`) è il codice applicativo che si appoggia al mirror
dEPM + rete produttiva + processo P/R/A/C costruiti da `db/` (T1). T2
introduce dominio, macchine a stati e semantic layer; i task successivi
(T3+) aggiungono motore, scenari, processo, API.

Confine (AC10): nessuna entità ordine/BOM/MRP in questo package — se un
oggetto ha una controparte transazionale in SAP, qui esiste solo come
chiave e attributi di pianificazione.
"""
from __future__ import annotations

__version__ = "0.1.0"
