# Pattern di Testing

**Data di analisi:** 2026-09-19

## Framework di Test

**Runner:**
- `pytest==8.3.3` (pin esatto in `pyproject.toml`, dipendenza base — non nell'extra `[forecast]`).
- Nessun file di configurazione dedicato (`pytest.ini`, `pyproject.toml [tool.pytest.ini_options]`,
  `setup.cfg` sono assenti): comportamento pytest di default, discovery automatica su `tests/`.

**Libreria di asserzione:**
- `assert` nativo di pytest (nessun `unittest.TestCase`, nessuna libreria di assertion
  aggiuntiva).

**Comandi:**
```powershell
python -m pytest -q          # tutta la suite
python -m pytest tests/test_engine_ac10_recalc_equivalence.py -q   # un solo file
python -m pytest -k ac16 -q  # filtro per nome (tutti i test AC16)
```
Nessuna modalità watch/coverage configurata nel repository (nessun `pytest-cov`,
`pytest-watch` in dipendenze).

**Stato della suite (verificato in questa sessione, 2026-09-19):**
```
python -m pytest -q
187 passed in ~111s
```
Suite **verde**. Nota: la suite richiede `data/ibp.duckdb` prodotto da `python db/build_db.py`
(T1) — su un checkout pulito senza quel file, i test che dipendono dal DB reale sono skippati con
motivo esplicito, non falliti (vedi `tests/conftest.py::_require_db`), a meno che `data/` esista
ma sia vuota/incompleta (build T1 rotto a metà), nel qual caso il test fallisce esplicitamente
invece di skippare — per non far leggere un build rotto come verde.

## Convenzione di Naming: file di test = Acceptance Criteria

**Questa è la convenzione portante della suite.** Molti file `tests/test_*.py` sono nominati
`test_<area>_ac<N>_<descrizione>.py`, dove `<N>` è il numero dell'Acceptance Criteria che quel
file verifica (gli AC sono definiti in `docs/01-plan-m1.md`/`docs/02-spec-m1-corrente.md`). Il
numero AC non è decorativo: è il modo in cui la pianificazione a valle sa quale criterio ha già
copertura e quale no. Quando si aggiunge un test per un AC nuovo o non ancora coperto, seguire
lo stesso schema di nome.

Non tutti i file seguono lo schema `ac<N>`: alcuni verificano un contratto strutturale
trasversale (es. "un solo entrypoint DB") o un difetto emerso durante lo sviluppo T2-T4 (non
tracciato come AC numerato) — questi sono elencati separatamente sotto.

### Mappa completa: file di test → cosa verifica

**Test nominati per AC:**

| File | AC | Cosa verifica |
|---|---|---|
| `tests/test_semantic_ac2_master_data.py` | AC2 | Le regole di capacità (`max_slots`, granularità, soglie) sono master data su `DPLANT`/`db/seed/data/plant_master.json`, mai literal in codice di calcolo. Include lo scan AST anti-magic-number (`test_no_capacity_literals_in_calculation_code`) e il test che aggiunge un plant a runtime senza toccare Python. |
| `tests/test_domain_ac10_erp_boundary.py` | AC10 (confine ERP) | Nessuna entità/classe di dominio nominata come ordine/BOM/MRP (`ibp.domain` non deve replicare concetti ERP-transazionali). Scan sia su `dir(domain)` sia via AST sulle `ClassDef` del sorgente. |
| `tests/test_engine_ac10_recalc_equivalence.py` | AC10 (equivalenza di ricalcolo) | Il test cardine del motore: `recalculate()` (propagazione dirty sul sottografo) deve produrre risultati **esattamente identici** (`==`) a `full_recalculate()` sullo stesso stato, su sequenze di edit incluse 8 sequenze casuali da 15 batch (`@pytest.mark.parametrize("seed", range(8))`). |
| `tests/test_engine_ac11_cutoff.py` | AC11 | L'early cutoff è misurato (`CutoffStats`), non solo promesso: direzione corretta per edit no-op vs edit reale, invariante `visited == computed + cutoff + absent` verificato a ogni chiamata. |
| `tests/test_engine_ac12_aggregate.py` | AC12 | `min`/`max`/`ratio` si ricalcolano sul gruppo, mai per delta — test diretti su `ibp/engine/aggregate.py` (`combine`/`combine_ratio`/`is_delta_safe`). |
| `tests/test_scenario_ac13_promotion.py` | AC13 | `branch → edit sparso → compare → promote` crea una **nuova** istanza `DVERSIONS` (mai una mutazione di un'istanza esistente); verifica il nome esatto prodotto (portante per le misure DAX Power BI), parametrizzato su `side`/`status` (`DEMAND/P`, `DEMAND/R`, `SUPPLY/A`, `SUPPLY/C`). |
| `tests/test_scenario_ac14_tombstone.py` | AC14 | Una cella cancellata in uno scenario (`is_deleted=TRUE` esplicito) non deve mai ricomparire dal base; mai `value=NULL` come sentinella implicita. |
| `tests/test_scenario_ac15_isolation.py` | AC15 | La cache/lettura di uno scenario non deve mai includere celle di uno scenario fratello — copre sia la lettura diretta (`resolve_cell`/`materialize`) sia la catena di scenari annidati. |
| `tests/test_scenario_ac16_conflict.py` | AC16 (conflitto a runtime) | Promozione con base mossa dal branch time: conflitto rilevato **prima** di qualunque scrittura (nessuna riga `DVERSIONS`/`TSOP_DEMAND`/`TSOP_OPS` parziale, nessun cambio di stato dello scenario). |
| `tests/test_seed_ac16_snapshot.py` | AC16 (validità del seed) | Il seed deve produrre scenari su cui AC16 verifichi *davvero* qualcosa: `base_snapshot_id` deve essere un'impronta di contenuto (digest), non un'etichetta `SNAP_{version_name}_{iso_ts}` che renderebbe la promozione tollerante per costruzione. |

**Test strutturali/di contratto non numerati per AC (ma riferiti a T2/T3/T4 "done_when" o a difetti reali chiusi durante lo sviluppo):**

| File | Cosa verifica |
|---|---|
| `tests/test_db_single_entrypoint.py` | T2 done_when #5: `ibp/db.py` è l'unico punto di apertura di connessioni DuckDB in `ibp/` — verificato via scan AST, non ispezione manuale. |
| `tests/test_domain_state_machines.py` | T2 done_when #1: ogni transizione di stato dichiarata deve riuscire, ogni transizione illegale deve sollevare l'eccezione specifica (mai `Exception` generica, mai fallimento silenzioso). Copre tutte le macchine a stati di `ibp.domain` più il caso `STAT_03` (tocca AC4/AC20, non ha file dedicato per quei numeri). |
| `tests/test_engine_clone_isolation.py` | Verifica l'infrastruttura di test stessa (`_engine_support.clone_engine()`): un difetto lì produrrebbe falsi negativi/positivi indistinguibili da un bug reale del motore — copre il difetto reale trovato dal critic T3 (stato mutabile condiviso fra cloni). |
| `tests/test_engine_confirmed_production_root.py` | Chiude il difetto T3 per cui `confirmed_production` era un secondo nodo radice eseguito dal motore ma assente da `MEASURE_DAG` dichiarato — ora `MEASURE_DAG["confirmed_production"]` esiste con `depends_on=()`. |
| `tests/test_engine_invalid_edit_keys.py` | Regressione su un difetto misurato dal critic ("nessun test esercita un `manufact_key` non valido"): un `ConfirmedProductionEdit` con `manufact_key` inesistente deve fallire *prima* di scrivere stato, non a metà propagazione. Parametrizzato su tipo di edit e posizione nel batch (`alone`/`first`/`last`). |
| `tests/test_engine_sparse_rate_card.py` | `rate_card` copre solo 4/14 `manufacturing_category`: una cella `gap_req_conf` senza tariffa applicabile deve risultare **assente** (`absent`/non presente in dict), mai `value_gap == 0.0` (0.0 si leggerebbe come "nessun value gap", un'affermazione positiva diversa da "non sappiamo"). |
| `tests/test_scenario_compare.py` | `compare(ref_a, ref_b)` funziona su tutte e tre le combinazioni (versione/versione, scenario/scenario, versione/scenario); il caso "scenario contro il proprio base" riporta solo le celle davvero sovrascritte. |
| `tests/test_scenario_proration.py` | Decisione dell'implementatore non imposta dallo schema: una slice di `overlay` più larga della grana piena viene proratata al `promote()` sul mix osservato in base (o distribuita in parti uguali se il mix è tutto zero); una slice senza riga base corrispondente è rifiutata (`UnmaterializableCellError`), mai materializzata a caso. |
| `tests/test_semantic_graph.py` | Overlay a grafo (`neighbors()` su `edge`, `resolve_manufacturing_items()` su `item_link`): riflette esattamente ciò che il seed ha scritto, incluse `quota`/`quota_source`/`offset_months` e la validità datata. File di test più esteso della suite (440 righe, 33 `assert`/`pytest.raises` diretti + parametrizzazioni su `rel_type` e `direction`). |
| `tests/test_semantic_measures_dag.py` | Il DAG delle misure calcolate è dichiarato (non eseguito) in T2: copre struttura del grafo (`nodes`/`edges`/`topological_order`/`dirty_set`) e verifica che nessuna funzione del layer semantico legga o calcoli un valore di misura. |
| `tests/test_semantic_numeric_types.py` | Contratto di tipo "mai `Decimal` nel semantic layer": DuckDB ritorna `decimal.Decimal` per colonne `DECIMAL(6,3)` (`DPLANT.slot_granularity_factor`, `item.slot_equivalence_factor`, `item.average_assembly_hours`) — il costruttore di riga deve convertirle, altrimenti un `TypeError` emerge solo a valle in T3 quando un chiamante le moltiplica contro una misura `DOUBLE`. |

**File di supporto (non test, nessuna funzione `test_*`):**

| File | Ruolo |
|---|---|
| `tests/conftest.py` | Fixture condivise (vedi sezione Fixture sotto). |
| `tests/_engine_support.py` | Costanti di fixture reali (chiavi verificate contro il DB), `clone_engine()`, `assert_matches_full_recalculate()`, `values_close()`. |
| `tests/_scenario_support.py` | Costanti di fixture per i test di `ibp/scenario/` (chiavi di versione/cella usate da AC13-AC16). |

**Conteggio:** 24 file sotto `tests/` (21 file `test_*.py` + `conftest.py` + 2 moduli di
supporto `_engine_support.py`/`_scenario_support.py`). 157 funzioni `def test_...` distinte,
espanse a **187 test collezionati ed eseguiti** da pytest via `@pytest.mark.parametrize` (usato
in `test_domain_state_machines.py`, `test_engine_ac10_recalc_equivalence.py`,
`test_engine_invalid_edit_keys.py`, `test_scenario_ac13_promotion.py`, `test_semantic_graph.py`
— 3 siti di parametrizzazione —, `test_semantic_measures_dag.py`).

## Organizzazione dei File di Test

**Posizione:** directory unica `tests/` a livello di repository (non co-locati con `ibp/`).

**Naming:** `test_<package>_<area>.py` per i file strutturali, `test_<package>_ac<N>_<slug>.py`
per i file legati a un Acceptance Criteria — vedi tabella sopra. `<package>` rispecchia il
package sotto test: `domain`, `engine`, `scenario`, `semantic`, `db`, `seed`.

**Struttura interna di un file di test tipico:**
```
"""Docstring di modulo: perché questo file esiste, quale difetto reale
chiude o quale AC verifica — con riferimento esplicito al numero AC o
al done_when di task quando applicabile."""
from __future__ import annotations

import pytest
import ibp.scenario as sc          # import assoluto del package sotto test

from _scenario_support import (    # import diretto dai moduli di supporto
    DEMAND_BASE_VERSION_KEY,
    ...
)


def _helper():                     # helper locale al file, prefisso "_"
    ...


def test_comportamento_specifico(engine):   # nome descrittivo, fixture da conftest
    ...
```

## Fixture (tutte in `tests/conftest.py`)

**Gerarchia di scope, dalla più costosa alla più economica:**

| Fixture | Scope | Cosa fornisce |
|---|---|---|
| `db_available` | `session` | Verifica che `data/ibp.duckdb` esista; `pytest.skip` esplicito se manca su checkout pulito, `pytest.fail` esplicito se manca ma `data/` non è vuota (build rotto). |
| `con` | function | Connessione **read-only** al DB reale (`ibp.db.session(read_only=True)`): non muta mai il file su disco. |
| `registry` | function | `SemanticRegistry(con)` sulla connessione read-only. |
| `writable_db_copy` | function | Copia scrivibile del DB reale in `tmp_path` (per test che devono mutare dato, es. AC2 — aggiungere un plant); non tocca mai `data/ibp.duckdb`. |
| `registry_copy` | function | `SemanticRegistry` sulla copia scrivibile. |
| `engine_con` | `session` | Connessione dedicata, read-only, di durata sessione, separata da `con` — usata solo per il motore. |
| `warm_engine` | `session` | Un `RecalcEngine` costruito **una sola volta per l'intera sessione**, su `DEMAND_VERSION_KEY=369`/`OPS_VERSION_KEY=371` (vedi `_engine_support.py` per la motivazione della coppia). Non va mai mutato direttamente da un test. |
| `engine` | function | Copia indipendente ed economica di `warm_engine` via `clone_engine()`: ogni test la muta via `.recalculate()` senza influenzare gli altri test, senza ripagare il costo di costruzione (`RecalcEngine.__init__` carica per intero `TSOP_DEMAND` e fa un `full_recalculate()` — decine di secondi sul DB reale). |

**Perché questo schema conta per chi scrive nuovi test:** costruire un `RecalcEngine` da zero in
ogni test renderebbe la suite proibitiva in tempo di esecuzione. Un nuovo test sul motore deve
usare la fixture `engine` (mai istanziare `RecalcEngine` direttamente), un nuovo test che deve
mutare dato deve usare `writable_db_copy`/`registry_copy` (mai scrivere su `con`, che è
read-only per contratto).

## Nessun Mocking

**Verificato:** nessuna occorrenza di `unittest.mock`, `Mock(`, `monkeypatch` in tutta `tests/`.
La suite è **interamente basata su un DB DuckDB reale** (`data/ibp.duckdb`, prodotto da
`python db/build_db.py`) con dati sintetici ma deterministici (RNG via `hashlib`, vedi
CONVENTIONS.md). Le costanti di fixture (chiavi di prodotto, plant, versione) sono documentate
nei moduli di supporto come "verificate contro il DB reale", non inventate — es.
`_engine_support.py`: *"Pool di (product_key, division_key, date_key) realmente presenti in
TSOP_DEMAND per version_key=369, measure REQ_PROD — verificato contro il DB reale (66
combinazioni)"*.

**Implicazione per test nuovi:** non introdurre mock per DuckDB o per i moduli `ibp.*` — il
pattern consolidato è usare `con`/`writable_db_copy`/`engine` su dato reale o una copia
scrivibile dello stesso. Se una fixture di dato serve (nuove chiavi, nuovo pool), verificarne
l'esistenza contro il DB reale e documentarlo nel modulo di supporto come fanno
`_engine_support.py`/`_scenario_support.py`.

## Pattern per Test Strutturali (AST, non grep testuale)

Diversi file usano il modulo `ast` di libreria standard per verificare vincoli sul *sorgente*
stesso, non sul comportamento a runtime:

- `tests/test_semantic_ac2_master_data.py` — `_fold_numeric()` valuta ricorsivamente
  `ast.Constant`/`ast.UnaryOp`/`ast.BinOp` per scoprire letterali di capacità anche dietro
  aritmetica immediata (`29 + 1`) o forma float (`30.0`).
- `tests/test_domain_ac10_erp_boundary.py` — scan delle `ast.ClassDef` in `ibp/domain/*.py` per
  nomi che contengono frammenti ERP-transazionali (`order`, `bom`, `mrp`, ...).
- `tests/test_db_single_entrypoint.py` — scan AST per l'apertura di connessioni DuckDB fuori da
  `ibp/db.py`.

**Ogni test AST include anche un controllo di non-vacuità** (es.
`test_capacity_literal_scan_actually_detects_evasive_forms`,
`test_calculation_root_candidates_are_existence_tolerant`): verifica che lo scanner stesso
riconosca le forme che dovrebbe intercettare, su un frammento sintetico, così un test che passa
sempre per costruzione (perché la lista di root è vuota, o il pattern regex non matcha mai)
verrebbe scoperto.

## Testing degli Errori

Pattern uniforme: `with pytest.raises(NomeErroreSpecifico): ...`, mai
`with pytest.raises(Exception):` generico. 46 occorrenze totali di
`pytest.raises`/`pytest.mark`/`pytest.skip`/`pytest.fail` nella suite. Esempio da
`tests/test_domain_ac10_erp_boundary.py`:
```python
def test_unknown_plant_key_raises_key_error(registry: SemanticRegistry):
    with pytest.raises(KeyError):
        registry.plant_capacity(999_999)
```
Per le eccezioni di dominio (`ScenarioError`, `EngineError`, `DomainError` e sottoclassi), i test
verificano il tipo esatto sollevato, coerente con la convenzione "un'eccezione specifica, non
generica" descritta in CONVENTIONS.md.

## Coverage

**Requisiti:** nessuno imposto/misurato (nessun `pytest-cov` in dipendenze, nessuna soglia
configurata). La copertura è governata dalla convenzione AC-per-file: la tabella sopra è la
mappa di riferimento per capire quali AC hanno già un test dedicato (AC2, AC4/AC20 parziale,
AC10, AC11, AC12, AC13, AC14, AC15, AC16) e quali no — qualunque AC citato in
`docs/01-plan-m1.md`/`docs/02-spec-m1-corrente.md` non presente in questa tabella non ha ancora
un file di test dedicato.

## Tipi di Test

**Unitari puri:** funzioni pure senza I/O, es. `tests/test_engine_ac12_aggregate.py` su
`ibp/engine/aggregate.py` (`combine`/`combine_ratio`/`is_delta_safe`).

**Integrazione su DB reale:** la maggioranza della suite — ogni test che usa `con`, `registry`,
`writable_db_copy`, `engine` opera contro `data/ibp.duckdb` reale o una sua copia scrivibile, non
contro dato sintetico costruito nel test.

**Strutturali (AST-based):** vedi sezione dedicata sopra.

**E2E:** non applicabile — nessuna API HTTP/UI ancora costruita (T10/T11 pendenti secondo
`.planning/intel/context.md`).

## Pattern Comuni

**Snapshot prima/dopo per verificare "nessuna scrittura parziale" (AC16):**
```python
def _snapshot_counts(con):
    dversions = con.execute("SELECT count(*) FROM DVERSIONS").fetchone()[0]
    demand = con.execute("SELECT count(*) FROM TSOP_DEMAND").fetchone()[0]
    ops = con.execute("SELECT count(*) FROM TSOP_OPS").fetchone()[0]
    return dversions, demand, ops
```
usato in `tests/test_scenario_ac16_conflict.py` per verificare che un conflitto rilevato non
lasci righe scritte a metà.

**Confronto esatto, mai a tolleranza, per il motore di ricalcolo:**
```python
# tests/_engine_support.py
def assert_matches_full_recalculate(engine, result) -> None:
    """... deve produrre valori esattamente identici (`==`, non più tolleranza) ..."""
```

**Sequenze casuali con seed fisso per stress-test di equivalenza:**
```python
@pytest.mark.parametrize("seed", range(8))
def test_random_batch_sequence_matches_full_recalculate(seed, engine):
    rng = random.Random(seed)
    ...
```
(`tests/test_engine_ac10_recalc_equivalence.py`) — il seed del test è passato esplicitamente a
`random.Random`, non al RNG di produzione (`hashlib`-based); è un dettaglio di riproducibilità
del *test*, distinto dal determinismo del *seed di dati* discusso in CONVENTIONS.md.

---

*Analisi testing: 2026-09-19*
