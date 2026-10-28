<!-- refreshed: 2026-09-19 -->
# Architettura

**Data di analisi:** 2026-09-19

**Stato del codice analizzato:** M1, T1-T4 completati (187 test verdi). `ibp/network/`, `ibp/capacity/`,
`ibp/process/`, `ibp/adapters/`, `ibp/api/`, `ibp/forecast/`, `ibp/cli.py`, `web/` sono **dichiarati nel
layout di design** (`docs/02-spec-m1-corrente.md`, sezione D7) ma **non esistono ancora sul filesystem**:
sono lavoro futuro (T5-T13). Questo documento descrive solo ciò che è realmente a terra oggi:
`ibp/domain/`, `ibp/semantic/`, `ibp/engine/`, `ibp/scenario/`, più `db/` e `tests/`.

## System Overview

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                    Seed / build (offline, riproducibile)                 │
│  `db/build_db.py` orchestrata da `db/seed/*.py` -> `data/ibp.duckdb`     │
└───────────────────────────────┬────────────────────────────────────────┘
                                  │ (schema + master data + fatti)
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│               Semantic layer — mirror dEPM + graph overlay (D1)          │
│  `ibp/semantic/dimensions.py`  `graph.py`  `measures.py`  `registry.py` │
│  Legge `item`, `item_link`, `edge`, `DMEASURE_*`, `DPLANT` — dichiara    │
│  il DAG delle misure derivate (`MEASURE_DAG`), non calcola nulla.        │
└───────────────────────────────┬────────────────────────────────────────┘
                                  │ (letto da)
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│           Motore di ricalcolo — concurrent planning (D4)                 │
│  `ibp/engine/engine.py` (`RecalcEngine`)  `cells.py`  `aggregate.py`    │
│  `full_recalculate()` / `recalculate(changed)`: height, early cutoff.   │
└───────────────────────────────┬────────────────────────────────────────┘
                                  │ (legge/scrive TSOP_DEMAND / TSOP_OPS)
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│         Livello Scenario — event log -> overlay -> layer stack (D3)      │
│  `ibp/scenario/branch.py` `edits.py` `overlay.py` `compare.py`         │
│  `promote.py` `registry.py`                                             │
│  `scenario` (stato) + `edits` (log append-only) + `overlay` (cache)     │
│  risolti a runtime; `promote()` materializza una NUOVA `DVERSIONS`.     │
└───────────────────────────────┬────────────────────────────────────────┘
                                  │ (entità e macchine a stati condivise da tutti gli strati sopra)
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                  Dominio — entità, macchine a stati, errori (T2)         │
│  `ibp/domain/scenario.py` `cycle.py` `gap.py` `project.py`             │
│  `portfolio_item.py` `review.py` `state_machine.py` `errors.py`        │
└──────────────────────────────────────────────────────────────────────────┘

