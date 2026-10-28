"""Generatori del seed sintetico ma isomorfo (F4) per il DB IBP.

Ogni modulo espone funzioni `build_*(...)` che ritornano `polars.DataFrame`
pronti per l'inserimento; nessuna funzione qui si connette a DuckDB — questo
tiene i generatori testabili in isolamento e il build deterministico
(`db/build_db.py` orchestra ordine di caricamento e RNG seed).
"""
