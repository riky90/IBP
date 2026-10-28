# Technology Stack

**Analysis Date:** 2026-09-19

## Languages

**Primary:**
- Python 3.11+ (dichiarato in `pyproject.toml`, `requires-python = ">=3.11"`) — sviluppato e verificato su Python 3.13, Windows. Tutto il codice applicativo (`ibp/`, `db/`, `tests/`).

**Secondary:**
- SQL (DuckDB dialect) — `db/schema.sql` (DDL completo: mirror dEPM, rete produttiva, scenari, forecast, processo).
- JSON — master data letto dal codice, non literal Python: `db/seed/data/plant_master.json`, `db/seed/data/process_phases.json` (vedi AC2 in `README.md`).

## Runtime

**Environment:**
- CPython 3.11+ (verificato su 3.13). Nessun runtime alternativo (no PyPy).
- Piattaforma di sviluppo primaria: Windows (i "Gotcha Windows" in `README.md` sono espliciti e vincolanti: temp_directory, Defender, lock DuckDB, segfault OpenMP).

**Package Manager:**
- pip, con installazione in modalità editable: `pip install -e .`
- Build backend: `setuptools>=68` (`[build-system]` in `pyproject.toml`, `build-backend = "setuptools.build_meta"`).
- Package discovery: `[tool.setuptools.packages.find]` con `include = ["ibp*"]` — solo il package `ibp` viene distribuito, `db/` e `tests/` restano fuori dal wheel.
- Lockfile: assente. Le versioni sono pinnate direttamente in `pyproject.toml` con `==` esatto (nessun range), che funge da pin de facto. Non esiste `requirements.txt` né `poetry.lock`/`uv.lock`.

## Frameworks

**Core (dipendenze base, M1–M3, dichiarate una sola volta in `pyproject.toml`):**
- `duckdb==1.1.3` — unico datastore, file singolo locale (`data/ibp.duckdb`, gitignored).
- `polars==1.9.0` — costruzione DataFrame per il seed sintetico e caricamento bulk nello schema (`db/seed/*.py`, `db/build_db.py`).
- `pyarrow==18.1.0` — usato da `db/seed/common.py` come backend Arrow per l'interscambio con DuckDB/Polars.
- `python-dateutil==2.9.0.post0` — calcoli di calendario nel seed e nell'engine.
- `openpyxl==3.1.5` — dichiarato in base ma non ancora usato nel codice sorgente attuale (T1–T4); riservato per un task successivo che leggerà/scriverà file Excel (vedi "Cosa NON è ancora qui" in `README.md` e il rischio "Excel che scrive sul database" in `docs/01-plan-m1.md`).
- `fastapi==0.115.0`, `uvicorn==0.30.6`, `pydantic==2.9.2` — dichiarati in base per l'API HTTP pianificata in T10 (`ibp/api/`, non ancora presente su disco); a T1–T4 nessun modulo importa `fastapi`/`pydantic`/`uvicorn`.

**Testing:**
- `pytest==8.3.3` — unico framework di test, 20 file in `tests/` (`test_domain_*`, `test_engine_*`, `test_scenario_*`, `test_semantic_*`, `test_seed_*`, `test_db_*`). Nessuna sezione `[tool.pytest.ini_options]` in `pyproject.toml` né `pytest.ini`/`setup.cfg`: configurazione di default.

**Build/Dev:**
- Nessun tool di build applicativo (nessun bundler, nessun transpiler): il "workbench" web pianificato (T11) è dichiarato "statico (no build, no CDN)" in `docs/01-plan-m1.md`.
- Nessun linter/formatter configurato a livello di repository (nessun `.flake8`, `ruff.toml`, `.pylintrc`, `pyproject.toml` non contiene sezioni `[tool.ruff]`/`[tool.black]`/`[tool.mypy]`).

## Key Dependencies

**Critico — deliberatamente escluso:**
- `numpy` **non è una dipendenza** del progetto, per scelta esplicita e documentata. `db/seed/common.py` (righe 11–13): "Solo stdlib: `db/build_db.py` deve girare con le sole dipendenze dichiarate in `pyproject.toml` (duckdb + polars + pyarrow bastano per il seed); numpy non è nell'elenco fissato da T1 e non viene introdotto qui per una comodità locale." Il seed usa solo `random`/`math`/`hashlib` della stdlib. Non reintrodurre `numpy` come dipendenza implicita in task futuri senza motivarlo esplicitamente.

