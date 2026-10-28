# Struttura del codebase

**Data di analisi:** 2026-09-19

**Nota di scope:** `data/` (il `.duckdb` generato e la sua directory temp), `.software-house/` e
`.claude/` sono gitignored. `.claude/` è una junction verso un dominio agente esterno (tooling, non
codice di progetto) e non è stata esplorata. Il codice di progetto vive interamente in `ibp/`, `db/` e
`tests/`. Le directory `ibp/network/`, `ibp/capacity/`, `ibp/process/`, `ibp/adapters/`, `ibp/api/`,
`ibp/forecast/`, `ibp/cli.py`, `web/` sono **dichiarate nel layout di design**
(`docs/02-spec-m1-corrente.md`, sezione D7) come lavoro futuro (T5-T13) ma **non esistono ancora** su
questo filesystem: non compaiono nell'albero sotto.

## Directory Layout

```
IBP/
├── db/                          # Schema DuckDB + seed sintetico (T1, proprietà sh-data)
│   ├── schema.sql                 # Verità sul modello dati — unica fonte, non il codice Python
│   ├── build_db.py                # Entry point: ricostruisce data/ibp.duckdb da zero, idempotente
│   ├── __init__.py
│   └── seed/                      # Un modulo per dominio di dato seminato
│       ├── common.py                # RNG deterministico (hashlib, non hash()), util condivise
│       ├── dimensions.py             # item, item_identifier, DPLANT, DSALES_DIVISION, DVERSIONS, ...
│       ├── facts.py                  # TSOP_DEMAND, TSOP_OPS, TWSC_PAR_CALWEEK
│       ├── network.py                # item_link, production_eligibility, routing, bill_of_resource
│       ├── graph.py                  # edge (overlay a grafo, snapshot dell'ultimo periodo item_link)
│       ├── scenario.py               # scenario/edits/overlay seminati (due what-if di esempio)
│       ├── process.py                # cycle, cycle_phase, process_phases.json
│       ├── forecast.py               # forecast_snapshot/override (dato, non calcolo — T5 lo userà)
│       └── data/                     # JSON di master data (plant_master.json, process_phases.json)
├── ibp/                          # Package applicativo installabile (`pip install -e .`)
│   ├── __init__.py                 # __version__, confine ERP dichiarato nel docstring
│   ├── config.py                    # Path derivati dalla repo root (DB_PATH, TEMP_DIR) — no segreti
│   ├── db.py                        # UNICO punto di apertura connessioni DuckDB (connect/session)
│   ├── domain/                      # Entità, macchine a stati, errori (T2)
│   │   ├── state_machine.py           # StateMachine/Transitions generici, riusati da ogni entità
│   │   ├── scenario.py                # Scenario (dataclass) + SCENARIO_STATE (Draft/Evaluated/Promoted/Discarded)
│   │   ├── cycle.py                   # Cycle/CyclePhase, build_phase_sequence_machine
│   │   ├── gap.py                     # Gap + GAP_STATUS
│   │   ├── project.py                 # Project + PROJECT_STATE
│   │   ├── portfolio_item.py          # PortfolioItem + PORTFOLIO_ITEM_LIFECYCLE
│   │   ├── review.py                  # ReviewInstance + REVIEW_STATUS
│   │   └── errors.py                  # DomainError, InvalidTransitionError, UnknownStateError, PhaseClosedError
│   ├── semantic/                    # Mirror dEPM + graph overlay + DAG dichiarato (T2, D1/D4)
│   │   ├── dimensions.py               # PlantCapacity, ItemFactors — letture dal master data
│   │   ├── graph.py                    # edge/neighbors(), resolve_manufacturing_items() (F7)
│   │   ├── measures.py                 # Catalogo misure (DB) + MEASURE_DAG dichiarato (dato puro)
│   │   └── registry.py                 # Facciata SemanticRegistry
│   ├── engine/                      # Motore di ricalcolo incrementale (T3, D4)
│   │   ├── engine.py                   # RecalcEngine: full_recalculate()/recalculate(), height, cutoff
│   │   ├── cells.py                    # CellKey, edit types, CutoffStats, RecalcResult
│   │   ├── aggregate.py                # combine(agg_method, values) — min/max/avg/ratio/sum/count
│   │   ├── dates.py                    # Aritmetica su date_key (shift_date_key, date_key_to_date)
│   │   └── errors.py                   # UnknownCellEditError
│   └── scenario/                    # Event log -> overlay -> layer stack -> promozione (T4, D3)
│       ├── branch.py                    # branch(), mark_evaluated(), discard()
│       ├── edits.py                     # set_cell/increment_cell/delete_cell, resolve_cell (re-export)
│       ├── overlay.py                   # Meccanica di lettura: chain, materialize_*, resolve_cell, digest
│       ├── compare.py                   # compare(ref_a, ref_b) -> list[CompareRow]
│       ├── promote.py                   # promote() -> nuova istanza DVERSIONS
│       ├── models.py                    # CellKey, ResolvedCell, CompareRow, ScenarioStack, PromotionResult
│       ├── errors.py                    # ScenarioError e sottoclassi tipizzate
│       └── registry.py                  # Facciata ScenarioRegistry
├── tests/                        # Proprietà esclusiva di sh-tester — un test per AC (T1-T4)
│   ├── conftest.py                  # Fixture condivise (DB in-memory/temp per test)
│   ├── _engine_support.py             # Helper privati non a schema `test_*`
│   ├── _scenario_support.py           # idem, per i test di ibp/scenario/
│   └── test_*.py                      # Un file per area + AC (es. test_engine_ac10_recalc_equivalence.py)
├── docs/                         # Piano, spec, ADR, diagrammi archify (deliverable primario, F6)
│   ├── 01-plan-m1.md                  # Piano canonico di programma (superseded per il dettaglio task)
│   ├── 02-spec-m1-corrente.md          # Spec corrente — SUPERSEDE 01 per task/AC/design (D1-D7)
│   ├── 03-consegna-t1-t4.md            # Nota di consegna T1-T4
│   ├── ADR-001-decisioni-dominio.md    # Architecture decision record
│   ├── ingest-manifest.yaml
│   └── diagrams/                      # Diagrammi archify (as-is/to-be/database/processo) + viewer HTML
├── pyproject.toml                # Tutte le dipendenze, proprietà esclusiva di T1 (deroga registrata per riaperture)
├── README.md                     # Setup locale, gotcha Windows/DuckDB offline
├── .planning/                    # Stato del progetto GSD (piani, intel, codebase map — questo file)
├── data/                         # GITIGNORED — data/ibp.duckdb generato da db/build_db.py
├── .software-house/              # GITIGNORED — non esplorato (dominio agente esterno)
└── .claude/                      # GITIGNORED, junction verso tooling esterno — non esplorato
```

