"""Configurazione minima: percorsi derivati dalla posizione del repository.

Nessun segreto e nessun valore specifico d'ambiente qui — solo path, con la
stessa struttura usata da `db/build_db.py` (`data/ibp.duckdb`,
`data/tmp/`), così `ibp.db` apre sempre lo stesso file che T1 costruisce.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
DB_PATH = DATA_DIR / "ibp.duckdb"
TEMP_DIR = DATA_DIR / "tmp"
