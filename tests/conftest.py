"""Fixture condivise per i test di T2 (dominio + semantic layer).

Tutti i test che leggono dati reali richiedono `data/ibp.duckdb` (prodotto
da `python db/build_db.py`, T1). Se il file non esiste, i test che ne
dipendono sono skippati con un motivo esplicito — non passano in silenzio.

Distinzione fra "checkout pulito" (T1 non ancora eseguito: `data/` non
esiste o è vuota, gitignored) e "repo costruito ma DB assente" (`data/`
esiste e contiene qualcosa, es. `data/tmp/` creato da `db/build_db.py`
prima di fallire, o il file `.duckdb` cancellato a mano dopo un build
riuscito): solo il primo caso è uno skip legittimo. Il secondo è un
sintomo di build T1 fallito o rotto e deve far fallire la suite — uno
skip qui farebbe leggere un build rotto come verde.
"""
from __future__ import annotations

import shutil

import pytest

from ibp import config
from ibp import db as ibp_db
from ibp.semantic.registry import SemanticRegistry

from _engine_support import DEMAND_VERSION_KEY, OPS_VERSION_KEY, clone_engine

DB_MISSING_REASON = (
    f"data/ibp.duckdb non trovato ({config.DB_PATH}); "
    "eseguire `python db/build_db.py` (T1) prima di questi test."
)


def _require_db() -> None:
    if config.DB_PATH.exists():
        return
    data_dir = config.DB_PATH.parent
    if data_dir.exists() and any(data_dir.iterdir()):
        contents = sorted(p.name for p in data_dir.iterdir())
        pytest.fail(
            f"data/ibp.duckdb assente ma {data_dir} esiste e non è vuota "
            f"(contiene: {contents}): non è un checkout pulito, sembra un "
            "build T1 fallito a metà o un file .duckdb cancellato dopo un "
            "build riuscito. Eseguire `python db/build_db.py` e verificarne "
            "l'esito prima di rilanciare i test — uno skip qui "
            "nasconderebbe un build rotto."
        )
    pytest.skip(DB_MISSING_REASON)


@pytest.fixture(scope="session")
def db_available() -> None:
    _require_db()


@pytest.fixture()
def con(db_available):
    """Connessione read-only al DB reale: non muta mai il file su disco."""
    with ibp_db.session(read_only=True) as connection:
        yield connection


@pytest.fixture()
def registry(con):
    return SemanticRegistry(con)


@pytest.fixture()
def writable_db_copy(db_available, tmp_path):
    """Copia scrivibile del DB reale in una directory temporanea (per test
    che devono mutare dato, es. AC2 — aggiungere un plant). Non tocca mai
    `data/ibp.duckdb`."""
    copy_path = tmp_path / "ibp_copy.duckdb"
    shutil.copy2(config.DB_PATH, copy_path)
    con = ibp_db.connect(str(copy_path))
    try:
        yield con
    finally:
        con.close()


@pytest.fixture()
def registry_copy(writable_db_copy):
    """`SemanticRegistry` sulla copia scrivibile: comodo per i test che
    devono mutare `item_link`/`DPLANT` e poi interrogare via registry."""
    return SemanticRegistry(writable_db_copy)


# ---------------------------------------------------------------------------
# ibp/engine/ (T3) — costruire un RecalcEngine sul DB reale carica per
# intero TSOP_DEMAND e fa un full_recalculate() nel costruttore: decine di
# secondi (query + risoluzione item_link per ogni (product_key, date_key)
# scoperto). Costruirlo una volta per sessione, poi clonarne lo stato
# mutabile (vedi _engine_support.clone_engine) per ogni test che deve
# editarlo, è ciò che rende la suite eseguibile in tempi ragionevoli invece
# di pagare quel costo per ogni singolo test.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def engine_con(db_available):
    """Connessione dedicata, di durata sessione, per il `RecalcEngine`
    riscaldato — separata dalla `con` per-test (function-scoped) usata dal
    resto della suite. Read-only: il motore non scrive mai facts (vedi
    ibp/engine/engine.py)."""
    with ibp_db.session(read_only=True) as connection:
        yield connection


@pytest.fixture(scope="session")
def warm_engine(engine_con):
    """Un `RecalcEngine` costruito una sola volta per l'intera sessione di
    test, su `DEMAND_VERSION_KEY`/`OPS_VERSION_KEY` (vedi
    `_engine_support.py` per il perché di questa coppia). Non va mai mutato
    direttamente da un test: usare la fixture `engine`, che ne clona lo
    stato."""
    from ibp.engine import RecalcEngine

    return RecalcEngine(engine_con, demand_version_key=DEMAND_VERSION_KEY, ops_version_key=OPS_VERSION_KEY)


@pytest.fixture()
def engine(warm_engine):
    """Copia indipendente e economica di `warm_engine` (vedi
    `_engine_support.clone_engine`): ogni test la può mutare via
    `.recalculate()` senza influenzare gli altri test, senza ripagare il
    costo di costruzione."""
    return clone_engine(warm_engine)