## Directory Purposes

**`db/` (proprietà T1/sh-data):**
- Scopo: definire lo schema DuckDB canonico e generare un database sintetico, deterministico e
  riproducibile.
- Contiene: `schema.sql` (unica verità sul modello dati — un prompt verso un implementatore deve sempre
  verificarla, mai fidarsi solo del codice Python), `build_db.py` (orchestratore + `_validate()`), `seed/`
  (un modulo Python per dominio di dato, ognuno produce `polars.DataFrame` caricati in bulk).
- File chiave: `db/schema.sql`, `db/build_db.py`, `db/seed/common.py` (RNG deterministico condiviso).

**`ibp/domain/` (T2):**
- Scopo: entità con ciclo di vita e la macchina a stati generica che tutte condividono. Nessuna
  entità ordine/BOM/MRP (confine ERP, AC10/AC24).
- Contiene: dataclass `frozen=True`, mappe di transizione dichiarate come dato, eccezioni di dominio.
- File chiave: `ibp/domain/state_machine.py` (l'astrazione riusata ovunque), `ibp/domain/scenario.py`.

**`ibp/semantic/` (T2):**
- Scopo: mirror dello star schema dEPM + overlay a grafo tipizzato; catalogo misure e DAG delle misure
  calcolate come dato dichiarativo (nessun calcolo in questo package).
- Contiene: funzioni pure a connessione esplicita (mai apre connessioni proprie) + `SemanticRegistry`
  come facciata comoda.
- File chiave: `ibp/semantic/measures.py` (`MEASURE_DAG`), `ibp/semantic/graph.py`
  (`resolve_manufacturing_items()`, fonte autorevole per le relazioni di produzione item->item).

**`ibp/engine/` (T3):**
- Scopo: eseguire il DAG dichiarato in `ibp/semantic/measures.py` con semantica di concurrent planning
  (propagazione immediata, non batch sequenziali) e early cutoff.
- Contiene: `RecalcEngine` (stato vivo per una coppia di versioni demand/ops), tipi di edit e risultati
  come dataclass, aritmetica di supporto (date, aggregazione).
- File chiave: `ibp/engine/engine.py` (644 righe — il file più grande del progetto).

**`ibp/scenario/` (T4):**
- Scopo: ciclo di vita what-if completo — branch, scrittura sparsa con tombstone esplicito, confronto,
  promozione a nuova istanza `DVERSIONS`. Vedi `ARCHITECTURE.md` per l'analisi approfondita di questo
  strato rispetto a R-001.
- Contiene: un modulo per responsabilità (non un unico file monolitico), value object frozen in
  `models.py`, eccezioni tipizzate in `errors.py`.
- File chiave: `ibp/scenario/overlay.py` (meccanica di lettura condivisa da tutto il resto del
  pacchetto), `ibp/scenario/promote.py` (il punto in cui uno scenario diventa un piano).

**`tests/` (proprietà esclusiva di sh-tester):**
- Scopo: un test (o gruppo di test in un file) per ogni acceptance criterion. **Nessun task
  implementatore tocca mai `tests/**`** — vincolo invariante dichiarato nel piano.
- Naming: `test_{area}_{ac_id}_{descrizione}.py` quando il file copre un AC specifico (es.
  `test_engine_ac10_recalc_equivalence.py`), oppure `test_{area}_{descrizione}.py` per test trasversali
  (es. `test_semantic_graph.py`). Helper privati non raccolti da pytest hanno prefisso `_` (es.
  `_engine_support.py`, `_scenario_support.py`).

## Key File Locations

**Entry point di build:**
- `db/build_db.py`: `python db/build_db.py` ricostruisce `data/ibp.duckdb` da zero.

**Accesso dati:**
- `ibp/db.py`: `connect()`/`session()` — unico punto di apertura connessioni DuckDB in tutto `ibp`.

**Configurazione:**
- `ibp/config.py`: path derivati dalla repo root (`DB_PATH`, `TEMP_DIR`). Nessun segreto.
- `pyproject.toml`: tutte le dipendenze — proprietà esclusiva di T1, riaperto solo due volte per deroga
  registrata (pin `statsforecast`, extra `[forecast]`).

**Logica di dominio centrale:**
- `db/schema.sql`: verità sul modello dati.
- `ibp/semantic/measures.py`: DAG dichiarato delle misure calcolate.
- `ibp/engine/engine.py`: esecuzione del DAG.
- `ibp/scenario/promote.py`, `ibp/scenario/overlay.py`: ciclo di vita scenario -> piano.

**Testing:**
- `tests/conftest.py`: fixture condivise.
- `tests/test_*.py`: 26 file, un'area/AC per file.

## Naming Conventions

**File:**
- Modulo per responsabilità singola dentro un package (`branch.py`, `edits.py`, `overlay.py`,
  `compare.py`, `promote.py` dentro `ibp/scenario/` — mai un unico `scenario.py` monolitico).
- `errors.py` per le eccezioni di un package, `models.py` per i value object condivisi, `registry.py`
  per la facciata comoda quando un package ne ha una (`SemanticRegistry`, `ScenarioRegistry`).
- Test: `test_{area}_{ac_id opzionale}_{descrizione}.py`; helper condivisi non-test con prefisso `_`.

**Directory:**
- Un package Python per strato architetturale (`domain/`, `semantic/`, `engine/`, `scenario/`), tutti
  sotto `ibp/` come sub-package con `__init__.py` che ri-esporta l'API pubblica (vedi
  `ibp/scenario/__init__.py`: importa da ogni modulo interno e dichiara `__all__` esplicito).