**Extra opzionale `[forecast]` (usato solo da T5, non ancora implementato):**
- `statsforecast==2.1.1`
- `hierarchicalforecast==1.5.1`
- `utilsforecast==0.2.16`

Installazione: `pip install -e ".[forecast]"` (non incluso in `pip install -e .`). Motivazione documentata in `pyproject.toml` e `README.md` ("Gotcha Windows"):
- Il pin storico `statsforecast==1.7.8` **non esiste su PyPI** (la serie 1.7 arriva a 1.7.6, poi salta a 2.0.3): l'errore osservato ("serve MSVC") era un sintomo del fallback alla sdist, non una reale mancanza di wheel.
- La serie 2.x sostituisce `numba` con `coreforecast` e pubblica wheel `cp313-win_amd64`: si installa **da wheel**, senza toolchain C++, senza toccare i pin di base (`pyarrow` resta `18.1.0`).
- Resta un extra separato per un motivo diverso: tira dentro ~11 pacchetti transitivi che M1–M4 non usano, non perché richieda compilazione.
- **Vincolo di import critico (segfault, non eccezione)**: `hierarchicalforecast._lib` e `coreforecast`/`utilsforecast` sono due estensioni C++ con runtime OpenMP distinti nello stesso processo. Il modulo di forecast di T5 deve importare `hierarchicalforecast._lib` come prima riga, prima di qualunque altro import del pacchetto, altrimenti il processo termina con SIGSEGV senza traceback. Un test di regressione deve lanciare l'import in un subprocess e verificare `returncode == 0` (un segfault dentro pytest non è catturabile come eccezione).
- API `hierarchicalforecast` 1.x: `HierarchicalReconciliation.reconcile()` usa `S_df=`, non `S=` (diverso dalla 0.4.x).

**Infrastruttura:**
- `duckdb==1.1.3` è l'unica infrastruttura dati: nessun server esterno, nessun servizio cloud, nessuna licenza (AC25, "tutto offline").

## Configuration

**Environment:**
- Nessuna variabile d'ambiente richiesta per il funzionamento base: `ibp/config.py` deriva tutti i path dalla posizione del repository (`REPO_ROOT = Path(__file__).resolve().parent.parent`), nessun segreto, nessun valore specifico d'ambiente.
- `DATA_DIR = REPO_ROOT / "data"`, `DB_PATH = DATA_DIR / "ibp.duckdb"`, `TEMP_DIR = DATA_DIR / "tmp"` — stessa struttura usata da `db/build_db.py`.
- `data/` (il file `.duckdb` e la directory temp) è in `.gitignore`: mai committato, sempre rigenerato con `python db/build_db.py`.
- Connessione DuckDB aperta esplicitamente offline: `autoinstall_known_extensions=false`, `autoload_known_extensions=false` (sia in `db/build_db.py` sia in `ibp/db.py`), più `temp_directory` esplicito per evitare directory di sistema imprevedibili su Windows.

**Build:**
- `pyproject.toml` — unico file di configurazione dipendenze/build, per l'intero arco M1–M3 (nota nel file: "Nessun task successivo a T1 modifica questo file").
- `db/schema.sql` — DDL as configuration-as-code per lo schema DuckDB.
- Nessun file `.env`/`.env.*` rilevato nel repository.

## Platform Requirements

**Development:**
- Windows (piattaforma verificata, con accorgimenti espliciti: esclusione `data/` da Windows Defender, gestione lock DuckDB single-writer, ordine di import per evitare segfault OpenMP nell'extra `[forecast]`).
- Python 3.11+ (verificato su 3.13); nessun requisito di toolchain C++/MSVC per l'installazione standard né per l'extra `[forecast]` (entrambi risolvono da wheel).

**Production:**
- Nessun target di deployment definito a M1 (T1–T4): il sistema gira come libreria/CLI locale, offline, senza servizi esterni. Un'API HTTP (FastAPI) e un workbench web statico sono pianificati per T10/T11 ma non ancora implementati.

---

*Stack analysis: 2026-09-19*