Punto di accesso unico a DuckDB (attraversato verticalmente da ogni strato sopra):
`ibp/db.py` (`connect()` / `session()`) — nessun altro modulo apre una connessione propria.
```

## Component Responsibilities

| Componente | Responsabilità | File |
|---|---|---|
| Seed & build | Ricostruisce `data/ibp.duckdb` da zero, idempotente, con `_validate()` che fa fallire il build su invariante violata | `db/build_db.py`, `db/schema.sql`, `db/seed/**` |
| Accesso DB | Unico punto di apertura di connessioni DuckDB, config offline (no autoload extension, `temp_directory` esplicito) | `ibp/db.py` |
| Dominio | Entità, value object e macchine a stati generiche (dichiarate come dato, non `if`/`elif`) | `ibp/domain/**` |
| Semantic layer | Dimensioni/misure/grafo sopra il mirror dEPM; DAG delle misure calcolate dichiarato come dato | `ibp/semantic/**` |
| Motore di ricalcolo | Esecuzione del DAG dichiarato: `full_recalculate()`/`recalculate()`, height, early cutoff | `ibp/engine/**` |
| Livello Scenario | Event log append-only, overlay con tombstone, confronto, promozione a nuova `DVERSIONS` | `ibp/scenario/**` |
| Suite di test | Proprietà esclusiva di `sh-tester`; un test per AC | `tests/**` |

## Pattern Overview

**Complessivo:** architettura a strati verticali sopra un unico DB DuckDB embedded, senza server
applicativo (M1 non ha ancora API HTTP): ogni strato riceve una connessione dal chiamante e non ne apre
di proprie. Non è MVC né un'architettura a microservizi: è più vicina a un **motore di calcolo a
libreria** (una libreria Python importabile, `pip install -e .`), con lo stato persistente interamente
in DuckDB e nessuno stato di processo condiviso oltre le cache in-memory di `RecalcEngine`.

**Caratteristiche chiave:**
- **DAG dichiarato, non implicito**: `ibp/semantic/measures.py::MEASURE_DAG` è dato puro (nessun calcolo);
  `ibp/engine/engine.py` lo esegue. Chi vuole sapere "cosa dipende da cosa" legge il dato, non il codice
  del motore.
- **Event sourcing parziale per gli scenari**: `edits` è la verità append-only, `overlay` è una cache
  derivata e ricostruibile. Non è event sourcing completo (il base — `TSOP_DEMAND`/`TSOP_OPS` — non è
  esso stesso un log di eventi, è stato mutabile solo tramite un nuovo `INSERT` di versione via
  `promote()`).
- **COALESCE a runtime, mai materializzato fino alla promozione**: leggere una cella di uno scenario
  (`resolve_cell()`, `materialize_ref()`) attraversa la catena di scenari e il base ad ogni chiamata;
  nessuna tabella contiene il "valore risolto corrente" finché `promote()` non scrive una nuova
  `DVERSIONS`.
- **Grana dichiarata esplicitamente, mai nascosta**: ogni modulo che lavora a una grana più larga o più
  stretta di quella "naturale" del fatto lo dice nel docstring (`overlay` non porta `division_key`/
  `region`/`manufact_key`; `derived_manufacturing_demand` aggrega su `(manufact_key, date_key)` e perde
  la region — debito noto, T6.0).
- **Errori tipizzati, mai `ValueError` generico**: ogni pacchetto (`ibp.domain.errors`,
  `ibp.engine.errors`, `ibp.scenario.errors`) ha una gerarchia di eccezioni proprie; un fallimento
  riconoscibile per tipo, mai un risultato plausibile ma sbagliato.

## Layers

**Dominio (`ibp/domain/`):**
- Scopo: entità con ciclo di vita (`Scenario`, `Cycle`/`CyclePhase`, `Gap`, `Project`, `PortfolioItem`,
  `ReviewInstance`) e la macchina a stati generica che tutte condividono.
- Posizione: `ibp/domain/`
- Contiene: dataclass frozen + mappe di transizione (`Transitions = Mapping[str, tuple[str, ...]]`) +
  eccezioni di dominio.
- Dipende da: nulla dentro `ibp` (è lo strato più a monte).
- Usato da: `ibp/semantic/registry.py` (macchina a stati del ciclo), `ibp/scenario/*` (macchina a stati
  `Scenario`), test.

**Semantic layer (`ibp/semantic/`):**
- Scopo: mirror dello star schema dEPM + overlay a grafo (D1); DAG dichiarato delle misure derivate (D4,
  solo dato).
- Posizione: `ibp/semantic/`
- Contiene: `dimensions.py` (plant, item factors), `graph.py` (`edge`, `neighbors()`,
  `resolve_manufacturing_items()`), `measures.py` (catalogo misure + `MEASURE_DAG`), `registry.py`
  (facciata `SemanticRegistry`).
- Dipende da: `ibp/domain/cycle.py` (per `cycle_phase_machine`).
- Usato da: `ibp/engine/engine.py` (dimensions, graph, measures), `ibp/scenario/*` (indirettamente, via
  measure catalog in `overlay.py`).

**Motore di ricalcolo (`ibp/engine/`):**
- Scopo: eseguire il DAG dichiarato con semantica di concurrent planning (ogni edit ripropaga subito, con
  early cutoff sull'hash del valore).
- Posizione: `ibp/engine/`
- Contiene: `engine.py` (`RecalcEngine`), `cells.py` (tipi di edit, `CutoffStats`, `RecalcResult`),
  `aggregate.py` (`combine()` per `agg_method`), `dates.py` (aritmetica su `date_key`), `errors.py`.
- Dipende da: `ibp/semantic/` (dimensions, graph, measures).
- Usato da: nessuno strato oggi (T10/API non ancora costruita) — consumato direttamente dai test e dal
  futuro `ibp/api/`.

**Livello Scenario (`ibp/scenario/`):**
- Scopo: ciclo di vita what-if — branch, scrittura sparsa con tombstone, confronto, promozione a nuova
  `DVERSIONS` (D3). Vedi sezione dedicata sotto: è lo strato più rilevante per R-001.
- Posizione: `ibp/scenario/`
- Contiene: `branch.py`, `edits.py`, `overlay.py`, `compare.py`, `promote.py`, `models.py`, `errors.py`,
  `registry.py` (facciata `ScenarioRegistry`).
- Dipende da: `ibp/domain/scenario.py` (la macchina a stati `Scenario` è dichiarata lì, non duplicata).
- Usato da: nessuno strato oggi — seam esplicito per T3 (`mark_evaluated()`) non ancora agganciato da
  `ibp/engine/`.

## Data Flow

### Percorso primario di ricalcolo (concurrent planning, D4)

1. `RecalcEngine.__init__(con, demand_version_key=..., ops_version_key=...)` (`ibp/engine/engine.py:136`)
   carica `requested_production` da `TSOP_DEMAND` e `confirmed_production` da `TSOP_OPS`, poi chiama
   `full_recalculate()` — nessuna cache bulk oggi (debito noto: 14.394 query, T10.0 pending).
2. `full_recalculate()` (`engine.py:470`) visita ogni cella di `derived_manufacturing_demand` ->
   `slots_requested` -> `gap_req_conf` -> `value_gap`, chiamando le stesse `_compute_*_cell()` che userà
   `recalculate()` — questa identità di funzione è ciò che rende AC10 vero per costruzione.
3. Un edit successivo passa da `recalculate(changed_cells)` (`engine.py:535`): fase 1 valida ogni edit
   per tipo (`_EDIT_VALIDATORS`, dispatch esplicito, mai `isinstance` sparso) **prima** di mutare stato;
   fase 2 applica gli edit ed enqueue le celle a valle in un min-heap ordinato per `height` del nodo
   (`_node_heights()`, `engine.py:99`); ogni cella ricalcolata che risulta invariata (`_classify_cell`,
   `engine.py:440`) non propaga oltre (early cutoff, AC11).

### Risoluzione di una cella scenario (lettura, D3)

1. `resolve_cell(con, ref, cell)` (`ibp/scenario/edits.py:24`, ri-esporta `overlay.resolve_cell`,
   `overlay.py:357`) valida che la misura sia additiva (`require_additive_measure`, AC12), poi:
2. Se `ref` è uno `scenario_id`, percorre `scenario_chain()` (`overlay.py:51`) da **foglia a radice**
   cercando la prima riga di `overlay` che ha scritto quella `CellKey` esatta (`_find_overlay_row`,
   `overlay.py:336`) — il layer più vicino alla foglia vince.
3. Se nessun layer ha scritto la cella, risolve da `base_cell_value()` sul `base_version_key` della
   radice della catena, sommando in Python su righe ordinate deterministicamente (mai `SUM ... GROUP BY`
   lato SQL, per determinismo bit-esatto fra chiamate).

### Scrittura di un edit su uno scenario (D3)

1. `set_cell`/`increment_cell`/`delete_cell` (`ibp/scenario/edits.py:134-150`) delegano a `_apply_edit`
   (`edits.py:89`), dentro una transazione nuda (`BEGIN`/`COMMIT`/`ROLLBACK` — debito AC30, T10.1
   pending).
2. `_writable_scenario()` (`edits.py:49`) rifiuta la scrittura su scenario terminale
   (`ScenarioWriteRejectedError`) e riporta `Evaluated -> Draft` se necessario (un nuovo edit dopo la
   valutazione rimette in lavorazione).
3. Viene inserita **sempre** una riga in `edits` (log immutabile) e fatto un upsert in `overlay`
   (`_upsert_overlay`, `edits.py:65`) — mai un solo dei due.

### Promozione di uno scenario a nuova versione (D3, il percorso più rilevante per R-001)

1. `promote(con, scenario_id, *, cycle_year, cycle_month, side, status, user)`
   (`ibp/scenario/promote.py:257`) carica lo scenario, calcola `version_name` con la grammatica fissa
   `SOP_{YYYY}_{MM}_{SIDE}_{STATUS}` (`_version_name`, `promote.py:60`).
2. Verifica `SideMismatchError`, `DuplicateVersionError`, valida la transizione di stato
   (`scenario.transition_to("Promoted")`) **prima** di materializzare qualunque riga.
3. `_snapshot_check()` (`promote.py:223`) rileva una base mossa dal branch time (AC16) ricalcolando
   `base_content_digest()` e confrontandolo con `base_snapshot_id` — solo se quest'ultimo è nel formato
   prodotto da `branch()`.
4. `overlay_touched_slices()` (`overlay.py:260`) calcola l'insieme esatto di slice scritte/cancellate
   dall'intera catena; `_materialize_demand`/`_materialize_ops` (`promote.py:142`, `189`) copiano ogni
   riga base non toccata **byte per byte**, e ripartiscono (`_shares()`, `promote.py:117`) solo le slice
   toccate su più righe base.
5. Dentro un'unica transazione: `INSERT` di una **nuova** riga `DVERSIONS` con `version_key` calcolato
   (`MAX(version_key)+1`), bulk insert in `TSOP_DEMAND`/`TSOP_OPS`, `UPDATE scenario SET state =
   'Promoted'`.

**Gestione dello stato:** nessuno stato di processo condiviso oltre le cache in-memory di
`RecalcEngine` (per istanza, non globali). Tutto lo stato persistente vive in DuckDB; DuckDB è
single-writer con lock di processo (vincolo di piattaforma, non di questo codice).

## Key Abstractions

**`CellKey` (`ibp/scenario/models.py:22`):**
- Scopo: identifica una cella di scenario alla grana di `overlay`: `(version_key, date_key,
  measure_key, product_key | plant_key)` — esattamente uno fra `product_key` (demand) e `plant_key`
  (ops), mai entrambi (XOR validato in `__post_init__`).
- Esempi: costruita da `ibp/engine/cells.py` (`RequestedProductionEdit`/`ConfirmedProductionEdit`) e da
  ogni chiamante di `ibp/scenario/edits.py`.
- Pattern: value object frozen con validazione nel costruttore, mai un dict libero.

**`MeasureNode`/`MEASURE_DAG` (`ibp/semantic/measures.py:80`):**
- Scopo: dichiara il DAG delle misure calcolate come dato Python (`graphlib.TopologicalSorter` per
  validare l'aciclicità), separando "cosa dipende da cosa" da "come si calcola" (`ibp/engine/`).
- Esempi: `requested_production`, `confirmed_production` (sorgenti), `derived_manufacturing_demand`,
  `slots_requested`, `gap_req_conf`, `value_gap` (calcolati).
- Pattern: registry dichiarativo; `nodes()`/`edges()`/`dirty_set()` sono pure funzioni di lettura, mai
  esecuzione.

**`StateMachine`/`Transitions` (`ibp/domain/state_machine.py:19`):**
- Scopo: macchina a stati generica riusata da ogni entità di dominio con ciclo di vita — le transizioni
  valide sono dato (`Mapping[str, tuple[str, ...]]`), non `if`/`elif` sparsi.
- Esempi: `SCENARIO_STATE` (`ibp/domain/scenario.py:27`, Draft/Evaluated/Promoted/Discarded),
  `CYCLE_PHASE_STAT_MACHINE` (`ibp/domain/cycle.py`), `PORTFOLIO_ITEM_LIFECYCLE`, `PROJECT_STATE`,
  `GAP_STATUS`, `REVIEW_STATUS`.
- Pattern: composizione, non ereditarietà — ogni dataclass di dominio ha un metodo `transition_to()` che
  delega alla propria `StateMachine` condivisa a livello di modulo.

**`ScenarioStack` (`ibp/scenario/models.py:95`):**
- Scopo: la chiave di isolamento cache (AC15) — `base_version_key` più la catena ordinata radice->foglia
  degli `scenario_id`. `cache_key()` è ciò che qualunque cache a valle (T3, T10 futuri) deve includere per
  intero, mai solo la foglia.
- Pattern: value object frozen, nessuna logica oltre `cache_key()`.

## Entry Points

**`db/build_db.py` (funzione `main`/script):**
- Posizione: `db/build_db.py`
- Trigger: eseguito manualmente (`python db/build_db.py`) o da CI/demo.
- Responsabilità: ricrea `data/ibp.duckdb` da zero (drop+create da `db/schema.sql`), orchestra il seed
  (`db/seed/*.py`), sostituisce `PENDING_DIGEST` con l'impronta reale (`_stamp_base_snapshots`), esegue
  `_validate()` che fa fallire il build su invariante violata (quote item_link non al 100%, sentinella
  di digest residuo, ecc.).

**`ibp.db.connect()` / `ibp.db.session()` (`ibp/db.py`):**
- Posizione: `ibp/db.py`
- Trigger: chiamato da ogni test e da ogni futuro consumatore (CLI, API) che ha bisogno di una
  connessione.
- Responsabilità: unico punto di apertura di connessioni DuckDB nel package, con le impostazioni offline
  (no autoload/autoinstall extension, `temp_directory` esplicito).

**Non ancora esistenti (dichiarati nel design, T5+):** `ibp/cli.py` (comandi + demo end-to-end, T12),
`ibp/api/app.py` (`uvicorn ibp.api.app:app`, T10). Oggi l'unico modo di "entrare" nel sistema è importare
i moduli Python direttamente (come fa `tests/`).

## Architectural Constraints

- **Threading/concorrenza:** nessun modello a thread nel codice applicativo; DuckDB stesso è
  single-writer con lock di processo (vincolo di piattaforma citato in `ibp/db.py` e nel README) — un
  futuro server (T10) dovrà condividere **una** connessione fra richieste HTTP e job, non aprirne una per
  richiesta.
- **Stato globale:** nessun singleton a livello di modulo che tenga stato applicativo; `RecalcEngine` è
  istanziato per chiamata e tiene le proprie cache (`_item_factor_cache`, `_eligible_plant_cache`, ecc.)
  come attributi di istanza, non di classe.
- **Transazioni non rientranti (debito noto, AC30):** ogni helper di scrittura di `ibp/scenario/` apre un
  `BEGIN TRANSACTION` nudo (`branch.py:81,113,127`, `edits.py:93`, `promote.py:332`). DuckDB solleva
  `TransactionException: cannot start a transaction within a transaction` e **non supporta SAVEPOINT**:
  finché `ibp/db.py` non espone un context manager di transazione rientrante (T10.1, pending), nessuna di
  queste funzioni può essere chiamata dentro una transazione già aperta dal chiamante.
- **Determinismo numerico esplicito:** ogni somma su righe potenzialmente multiple (`materialize_version`,
  `base_content_digest`, `_shares`) usa `ORDER BY` sulla chiave primaria piena + somma in Python, mai
  `SUM(...) GROUP BY` lato SQL — DuckDB parallelizza `SUM` e non garantisce lo stesso ordine di riduzione
  fra due esecuzioni identiche, che produrrebbe rumore nell'ultimo bit e falsi "cambiamenti" in
  `compare()`.
- **Grana persa nell'aggregazione manifatturiera (debito noto, prerequisito bloccante T6.0):**
  `derived_manufacturing_demand` aggrega su `(manufact_key, date_key)` e **non porta la region della
  domanda**; `_eligible_plant_for()` (`ibp/engine/engine.py:209`) quindi non ha region con cui filtrare
  `production_eligibility.region_scope` e sceglie il plant a priorità minima cacheandolo per
  `manufact_key` soltanto. Corretto oggi solo perché il seed lascia `production_eligibility.valid_to`
  NULL — silenziosamente sbagliato appena AC5 (multi-plant con region_scope) sarà vera.

## Anti-Patterns

### Confondere "presente in overlay" con "toccato dallo scenario"

**Cosa succede:** un'implementazione ingenua di `promote()` userebbe la presenza di una slice nel
risultato di `materialize_ref()` (base + overlay risolto) come segnale di "questa slice è stata
modificata dallo scenario".
**Perché è sbagliato qui:** `materialize_ref()` non distingue una slice mai sfiorata da una slice
toccata ma il cui overlay risolto coincide col valore di base — e ricalcolare `sum(v) * (v / sum(v))`
anche per la prima produce un valore che differisce dall'originale nell'ultimo bit
(`21.939 -> 21.939000000000004`), rendendo un `promote()` a zero edit non più bit-identico al base.
**Fare invece:** usare `overlay_touched_slices()` (`ibp/scenario/overlay.py:260`), che risponde
esattamente "quali slice ha scritto o cancellato la catena", copiando ogni altra riga invariata.

### Trattare un `base_snapshot_id` non riconosciuto come "base non spostata"

**Cosa succede:** un controllo naive tratterebbe qualunque `base_snapshot_id` che non solleva un
mismatch come "verificato, base immobile" (un singolo `bool`).
**Perché è sbagliato qui:** il seed pre-T4 (`db/seed/scenario.py`) scrive `base_snapshot_id` nel formato
`SNAP_{version_name}_{iso_ts}` (un'etichetta con timestamp, non un'impronta di contenuto), diverso dal
formato che `branch()` produce (`SNAP_{version_key}_{sha256}`). Trattarlo come "conflitto" bloccherebbe
per sempre l'unico scenario `Evaluated` spedito col seed; trattarlo silenziosamente come "verificato"
farebbe passare AC16 su una promozione che non è mai stata davvero controllata.
**Fare invece:** `_snapshot_check()` (`ibp/scenario/promote.py:223`) ritorna una coppia
`(verified, moved)`, e `PromotionResult.base_verified` la espone al chiamante — mai un solo `bool` che
confonde "confermato immobile" con "non verificabile".

## Error Handling

**Strategia:** eccezioni tipizzate per pacchetto, mai `ValueError`/`Exception` generico per un errore di
dominio. Ogni pacchetto (`ibp.domain.errors`, `ibp.engine.errors`, `ibp.scenario.errors`) definisce una
classe base (`DomainError`, `ScenarioError`, ecc.) e sottoclassi specifiche con attributi strutturati
(non solo un messaggio) per permettere a un chiamante di reagire per tipo.

**Pattern:**
- Validazione **prima** della mutazione: `recalculate()` valida ogni edit del batch (`_EDIT_VALIDATORS`)
  prima di scrivere qualunque stato — un batch parzialmente applicato lascerebbe il motore avvelenato per
  sempre (bug reale chiuso in T3, due volte).
- Rifiuto esplicito invece di un valore plausibile ma sbagliato: `NonAdditiveMeasureError` invece di
  sommare un `ratio`; `UnmaterializableCellError` invece di inventare `division_key`/`region` mancanti;
  `GraphSnapshotLimitationError` invece di restituire `[]` silenziosamente per un `as_of` storico che
  `edge` non può onorare.
- Transazione con `try/except`+`ROLLBACK` esplicito in ogni funzione di scrittura di `ibp/scenario/`
  (pattern ripetuto identico in `branch.py`, `edits.py`, `promote.py` — debito di duplicazione risolto
  solo parzialmente, vedi T10.1).

## Cross-Cutting Concerns

**Logging:** nessun framework di logging nel codice applicativo oggi; i moduli comunicano lo stato
tramite valori di ritorno (`RecalcResult`, `PromotionResult`, `CutoffStats`) ed eccezioni tipizzate.

**Validazione:** a più livelli — vincoli SQL (`CHECK`, `UNIQUE`) in `db/schema.sql`; guardie esplicite in
Python prima di ogni operazione sensibile (`require_additive_measure`, `_writable_scenario`,
`_EDIT_VALIDATORS`); `_validate()` di fine build (`db/build_db.py`) per invarianti cross-tabella (somma
quote `item_link` = 100, nessun sentinella `PENDING_DIGEST` residuo).

**Autenticazione:** non applicabile a M1 (nessuna API HTTP ancora costruita); ogni scrittura porta un
campo `user`/`owner` libero (stringa), senza autenticazione né autorizzazione.

---

## Il livello Scenario oggi, e il divario verso R-001 (trunk unico stile Kinaxis)

Questa sezione risponde a una domanda specifica: **cosa distingue oggi uno "scenario" da un "piano
salvato" (un'istanza `DVERSIONS` promossa), e cosa dovrebbe cambiare perché diventino la stessa specie di
oggetto**, come richiesto da R-001 (un trunk centrale su cui sia i piani salvati sia gli scenari salvati
sono branch dello stesso tipo, come in Kinaxis RapidResponse).

### Cosa sono oggi i due oggetti — due spazi di identità strutturalmente diversi

**Uno `scenario`** (`db/schema.sql`, tabella `scenario`; classe `Scenario` in `ibp/domain/scenario.py:31`)
è:
- identificato da `scenario_id` (stringa opaca `SCN-{uuid.hex[:12]}`, generata da
  `ibp/scenario/branch.py::_new_scenario_id`, `branch.py:20` — nessuna collisione con un `MAX(...)+1` in
  corsa, perché è auto-sufficiente);
- **sempre** ancorato a un `base_version_key: int` (FK logica a `DVERSIONS.version_key`) — il tipo del
  parametro in `branch()` (`ibp/scenario/branch.py:28`) è fissato a `int`, non "un altro nodo dello stesso
  tipo";
- opzionalmente annidato via `parent_scenario_id: str | None` — un meccanismo **diverso** da
  `base_version_key`: annidare uno scenario sotto un altro scenario usa un campo, ancorarlo a un piano
  ufficiale ne usa un altro, e `branch()` impone che i due debbano condividere lo stesso
  `base_version_key` in fondo alla catena (`MismatchedBaseVersionError`, `branch.py:58-63`) — cioè
  esistono già DUE nozioni di "genitore" che devono restare coerenti a mano, non una sola;
  ha un **ciclo di vita esplicito**: `SCENARIO_STATE` (`ibp/domain/scenario.py:20-27`) —
  `Draft -> Evaluated -> Promoted|Discarded`, con `Evaluated -> Draft` ammesso (un nuovo edit rimette in
  lavorazione) e `Promoted`/`Discarded` terminali;
- porta contenuto **sparso**: ogni modifica è una riga di `overlay` (`db/schema.sql`, tabella `overlay`)
  alla grana `(scenario_id, version_key, date_key, measure_key, product_key | plant_key)` — **una grana
  più larga** di quella piena di `TSOP_DEMAND`/`TSOP_OPS` (`overlay` non porta `division_key`/`region`
  lato demand né `manufact_key`/`division_key`/`region` lato ops, vedi `CellKey`,
  `ibp/scenario/models.py:22-61`);
- risolto **a runtime, mai materializzato**: leggere una cella (`resolve_cell()`,
  `ibp/scenario/overlay.py:357`) o l'intero scenario (`materialize_ref()`, `overlay.py:285`) attraversa la
  catena di `scenario` genitori e infine il base ad ogni chiamata — non esiste una tabella con "il valore
  corrente risolto" finché non si promuove.

**Un'istanza `DVERSIONS` promossa** è, al contrario:
- identificata da `version_key: BIGINT` (autoincrement applicativo, `MAX(version_key)+1`,
  `ibp/scenario/promote.py:337-339`) e da un `version_name` che segue una **grammatica fissa**
  `SOP_{YYYY}_{MM}_{SIDE}_{STATUS}` (`_version_name()`, `promote.py:60-65`) — un vincolo esterno non
  negoziabile: le misure DAX di Power BI ricostruiscono questi nomi come stringhe (D3, D7);
- **priva di ogni nozione di genitore**: nessuna colonna su `DVERSIONS` punta allo scenario che l'ha
  generata. L'unico legame è quello che `promote()` sceglie di scrivere nel nome
  (`cycle_year`/`cycle_month`/`side`/`status`, decisi dal chiamante, non derivati dallo scenario) — dopo
  l'`INSERT`, sapere "questa versione viene dallo scenario SCN-xxxx" richiede di sapere fuori banda quale
  `promote()` l'ha creata; non è nello schema;
- **priva di ciclo di vita del tipo `SCENARIO_STATE`**: ha solo `is_budget`/`is_frozen` (booleani) e
  `status` (`P`/`R`/`A`/`C` — la **fase del ciclo S&OP**, un concetto ortogonale al lifecycle di uno
  scenario, non uno stato "Draft/Evaluated/Promoted");
- porta contenuto **denso e materializzato**: righe piene in `TSOP_DEMAND`/`TSOP_OPS` con tutte le
  coordinate (`division_key`, `region`, `manufact_key`) — non uno stack di delta da risolvere, un fatto
  scritto;
- **mai più mutata**: `promote()` non scrive mai su un `version_name` esistente
  (`DuplicateVersionError`, `promote.py:56-57,300-301`) — ogni promozione crea un `version_key` nuovo.

In sintesi: **non esistono oggi "piani salvati" come categoria distinta dagli scenari** — esistono
`DVERSIONS`, che sono sempre state "il trunk" fin dal seed (i cicli P/R/A/C ufficiali), e `scenario`, che
sono sempre rami temporanei destinati a scomparire (restando `Discarded`) o a essere fusi copiando il
loro contenuto risolto in una **nuova, distinta riga `DVERSIONS`** (`Promoted`). Il "trunk" e il "ramo"
non sono la stessa specie di oggetto: vivono in tabelle diverse, con PK di tipo diverso, con un modello
di contenuto diverso (denso vs sparso), risolti con meccaniche diverse (lettura diretta vs COALESCE su
uno stack), e con macchine a stati diverse (o assenti).

### Cosa fanno esattamente `branch()`, `promote()` e la risoluzione overlay

**`branch(con, *, name, base_version_key: int, owner, parent_scenario_id=None, ...)`**
(`ibp/scenario/branch.py:28-96`):
1. Verifica che `base_version_key` esista in `DVERSIONS` (`version_exists`).
2. Se annidato, verifica che il genitore condivida lo stesso `base_version_key` (altrimenti
   `MismatchedBaseVersionError` — l'invariante che rende AC15 vera: uno scenario annidato non può
   mescolare overlay scritti sotto basi diverse).
3. Calcola `base_snapshot_id = f"SNAP_{base_version_key}_{base_content_digest(con, base_version_key)}"` —
   un'**impronta di contenuto** (SHA-256 su ogni riga di `TSOP_DEMAND`/`TSOP_OPS` per quella
   `version_key`, ordinata deterministicamente, `overlay.py:308-333`), non un timestamp: è ciò che
   `promote()` ricalcolerà per rilevare una base mossa (AC16).
4. Inserisce **una sola riga** nella tabella `scenario`, in stato `Draft`. **Non scrive mai** una riga
   `DVERSIONS`: uno scenario what-if non è mai membro di quella tabella finché non è promosso.

**Risoluzione overlay** (`ibp/scenario/overlay.py`): la catena radice -> foglia di scenari annidati
(`scenario_chain()`, `overlay.py:51-72`, che rileva anche cicli come dato corrotto) è la struttura su cui
si applica lo stack: `apply_overlay_layer()` (`overlay.py:239-257`) sostituisce (mai somma) il valore di
una slice per ogni layer non-tombstone, o la rimuove per un tombstone — la stessa logica di
`COALESCE(l3, l2, l1, base)` della spec D3, ma implementata come un fold Python su dizionari, non come
una query SQL con `COALESCE`.

**`promote(con, scenario_id, *, cycle_year, cycle_month, side, status, user)`**
(`ibp/scenario/promote.py:257-383`): l'unica funzione che fa collassare uno scenario in un oggetto della
stessa specie di un piano ufficiale. In ordine:
1. Convalida `side` contro `DVERSIONS.side` della base (`SideMismatchError`) e l'unicità del
   `version_name` risultante (`DuplicateVersionError`) — **prima** di validare la transizione di stato.
2. Valida `scenario.transition_to("Promoted")` (fallisce presto su uno scenario non `Evaluated`, senza
   toccare il DB).
3. `_snapshot_check()` (righe 223-254) rileva se la base si è mossa dal branch time — solo per gli
   scenari il cui `base_snapshot_id` è nel formato di `branch()` (`_SNAPSHOT_RE`); altrimenti la
   promozione procede **senza verifica**, e `PromotionResult.base_verified=False` lo dichiara al
   chiamante invece di fingere un controllo riuscito.
4. `overlay_touched_slices()` isola l'insieme esatto di slice scritte/cancellate dall'intera catena;
   `_materialize_demand`/`_materialize_ops` copiano ogni riga base **non toccata** byte per byte e
   ripartiscono (`_shares()`, con guardia sulla grandezza per evitare l'esplosione numerica su valori che
   si cancellano quasi esattamente) solo le slice overlay-ate che coprono più righe base.
5. In un'unica transazione: nuova riga `DVERSIONS` (nuovo `version_key`, nome dalla grammatica fissa),
   bulk insert in `TSOP_DEMAND`/`TSOP_OPS`, `scenario.state = 'Promoted'`.

**Cosa identifica "questa è una promozione di scenario" dopo il fatto:** oggi, **nulla di strutturale**.
Il `version_name` assemblato da `promote()` segue la stessa identica grammatica `SOP_YYYY_MM_SIDE_STATUS`
usata dal seed per i cicli ufficiali — non c'è un prefisso, un flag, o una colonna che distingua "questa
`DVERSIONS` viene da una promozione" da "questa `DVERSIONS` viene dal seed". La provenienza a livello di
singola riga (`copied` | `overlay_override` | `prorated`) è calcolabile — `overlay_touched_slices()` la
conosce esattamente — ma viene **buttata via** dopo la scrittura (decisione D3, correzione pianificata in
T11.1/T11.2, non ancora implementata: richiede una tabella laterale, perché `TSOP_DEMAND`/`TSOP_OPS`
devono restare isomorfe al mirror dEPM).

### Cosa dovrebbe cambiare per convergere verso il modello R-001

Un trunk unico in cui **sia i piani salvati sia gli scenari salvati sono branch dello stesso tipo**
(come in Kinaxis RapidResponse, dove non esiste una distinzione strutturale fra "lo scenario ufficiale" e
"un what-if": entrambi sono nodi dello stesso albero, e "promuovere" significa spostare un puntatore, non
cambiare specie di oggetto) richiede di toccare cinque punti, in ordine di quanto sono fondativi:

1. **Unificare i due spazi di identità (`scenario` vs `DVERSIONS`) in un solo tipo di nodo versionato.**
   Oggi un branch può avere come genitore *o* un `DVERSIONS.version_key` (`base_version_key: int`, un
   puntatore a una tabella diversa) *o* un altro `scenario` (`parent_scenario_id: str`, un puntatore
   nella stessa tabella) — due meccanismi diversi che `branch()` deve tenere manualmente coerenti
   (`MismatchedBaseVersionError`). In un trunk unico ogni nodo (che rappresenti "il piano ufficiale
   corrente" o "un what-if in corso") avrebbe un solo tipo di puntatore al genitore, dello stesso tipo per
   qualunque genitore. Questo implica far collassare `DVERSIONS` e `scenario` in una sola tabella/entità
   concettuale, o quantomeno dare a `DVERSIONS` lo stesso meccanismo di parent-pointer che oggi ha solo
   `scenario`.

2. **Far scrivere agli edit sulla stessa grana dei fatti, non su una grana più larga.** Il motivo per cui
   `promote()` deve *materializzare* (copiare righe dense in una tabella diversa) invece di limitarsi a
   spostare un puntatore è che `overlay` strutturalmente non può rappresentare una riga
   `TSOP_DEMAND`/`TSOP_OPS` completa: non porta `division_key`/`region`/`manufact_key`
   (`UnmaterializableCellError` è la prova diretta di questo limite — una cella overlay-ata senza riga
   base da cui ereditare quelle coordinate non è promuovibile). Finché "un ramo" e "il trunk" hanno un
   modello di contenuto diverso (sparso con riparto vs denso), la promozione **deve** restare
   un'operazione di copia con perdita di reversibilità (`_shares()` prorata, non preserva l'informazione
   originale su come le righe si sarebbero dovute dividere se l'edit non fosse mai avvenuto). R-001
   richiede che un "piano" possa esistere come pura sequenza di edit overlay sopra il proprio genitore,
   esattamente come uno scenario oggi — il che vuol dire estendere `overlay`/`edits` alla grana piena, o
   accettare che "il trunk" non abbia mai una tabella dei fatti densa indipendente, solo overlay
   ricorsivi fino alla radice dell'albero.

3. **Trasformare `promote()` da "copia materializzante" a "spostamento di riferimento".** Con identità
   unificata (punto 1) e grana unificata (punto 2), promuovere un ramo a "piano ufficiale" potrebbe
   diventare un'operazione O(1) — spostare un nome/etichetta (`SOP_2026_09_DEMAND_A`) a puntare al nodo
   che era lo scenario, invece di ricopiare ogni riga di `TSOP_DEMAND`/`TSOP_OPS`. Oggi questo non è
   possibile perché la grammatica dei nomi (`version_name`) è una colonna `UNIQUE` di una riga
   `DVERSIONS`, e `DVERSIONS` non è lo stesso tipo di riga di `scenario` — la grammatica di naming
   dovrebbe diventare un'etichetta applicabile a un nodo qualunque dell'albero, non il formato della PK di
   un'intera tabella.

4. **Rendere omogenea la catena di risoluzione fino alla radice.** Oggi la catena si ferma sempre a un
   `base_version_key` che è letto **direttamente** da `TSOP_DEMAND`/`TSOP_OPS` come dato denso
   (`base_cell_value()`, `materialize_version()`) — un "fondo" strutturalmente diverso dai layer sopra.
   Un trunk vero avrebbe una root esplicita (es. il primo seed, cycle 0) e ogni nodo sopra — trunk
   ufficiale o ramo what-if — risolto con la **stessa** meccanica ricorsiva di `apply_overlay_layer()`,
   non con un salto a una tabella diversa a un livello arbitrario dell'albero.

5. **Disaccoppiare le due macchine a stati oggi asimmetriche.** `SCENARIO_STATE`
   (Draft/Evaluated/Promoted/Discarded) vive solo su `scenario`; `DVERSIONS.status` (`P`/`R`/`A`/`C`,
   fase del ciclo S&OP) e `is_frozen`/`is_budget` vivono solo su `DVERSIONS` — e sono concetti
   ortogonali (lifecycle di un what-if vs fase del processo di pianificazione), oggi confusi dal fatto che
   uno vive solo su una tabella e l'altro solo sull'altra. Un nodo unico dovrebbe poter portare entrambi
   gli assi indipendentemente: un ramo "ufficiale" può essere in una fase di ciclo (`P`/`R`/`A`/`C`) e
   contemporaneamente avere un proprio lifecycle di lavorazione (bozza/valutato); un ramo what-if oggi non
   ha alcuna nozione di fase di ciclo perché quel concetto vive solo su `DVERSIONS`.

**Cosa NON richiederebbe modifiche sostanziali:** `ScenarioStack`/`cache_key()`
(`ibp/scenario/models.py:94-109`, la chiave di isolamento per AC15) generalizza già correttamente
l'idea di "un puntatore di base più una catena ordinata di nodi sovrapposti" — sostituire
`base_version_key: int` con "l'id del nodo genitore, dello stesso tipo di uno `scenario_id`" e rendere la
catena uniforme (nodi, non "scenari sopra una versione") è un'estensione diretta di un'astrazione che
esiste già, non una riscrittura. Allo stesso modo, `overlay_touched_slices()` e la logica di tombstone
(`is_deleted`, mai `NULL` come sentinella) restano valide indipendentemente da come viene risolto il
punto 2: sono già corrette per un modello a grana sparsa, qualunque sia la tabella di fondo.

**Debito di modellazione già visibile come sintomo:** l'incoerenza fra il formato di `base_snapshot_id`
prodotto dal seed pre-T4 (`SNAP_{version_name}_{iso_ts}`, un'etichetta) e quello prodotto da `branch()`
(`SNAP_{version_key}_{sha256}`, un'impronta di contenuto) — gestita oggi con un `bool` doppio
(`verified`, `moved`) invece di un formato unico — è un'anteprima in piccolo del tipo di migrazione che
un'unificazione del trunk dovrebbe affrontare su scala più larga: due generazioni di codice che modellano
"cos'è la base di un ramo" in modo diverso, riconciliate con un livello di tolleranza esplicito invece che
con un formato comune fin dall'inizio.

---

*Analisi architettura: 2026-09-19*