**Funzioni/identificatori (convenzioni osservate, da rispettare scrivendo nuovo codice):**
- Funzioni pure a connessione esplicita: primo parametro sempre `con`, mai una connessione aperta
  internamente (vincolo esplicito, T2 done_when #5 — "unico punto di accesso DuckDB").
- Prefisso `_` per funzioni/helper privati di modulo (`_apply_edit`, `_upsert_overlay`,
  `_snapshot_check`, `_materialize_demand`).
- Docstring di modulo estesi che dichiarano esplicitamente limiti di grana, bug reali chiusi e la
  motivazione delle scelte (non solo "cosa fa" ma "perché così e non altrimenti") — pattern pervasivo in
  `ibp/scenario/` e `ibp/engine/engine.py`, da continuare in nuovo codice sullo stesso strato.
- Costanti a livello di modulo in `UPPER_SNAKE_CASE` per insiemi/mappe dichiarativi
  (`MEASURE_DAG`, `SCENARIO_TRANSITIONS`, `_SIDES`, `_STATUSES`, `_MEASURE_TABLE`).
- Eccezioni: sempre sottoclassi di una base di package (`ScenarioError`, `DomainError`), con attributi
  strutturati nel costruttore (non solo un messaggio testuale) così un chiamante può leggere
  `err.scenario_id`, `err.expected_snapshot`, ecc.

## Where to Add New Code

**Nuovo strato applicativo dichiarato nel design ma non ancora creato** (`ibp/network/`,
`ibp/capacity/`, `ibp/process/`, `ibp/adapters/`, `ibp/api/`, `ibp/forecast/`, `web/`, `ibp/cli.py`):
- Seguire lo stesso pattern di `ibp/scenario/`: un modulo per responsabilità, `errors.py` per le
  eccezioni tipizzate del package, `models.py`/`registry.py` se servono value object o una facciata,
  `__init__.py` con `__all__` esplicito.
- Verificare sempre `docs/02-spec-m1-corrente.md` (sezione D7, backlog per task) per i path assegnati:
  due task nella stessa ondata non toccano mai lo stesso file (vincolo invariante del piano).

**Nuova entità di dominio con ciclo di vita:**
- File in `ibp/domain/`, dataclass `frozen=True` + mappa di transizioni dichiarata come
  `Transitions = Mapping[str, tuple[str, ...]]` accanto alla dataclass, istanza di
  `StateMachine(name, transitions)` a livello di modulo, metodo `transition_to()` che delega ad essa
  (vedi `ibp/domain/scenario.py` come riferimento minimo).

**Nuova misura calcolata nel DAG di ricalcolo:**
- Dichiarare il nodo in `ibp/semantic/measures.py::MEASURE_DAG` (dato, non calcolo).
- Implementare `_compute_<nome>_cell()` in `ibp/engine/engine.py`, aggiungerla a `_COMPUTED_NODES` e al
  dispatch di `_compute_cell()`/`_downstream()` — mantenendo l'invariante che ogni cella abbia **una
  sola** funzione di calcolo chiamata identicamente da `full_recalculate()` e `recalculate()` (è ciò che
  rende AC10 vero per costruzione; romperla rompe AC10 in un modo che nessun test locale mostra da solo).

**Nuovo tipo di edit per il motore:**
- Aggiungere il dataclass in `ibp/engine/cells.py`, registrare un validatore in
  `RecalcEngine._EDIT_VALIDATORS` (`ibp/engine/engine.py`) — un tipo senza validatore registrato deve
  sollevare `UnknownCellEditError`, mai passare silenziosamente.

**Utility condivise:**
- Aritmetica su date: `ibp/engine/dates.py`.
- RNG deterministico per seed: `db/seed/common.py` (sempre `hashlib`, mai `hash()` builtin — salato per
  processo).

**Test:**
- Sempre e solo in `tests/`, mai in un path di un altro task (vincolo invariante). Un file per AC quando
  l'AC è puntuale; helper condivisi con prefisso `_` accanto ai test che li usano.

## Special Directories

**`data/`:**
- Scopo: `data/ibp.duckdb` (generato da `db/build_db.py`) e `data/tmp/` (temp directory esplicita di
  DuckDB).
- Generato: sì, interamente derivato da `db/schema.sql` + `db/seed/**`.
- Committed: no (gitignored) — non esiste un percorso di migrazione incrementale perché non c'è un DB
  reale da preservare; ogni rebuild riparte da zero.

**`docs/diagrams/`:**
- Scopo: diagrammi archify (as-is, to-be, database, processo) più il loro viewer HTML statico e
  screenshot di verifica visiva.
- Generato: sì (tool archify), ma committed nel repo (fa parte del deliverable documentale, F6).
- Committed: sì.

**`.software-house/` e `.claude/`:**
- Scopo: tooling dell'agente di sviluppo (dominio "software-house" e dominio agente Claude) — non
  codice applicativo del progetto IBP.
- Generato/gestito da: tooling esterno al progetto.
- Committed: no (gitignored). `.claude/` è una junction filesystem verso un dominio esterno e non va
  esplorata da chi lavora sul codice applicativo.

---

*Analisi struttura: 2026-09-19*
