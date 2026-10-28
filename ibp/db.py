"""Unico punto di apertura di connessioni DuckDB nel package `ibp` (T2
done_when #5): ogni altro modulo riceve una connessione, nessuno la apre.

Riproduce le impostazioni offline di `db/build_db.py` (AC25): senza
`autoinstall_known_extensions=false` / `autoload_known_extensions=false` il
primo uso di un'extension proverebbe a scaricarla da internet e romperebbe
la demo offline; `temp_directory` esplicito evita che DuckDB scelga una
directory di sistema meno prevedibile su Windows (vedi README.md, gotcha A6).
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import duckdb

from . import config


def connect(db_path: str | None = None, *, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Apre una connessione a `data/ibp.duckdb` (o al path esplicito passato).

    `read_only=True` va usato da chi legge soltanto: DuckDB è single-writer
    con lock di processo (README.md), quindi più lettori read-only possono
    coesistere ma un solo scrittore alla volta.
    """
    path = db_path or str(config.DB_PATH)
    config.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(
        path,
        read_only=read_only,
        config={
            "autoinstall_known_extensions": "false",
            "autoload_known_extensions": "false",
            "temp_directory": str(config.TEMP_DIR),
        },
    )


@contextmanager
def session(db_path: str | None = None, *, read_only: bool = False) -> Iterator[duckdb.DuckDBPyConnection]:
    """Context manager di comodo: apre, cede, chiude sempre la connessione."""
    con = connect(db_path, read_only=read_only)
    try:
        yield con
    finally:
        con.close()
