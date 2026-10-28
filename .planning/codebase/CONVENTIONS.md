# Convenzioni di Codice

**Data di analisi:** 2026-09-19

## Ambito dell'analisi

Codice di prodotto: `ibp/` (dominio, semantic layer, motore di ricalcolo, scenari) e `db/`
(schema + seed). Test: `tests/`. `data/`, `.software-house/` e `.claude/` sono esclusi
(gitignored/tooling esterno).

## Naming Patterns

**File:**
- Un modulo per area/responsabilità, nome minuscolo con underscore: `ibp/domain/errors.py`,
  `ibp/engine/aggregate.py`, `ibp/scenario/overlay.py`.
- Ogni package (`ibp/domain/`, `ibp/engine/`, `ibp/scenario/`, `ibp/semantic/`) ha un proprio
  `errors.py` dedicato (vedi sezione Error Handling) e un proprio `__init__.py` che ri-esporta
  la superficie pubblica.

**Funzioni:**
- `snake_case` ovunque, verbo esplicito quando l'azione ha effetto (`branch()`, `promote()`,
  `mark_evaluated()`, `materialize_version()`, `resolve_cell()`).
- Funzioni "private" al modulo (helper non pensati per l'uso esterno) prefissate con `_`:
  `_persist_state`, `_fold_numeric`, `_eligible_plant_for`, `_compute_dmd_cell`.

**Variabili/costanti:**
- Costanti di modulo in `UPPER_SNAKE_CASE`: `SCENARIO_TRANSITIONS`, `MEASURE_DAG`,
  `FORBIDDEN_CAPACITY_NUMBERS`, `_MEASURE_TABLE`.
- Le chiavi di dominio hanno sempre il suffisso `_key` (`plant_key`, `version_key`,
  `measure_key`, `manufact_key`) per distinguerle da codici leggibili (`plant_code`,
  `version_name`).

**Tipi/classi:**
- `PascalCase` per dataclass e classi (`CellKey`, `ResolvedCell`, `ScenarioStack`,
  `RecalcEngine`, `StateMachine`).
- Le eccezioni terminano sempre in `Error` e derivano da una base di package dedicata (vedi
  sotto): `NonAdditiveMeasureError`, `MismatchedBaseVersionError`, `CellVersionMismatchError`,
  `SideMismatchError`, `UnknownStateError`, `InvalidTransitionError`.

## Stile del Codice

**Formattazione:**
- Nessun formatter/linter configurato nel repository (nessun `.flake8`, `.pylintrc`,
  `ruff.toml`, `black` config in `pyproject.toml`). Lo stile è tenuto uniforme manualmente,
  non imposto da tooling automatico — verificarlo a occhio quando si aggiunge codice.
- `from __future__ import annotations` come prima riga di codice (dopo il docstring di modulo)
  in ogni file `.py` di `ibp/` e `db/`: consente `int | None`, `"Scenario"` come stringa non
  necessaria per i forward reference, e le annotazioni posticipate.
- Type hint quasi ovunque su firme di funzione pubbliche e su campi di dataclass; uso sistematico
  della sintassi `X | None` (PEP 604), mai `Optional[X]`.

**Linting:**
- Non presente come tool. La disciplina è imposta da **test AST strutturali** (vedi TESTING.md):
  `test_domain_ac10_erp_boundary.py`, `test_db_single_entrypoint.py`,
  `test_semantic_ac2_master_data.py` scansionano il sorgente con `ast` invece di grep testuale,
  per non essere elusi da forme equivalenti (`30.0`, `"30"`, `29 + 1`).

## Organizzazione degli Import

**Ordine osservato (esempio `ibp/engine/engine.py`):**
1. `from __future__ import annotations`
2. stdlib (`heapq`, `itertools`, `math`, `collections.abc`)
3. import relativi al package genitore (`from ..semantic import dimensions, graph, measures`)
4. import relativi al proprio package (`from . import aggregate, dates`, `from .cells import (...)`)
5. import dell'ultimo modulo di errori del proprio package (`from .errors import UnknownCellEditError`)

**Import relativi, non assoluti, all'interno di `ibp/`:**
- `from ..domain.scenario import Scenario` (risalita di un livello), `from .errors import (...)`
  (stesso package). Nessun modulo interno a `ibp/` importa `ibp.xxx` in forma assoluta.

**Alias:**
- Alcuni moduli importano sotto-moduli propri con underscore-prefix per marcarli come dettaglio
  interno pur restando importabili: `from . import dimensions as _dimensions` in
  `ibp/semantic/registry.py`.

**Nessun path alias/bundler**: è un package Python puro (`pip install -e .`,
`pyproject.toml` → `[tool.setuptools.packages.find] include = ["ibp*"]`).

## Error Handling

**Principio cardine (esplicito nei docstring di ogni `errors.py`):** un guasto di dominio deve
sollevare un tipo specifico e riconoscibile, mai un `ValueError`/`Exception` generico, e mai
fallire in silenzio restituendo un valore plausibile ma sbagliato. Citazione da
`ibp/scenario/errors.py`: *"un guasto riconoscibile per tipo, mai un `ValueError` generico né,
peggio, un fallimento silenzioso (branch/edit/compare/promote non devono mai tornare un
risultato plausibile ma sbagliato)"*.

**Gerarchia per package**, ciascuno con una eccezione base che eredita direttamente da
`Exception` (non condivisa fra package):
- `ibp/domain/errors.py`: `DomainError` → `UnknownStateError`, `InvalidTransitionError`,
  `PhaseClosedError`.
- `ibp/engine/errors.py`: `EngineError` → `UnknownCellEditError`.
- `ibp/scenario/errors.py`: `ScenarioError` → `UnknownVersionError`, `UnknownScenarioError`,
  `InvalidCellKeyError`, `ScenarioWriteRejectedError`, `DuplicateVersionError`,
  `PromotionConflictError`, `UnknownMeasureError`, `NonAdditiveMeasureError`,
  `MismatchedBaseVersionError`, `CellVersionMismatchError`, `SideMismatchError`,
  `UnmaterializableCellError`.

Verificato contro il codice (`ibp/domain/errors.py`, `ibp/engine/errors.py`,
`ibp/scenario/errors.py`): tutte le classi elencate esistono con questo esatto nome e questa
esatta relazione di ereditarietà.

**Eccezione alla regola (nota, non un bug):** `ibp/semantic/graph.py:64` dichiara
`GraphSnapshotLimitationError(ValueError)` — eredita da `ValueError`, non da una base dedicata
al package `ibp.semantic` (che non ha un proprio `errors.py`). Se si aggiunge altro codice di
errore in `ibp/semantic/`, valutare se allinearlo allo stesso pattern usato da
`domain`/`engine`/`scenario` invece di continuare a estendere `ValueError` direttamente.

**Ogni eccezione di dominio porta i dati strutturati della violazione come attributi**, non solo
un messaggio testuale — es. `CellVersionMismatchError.__init__` salva `scenario_id`,
`scenario_base_version_key`, `cell_version_key` come attributi dell'istanza oltre a comporre il
messaggio. Questo permette al chiamante (o a un test) di ispezionare la causa senza fare parsing
di stringhe.

**`raise ... from None`** quando l'eccezione originale (tipicamente un `KeyError` di lookup) non
aggiunge informazione utile al chiamante: `ibp/domain/state_machine.py` —
`raise UnknownStateError(self.name, state) from None` dentro un `except KeyError:`.

**Transazioni esplicite con rollback su `except Exception: ... raise` (bare re-raise)**: pattern
ripetuto in `ibp/scenario/branch.py` (due occorrenze), `ibp/scenario/edits.py`,
`ibp/scenario/promote.py` — `con.execute("BEGIN TRANSACTION")` seguito da `try/except Exception:
con.execute("ROLLBACK"); raise`. Nota di debito tecnico già registrata a livello di progetto
(`.planning/intel/context.md`, pacchetto **T10.1**): il `BEGIN TRANSACTION` è "nudo" (nessun
context manager dedicato) ed è un prerequisito bloccante per T10 (l'API HTTP). Non introdurre
nuovo codice che ripete questo pattern senza consultare quel pacchetto.

## Docstring e Commenti

**Ogni modulo ha un docstring di apertura che spiega il "perché", non solo il "cosa"**: cita la
decisione di design, il difetto storico chiuso (spesso con riferimento a "il critic" o "il
tester" e il task/AC coinvolto), e il vincolo che il codice sottostante rispetta. Esempio,
`ibp/engine/engine.py`: il docstring di modulo di ~40 righe elenca cosa il motore *non* fa,
perché `confirmed_production` è un secondo nodo radice, e come funziona lo spread a due mesi —
prima di qualsiasi riga di codice.

**Le docstring di funzione spiegano l'invariante o il vincolo, non ripetono la firma**: es.
`materialize_version()` in `ibp/scenario/overlay.py` dedica un intero paragrafo al perché la
somma non si fa con `SUM(...) GROUP BY` lato SQL (vedi CONVENTIONS → determinismo).

**Riferimenti incrociati a task/AC nei commenti**: `AC2`, `AC10`, `AC12`, `AC15`, `AC16`, `T3`,
`T4`, `F7`, `F8`, `D3`/`D4`/`D5`/`D7` compaiono nei docstring come ancore verso
`docs/01-plan-m1.md`/`docs/02-spec-m1-corrente.md`/`docs/ADR-001-decisioni-dominio.md`. Quando si
aggiunge codice che implementa o corregge un AC, riportare il numero dell'AC nel docstring del
modulo o della funzione, non solo nel messaggio di commit.

**Lingua:** tutti i docstring e i commenti sono in italiano. I nomi di identificatori (classi,
funzioni, variabili, colonne SQL) sono in inglese. Mantenere questa convenzione per codice nuovo.

## Determinismo (verificato contro il codice)

Tre regole esplicite, tutte confermate leggendo il sorgente:

**1. `ORDER BY` sulla chiave primaria completa + somma in Python, mai `SUM(...) GROUP BY` parallelo.**
Verificato in `ibp/scenario/overlay.py::materialize_version()`: le due query SQL portano
`ORDER BY product_key, date_key, measure_key, division_key` (lato demand) e
`ORDER BY plant_key, date_key, measure_key, manufact_key, product_key, division_key` (lato ops),
seguite da un accumulo Python (`out[...] += float(value)`) invece di un `SUM(...) GROUP BY` SQL.
Stesso pattern in `ibp/scenario/promote.py::_base_slice_totals` (righe 95-136, `ORDER BY
product_key, date_key, measure_key, division_key` / `ORDER BY plant_key, date_key, measure_key,
manufact_key, product_key, division_key`). Motivazione testuale nel codice: il `SUM` parallelo di
DuckDB su una base con 100k+ righe non garantisce lo stesso ordine di riduzione fra due
esecuzioni identiche — due chiamate indipendenti potrebbero differire nell'ultimo bit (~1e-13),
che `compare()` leggerebbe come migliaia di celle "cambiate" senza che nessuno le abbia toccate.
L'`ORDER BY` fissa un ordine totale (dato `version_key` fisso) e la somma Python nello stesso
ordine dà sempre lo stesso bit pattern.

**2. I test asseriscono `==`, non `math.isclose`.** Verificato in
`tests/test_engine_ac10_recalc_equivalence.py` e nel suo helper
`tests/_engine_support.py::assert_matches_full_recalculate` (righe 157+): il confronto fra
`recalculate()` e `full_recalculate()` è **esatto**. Il file espone comunque
`values_close(a, b, *, rel_tol=0.0, abs_tol=0.0)` (righe 111-138) come util configurabile — ma con
tolleranza zero di default, cioè `==` in pratica — "ancora configurabile" per un caso futuro che
richiedesse tolleranza, non usato oggi. Il motore stesso somma su `sorted(...)` (ordine totale
esplicito) proprio per rendere il confronto esatto possibile: prima di questa correzione la somma
iterava su `set` non ordinati e serviva `math.isclose`.

**3. RNG deterministico via `hashlib`, mai il builtin salato `hash()`.** Verificato in
`db/seed/common.py:59-62`: `digest = hashlib.sha256(f"{SEED}:{stream}".encode("ascii")).hexdigest()`,
con commento esplicito sul motivo (`hash()` di stringa in Python è salato per processo per
sicurezza e cambierebbe la seed a ogni esecuzione). Stesso pattern in
`ibp/scenario/overlay.py:310-316` per l'impronta di contenuto del base (`base_content_digest`,
usata da AC16 per rilevare una base mossa): `hashlib.sha256()` su un flusso ordinato di righe, mai
`hash()`. Nessuna occorrenza del builtin `hash()` trovata nel codice di prodotto (`ibp/`, `db/`).

**Implicazione per codice nuovo:** qualunque aggregazione che alimenti un confronto scenario/base
(`compare()`, `promote()`, AC16) deve seguire lo stesso pattern — `ORDER BY` esplicito sulla
chiave primaria disponibile + riduzione in Python — non un `GROUP BY` lato SQL su colonne
float. Qualunque nuovo bisogno di riproducibilità (seed, digest, campionamento deterministico)
deve passare da `hashlib`, mai da `hash()`.

## Magic Number Banditi dai File `.py`

**Regola (AC2):** i valori di capacità (`max_slots`, il fattore di granularità, le soglie) non
compaiono come literal in nessun file `.py` di codice di calcolo — vivono in
`db/seed/data/plant_master.json`. Le fasi del ciclo (day range, `stat_state`, gate) vivono in
`db/seed/data/process_phases.json`.

**Verificato:** `test_semantic_ac2_master_data.py::test_no_capacity_literals_in_calculation_code`
esegue uno scan **AST** (non testuale — elude `30.0`, `"30"`, `29 + 1`) su ogni root di calcolo
esistente (`ibp/semantic/`, `ibp/engine/`; `ibp/capacity/` quando esisterà), cercando i valori
proibiti `{30, 8, 500}` come `int`/`float`/combinazione aritmetica immediata di letterali, o come
stringa `"30"`/`"8"`/`"500"`. L'unica occorrenza residua del carattere `8` nel codice è l'idioma
`encoding="utf-8"`, esplicitamente escluso perché non è un valore di capacità (nota anche in
`README.md`). Il test include anche un controllo di non-vacuità
(`test_capacity_literal_scan_actually_detects_evasive_forms`) che verifica che lo scanner
riconosca davvero le forme elusive su un frammento sintetico.

**Implicazione per codice nuovo:** qualunque soglia di capacità aggiunta a `ibp/engine/` o a un
futuro `ibp/capacity/` deve essere letta da master data (`DPLANT`/`plant_master.json` o
equivalente), mai scritta come literal — il test la intercetterebbe.

## Design delle Funzioni

**Dimensione:** funzioni di dominio tipicamente brevi (10-40 righe di codice, spesso con
docstring più lungo del corpo). Le funzioni con logica più corposa (`RecalcEngine.recalculate`,
`ibp/scenario/promote.py::promote`) restano comunque a singola responsabilità dichiarata nel
docstring.

**Parametri:** connessione DB (`con`) sempre come primo parametro esplicito, mai riaperta
internamente — vedi convenzione "single entrypoint" sotto.

**Valori di ritorno:** oggetti di dominio tipati (dataclass), non tuple/dict posizionali, per le
API pubbliche di package (`Scenario`, `PromotionResult`, `ResolvedCell`, `RecalcResult`,
`CutoffStats`). `dict`/`tuple` usati solo come strutture interne di calcolo
(`materialize_version() -> dict[tuple, float]`).

## Design dei Moduli

**Nessuna funzione in `ibp/` apre una propria connessione DuckDB.** Contratto esplicito,
verificato strutturalmente: `tests/test_db_single_entrypoint.py` fa uno scan **AST** del
sorgente e verifica che `ibp/db.py` sia l'unico punto in cui compare l'apertura di una
connessione DuckDB nel package `ibp` — ogni altro modulo riceve `con` come parametro. Docstring
di conferma anche in `ibp/scenario/overlay.py`: *"Nessuna funzione qui apre una connessione
propria (`con` è sempre ricevuto, mai `ibp.db.connect()`) — stesso contratto di `ibp.semantic`"*.

**Export:** ogni package usa `__all__` esplicito nei moduli che ri-espongono simboli di un altro
livello (`ibp/scenario/models.py` ri-esporta `Scenario` da `ibp.domain.scenario` con `__all__`
dichiarato).

**Dataclass immutabili:** `@dataclass(frozen=True)` per i value object di dominio (`CellKey`,
`Scenario`, `StateMachine`, `PlantCapacity`); le transizioni di stato non mutano l'istanza ma ne
producono una nuova (`dataclasses.replace`, vedi `Scenario.transition_to`).

**Validazione negli `__post_init__`:** invarianti strutturali (es. `CellKey` — esattamente uno
fra `product_key`/`plant_key` valorizzato) verificate in `__post_init__` con l'eccezione di
dominio appropriata (`InvalidCellKeyError`), non lasciate a un controllo a valle.

---

*Analisi convenzioni: 2026-09-19*
