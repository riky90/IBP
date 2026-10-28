# Problemi noti del codebase

**Data di analisi:** 2026-09-19

> Verifica puntuale dei sei item di debito noto elencati in
> `docs/03-consegna-t1-t4.md` (sezione "Debito aperto, da schedulare") e
> impacchettati come task in `docs/02-spec-m1-corrente.md` (T6.0, T10.0,
> T10.1, T11.0, T11.1/T11.2). Ogni item è stato riletto contro il codice
> reale del 2026-09-19, con conferma a runtime dove possibile (query
> instrumentate, riproduzione dell'eccezione). Tutti e sei sono **ancora
> presenti**, nessuno è già risolto, nessuno è misdescritto — ma due (#1 e
> #2) sono in realtà leggermente **peggio** o **più radicati** di come la
> loro descrizione breve lascia intendere. I dettagli sono nelle rispettive
> sezioni sotto.

## Tech Debt

### #1 — `_eligible_plant_for` cachea per `manufact_key` e ignora la region (T6.0)

- File: `ibp/engine/engine.py:209-226` (funzione `_eligible_plant_for`)
- Stato: **presente, confermato**, e il problema strutturale è un gradino più
  in basso di quanto la formulazione lasci intendere.
- Cosa fa oggi: la cache è `dict[int, int | None]` chiavata solo su
  `manufact_key` (riga 151: `self._eligible_plant_cache: dict[int, int | None]`).
  La prima chiamata per un dato `manufact_key`, a qualunque `date_key`,
  risolve il plant eleggibile e lo fissa per sempre — ogni chiamata
  successiva con la stessa `manufact_key` e una `date_key` diversa restituisce
  il valore cacheato senza nemmeno interrogare `production_eligibility` di
  nuovo (righe 215-216: `if manufact_key in self._eligible_plant_cache: return ...`).
  Non c'è alcun parametro `region`/`region_scope` nella firma della funzione
  (riga 209: `def _eligible_plant_for(self, manufact_key: int, date_key: int) -> int | None`).
- **Perché è più profondo del previsto**: `docs/02-spec-m1-corrente.md` (T6.0,
  nota) lo dice esplicitamente e il codice lo conferma — il difetto non è
  la cache in sé, è che `derived_manufacturing_demand` aggrega già a
  `(manufact_key, date_key)` **senza region** (vedi `_compute_dmd_cell`,
  `engine.py:347-366`, e la chiave `dmd_keys` costruita in
  `full_recalculate()`, `engine.py:492-499`, e nella propagazione
  incrementale, `engine.py:424-430`). La region della domanda non sopravvive
  fino al punto in cui `_eligible_plant_for` viene chiamata: aggiungere un
  parametro `region` alla funzione senza allargare la grana della cella
  non risolverebbe nulla, perché a monte l'informazione è già stata persa.
  Il fix corretto non è locale a questa funzione.
- Oggi funziona per caso: nel seed `production_eligibility.valid_to` è
  sempre `NULL` (vedi il docstring della funzione stessa, righe 210-214, e
  la nota T6.0), quindi non esiste ancora un caso osservabile in cui la
  stessa `manufact_key` abbia eleggibilità diversa a date diverse. Il bug è
  silenzioso — nessun test fallisce, nessun'eccezione, solo un plant sbagliato
  il giorno in cui T6/T7 introducono eleggibilità datata o scoping per
  region (AC5).
- Impatto se non corretto prima di T6/T7: `slots_requested`, `gap_req_conf`
  e `value_gap` verrebbero assegnati al plant sbagliato per la porzione di
  domanda con eleggibilità region-specific, senza sollevare nulla —
  esattamente il tipo di errore "numero plausibile ma sbagliato" che il
  resto della codebase (vedi note su `T6.b`, `back_allocation`) si sforza
  di evitare altrove.
- Fix proposto (T6.0, già pianificato): allargare la grana della cella con
  la region della domanda fino a `_eligible_plant_for`, far cachare la
  funzione per `(manufact_key, region, date_key)` con controllo di validità
  temporale reale, non solo per `manufact_key`.

### #2 — Costruzione del motore dominata da query N+1 (T10.0)

- File chiamante: `ibp/engine/engine.py:289` (dentro `_ensure_rp_targets`,
  righe 275-297), invocato da `full_recalculate()` in un ciclo su
  `self._rp_by_product_date` (righe 492-495: `for product_key, date_key in
  self._rp_by_product_date: targets = self._ensure_rp_targets(product_key, date_key)`).
- File chiamato: `ibp/semantic/graph.py:223` (`resolve_manufacturing_items`).
- Stato: **presente, confermato con misura diretta sul DB reale** (non solo
  a lettura di codice). Riprodotto instrumentando `resolve_manufacturing_items`
  su `RecalcEngine(con, demand_version_key=353, ops_version_key=355)`
  (la coppia di versioni più popolata nel seed, 100.224 righe `TSOP_DEMAND` /
  42.780 righe `TSOP_OPS`):
  - **3.492 chiamate** a `resolve_manufacturing_items`, una per ciascuna
    delle 3.492 coppie distinte `(product_key, date_key)` presenti in
    `self._rp_by_product_date` — combacia esattamente con il numero
    riportato in `docs/02-spec-m1-corrente.md` (T10.0: "3.492× = 26,3 s").
  - **14.397 query totali** verso DuckDB durante `RecalcEngine.__init__`
    (contate con una connessione-proxy che intercetta `.execute()`), contro
    le **14.394** riportate nella spec — scarto di 3, compatibile con le
    query di setup (`measures.get_measure` per `WEEKS_PRODUCTION` e le due
    misure di `_load_confirmed_production`).
  - Tempo di costruzione misurato su questa macchina: **15,5 s** (non
    42,7 s né 63-86 s come nei due punti diversi della documentazione) —
    coerente con la nota della spec stessa ("il tempo dipende dalla
    macchina... la soglia primaria è il conteggio di query, non il tempo").
    Il conteggio di query, non il tempo, è la misura riproducibile e
    coincide.
- **Amplificazione nascosta, non esplicitata nella descrizione breve**:
  ogni riga restituita da `resolve_manufacturing_items` innesca a sua volta
  una query `resolve_identity()` (`graph.py:287`, dentro il list comprehension
  che costruisce `ManufacturingRealisation`) — un secondo livello di N+1
  dentro il primo. Misurato: **3.498 chiamate** a `resolve_identity` durante
  la stessa costruzione. Il piano di T10.0 lo copre comunque, perché
  `item_identifier` è già nell'elenco delle tabelle da precaricare in bulk
  (`docs/02-spec-m1-corrente.md`, T10.0 done_when), ma vale la pena
  segnalarlo esplicitamente: il preload deve risolvere **entrambi** i
  livelli di N+1, non solo il più esterno, o il conteggio di query resterà
  sopra la soglia di 25 richiesta da T10.0.
- Le altre cache lazy per-chiave della classe (`_item_factor_cache`,
  `_plant_capacity_cache`, `_weeks_cache`, `_rate_cache`, righe 149-153)
  sono lo stesso pattern strutturale su scala minore — corrette solo perché
  il carico di lettura ripetuta è più basso, non perché la strategia sia
  diversa.

## Fragile Areas — Transazioni

### #3 — `BEGIN TRANSACTION` nudo in tutto `ibp/scenario/`, nessun supporto per annidamento (T10.1)

- File e righe esatte confermate:
  - `ibp/scenario/branch.py:81, 113, 127` (funzioni `branch()`,
    `mark_evaluated()`, `discard()` — ognuna apre/chiude la propria
    transazione).
  - `ibp/scenario/edits.py:93` (`_apply_edit()`, usata da `set_cell()` /
    `increment_cell()` / `delete_cell()`).
  - `ibp/scenario/promote.py:332` (`promote()`).
- `ibp/db.py` **non espone alcun context manager di transazione** oggi —
  contiene solo `connect()` e `session()` (apre/chiude la connessione, non
  una transazione). Non c'è nessuna funzione riutilizzabile da cui questi
  cinque siti derivano il loro `BEGIN`/`COMMIT`/`ROLLACK`: sono cinque
  copie indipendenti dello stesso pattern try/except.
- Riprodotto a runtime, non solo dedotto dal codice: una seconda
  `BEGIN TRANSACTION` sulla stessa connessione DuckDB già in transazione
  solleva
  ```
  duckdb.duckdb.TransactionException: TransactionContext Error: cannot start a transaction within a transaction
  ```
  esattamente come descritto. DuckDB non supporta `SAVEPOINT` (confermato
  anche nella nota di T10.1) quindi non esiste una via d'uscita "annidata
  vera" — l'unica semantica corretta è la proprietà della transazione (chi
  la apre la chiude), non un contatore di annidamento ingenuo.
- Impatto: oggi nessun chiamante avvolge `branch()`/`record_edit()`/
  `promote()` in una propria transazione, quindi la suite (187 test, verde)
  non lo mostra. Il giorno in cui T10 costruisce un layer HTTP che vuole
  garantire atomicità su più operazioni di scenario in una singola richiesta
  (es. crea branch + applica N edit in un'unica transazione), la prima
  chiamata annidata rompe con l'eccezione sopra. Nessun test in `tests/`
  copre oggi questo scenario (verificato: nessun file contiene
  `BEGIN TRANSACTION`).
- Fix proposto (T10.1, già pianificato): context manager rientrante in
  `ibp/db.py` che, se la connessione ha già una transazione aperta, non la
  possiede (nessun `COMMIT`/`ROLLBACK` proprio) — decisione lasciata al
  chiamante più esterno.

## Gap Funzionali (misure non additive silenziosamente escluse)

### #4 — `compare()` vede solo le misure `agg_method='sum'` (T11.0)

- File: `ibp/scenario/overlay.py:123-179` (`materialize_version`), usata da
  `materialize_ref` che alimenta `ibp/scenario/compare.py:11-39` (`compare()`).
- Meccanismo confermato: `materialize_version` filtra esplicitamente
  (`overlay.py:167` e `overlay.py:176`: `if measure_key not in
  additive_demand/additive_ops: continue`) usando `additive_measure_keys()`
  (`overlay.py:91-98`, `WHERE agg_method = 'sum'`). Le righe con
  `agg_method` diverso da `'sum'` non generano eccezioni, non vengono
  segnalate: semplicemente non entrano nel dizionario `slices`, quindi
  `compare()` non le vede mai, in nessuna delle due versioni confrontate —
  il delta per quella misura non compare affatto nel risultato, non appare
  come riga a delta zero.
- **Catalogo verificato riga per riga** contro `db/seed/dimensions.py`
  (`build_dmeasure_demand`, righe ~440-455, e `build_dmeasure_ops`, righe
  ~458-473):
  - `DMEASURE_DEMAND` (11 misure): 10 `sum`, 1 `ratio` (`ORDER_COVERAGE`).
  - `DMEASURE_OPS` (15 misure): 9 `sum`, 3 `avg` (`AVG_MAX_CAPACITY`,
    `WEEKS_PRODUCTION`, `FROZEN_ZONE`), 2 `ratio` (`CAPACITY_UTIL`,
    `PLANT_RELIABILITY`), 1 `max` (`SLOTS_AVAILABLE`).
  - Totale: **19 `sum`, 1 `max`, 3 `avg`, 3 `ratio`** — combacia
    esattamente con il conteggio riportato in
    `docs/02-spec-m1-corrente.md` (T11.0: "19 sum, 1 max, 3 avg, 3 ratio").
    Il conteggio nella spec è corretto, non gonfiato né sottostimato.
- Il rischio pratico più citato nella documentazione (`CAPACITY_UTIL`,
  `agg_method='ratio'`) è reale: un confronto fra due scenari che differisce
  solo sull'utilizzo di capacità produrrebbe oggi **zero righe** in
  `compare()` per quella misura — non una riga con delta 0, proprio nessuna
  riga — un falso "nessuna differenza" silenzioso su una delle metriche
  che un planner guarderebbe per prima.
- Da notare, non ancora nella descrizione breve: `min`/`max` sono in
  realtà ricombinabili dai valori grezzi (min/max di un gruppo è min/max
  dei sotto-gruppi), quindi l'esclusione di `SLOTS_AVAILABLE` (`max`) è più
  facile da correggere di `avg`/`ratio`, che richiedono un denominatore che
  `overlay` non traccia — la spec T11.0 fa già questa distinzione (`min`/`max`
  "comparable", `avg`/`ratio` "not_comparable" con motivo esplicito), ed è
  coerente con quanto osservato nel codice.
- `require_additive_measure()` (`overlay.py:109-120`) applica invece un
  rifiuto esplicito (`NonAdditiveMeasureError`) per le scritture singola
  cella via `resolve_cell()` — quel percorso **non** ha il problema di
  sparizione silenziosa, solo l'aggregazione bulk di `materialize_version`
  (usata da `compare()` e dalla promozione) ce l'ha.

## Provenienza mancante

### #5 — Nessuna tabella di provenienza: una riga `DVERSIONS` promossa non risale allo scenario (T11.1/T11.2)

- Verificato su `db/schema.sql:115-128` (`CREATE TABLE DVERSIONS`): le
  colonne sono `version_key, version_name, cycle_year, cycle_month, side,
  status, is_budget, is_frozen, first_planning_year, first_planning_month,
  valid_budget_version` — **nessuna colonna** che referenzi uno
  `scenario_id` o un `edit_id`. Nessuna tabella laterale di provenienza
  esiste nello schema (cercato `provenance`/`origin` in `db/schema.sql`:
  zero occorrenze rilevanti).
- `ibp/scenario/promote.py` (`promote()`, righe 258 in avanti) scrive le
  nuove righe `TSOP_DEMAND`/`TSOP_OPS` con `INSERT` diretti (righe 351-368)
  senza persistere da nessuna parte se una riga è stata copiata
  byte-per-byte, proratata, o derivata da un `overlay_override` — anche se
  l'informazione **esiste già in memoria** al momento della scrittura:
  `overlay_touched_slices()` (`overlay.py:260+`) calcola esattamente
  l'insieme delle slice toccate da uno scenario, distinguendo "mai toccata"
  da "toccata", e viene interrogata in `promote.py:316` — il risultato è
  usato per decidere *come* scrivere (copia vs riparto) ma buttato via
  subito dopo, mai persistito.
- Impatto confermato per lettura del codice: un planner che guarda una
  `DVERSIONS` promossa non ha modo, a posteriori, di distinguere quali
  righe sono un override manuale, quali sono state proratate
  automaticamente sul mix osservato e quali sono identiche al base — le
  tre categorie sono indistinguibili una volta scritte.
- Fix proposto (già pianificato, due task separati per competenza): T11.1
  aggiunge lo schema (`db/schema.sql`, tabella laterale con
  `version_key, slice, origin ∈ {copied, overlay_override, prorated},
  scenario_id, edit_id?`, senza toccare `TSOP_DEMAND`/`TSOP_OPS` per non
  rompere l'isomorfismo con dEPM); T11.2 fa scrivere `promote()` in quella
  tabella, catturando l'informazione che `overlay_touched_slices()` già
  calcola invece di ricalcolarla.

## Guardia troppo ampia in `neighbors()`

### #6 — `as_of` storico rifiutato anche per node type che non possono averne bisogno

- File: `ibp/semantic/graph.py:148` (dentro `neighbors()`, righe 109-182).
- Stato: **presente, confermato**, riga esatta corrispondente alla
  descrizione:
  ```python
  if is_historical and (rel_type is None or rel_type in _ITEM_LINK_SNAPSHOT_REL_TYPES):
      raise GraphSnapshotLimitationError(...)
  ```
  La condizione non controlla `node_type` in nessun punto — guarda solo
  `is_historical` (calcolato riga 146: `as_of_explicit and as_of <
  dt.date.today()`) e `rel_type`. Una chiamata come
  `neighbors(con, "plant", "12", as_of=data_passata)` con `rel_type=None`
  solleva `GraphSnapshotLimitationError`, anche se un nodo `plant` non può
  strutturalmente avere archi `PRODUCES`/`AGGREGATES`/`SPLITS`/
  `DEPENDENT_DEMAND` (quei `rel_type` collegano solo nodi `item`) — la
  motivazione stessa dell'eccezione ("rel_type=None potrebbe includere
  relazioni derivate da item_link", riga 152) è falsa per un nodo `plant`.
- Non ancora corretto: nessun controllo su `node_type != "item"` esiste
  nella funzione. Il fix minimo indicato nella documentazione (saltare la
  guardia se `node_type != "item"`) non è stato applicato.
- Impatto: blocca query storiche legittime plant→region (il caso citato
  esplicitamente per T6) con un'eccezione fuorviante, costringendo il
  chiamante a capire che il vero limite riguarda solo i nodi `item`, non il
  tipo di nodo effettivamente interrogato.
- Non bloccante per M1 core (T1-T4): nessun consumatore attuale in
  `ibp/engine/` chiama `neighbors()` con `as_of` passato su un nodo
  `plant` — il motore usa `resolve_manufacturing_items()` direttamente per
  la risoluzione item→manufacturing, e `_eligible_plant_for` legge
  `production_eligibility` con SQL diretto, non via `neighbors()`. Il
  rischio si materializza solo quando `ibp/network/` (T6.b, eleggibilità
  per region) inizia a usare `neighbors()` su nodi `plant`.

## Item verificati come già risolti (non più debito)

- **Blocco d'installazione Windows per `statsforecast`** (citato in
  `docs/03-consegna-t1-t4.md` come "Debito noto, non di T2" e poi ripreso
  come rischio T5): verificato su `pyproject.toml` righe 32-55 — il pin è
  stato aggiornato il 2026-09-12 da `statsforecast==1.7.8` (senza wheel
  Windows/cp313) a `statsforecast==2.1.1` + `hierarchicalforecast==1.5.1` +
  `utilsforecast==0.2.16`, con wheel disponibili e installazione da `pip`
  senza MSVC (commento a riga 43: "si installano da wheel, senza..."). Lo
  stack di forecasting resta nell'extra opzionale `[forecast]`, quindi
  `pip install -e .` di base non lo richiede. **Non è più debito aperto**,
  ma non è stato ancora esercitato da T5 (che è tuttora `pending`): resta
  da verificare che l'installazione funzioni davvero quando T5 la userà
  per la prima volta, non solo che il pin sia risolvibile.
- **Le 5 correzioni T3/T4 elencate come "chiuse" in `docs/03-consegna-t1-t4.md`**
  (batch non atomico del motore, `confirmed_production` fuori dal DAG
  dichiarato, contatore `absent` di `CutoffStats`, non-determinismo di
  `materialize_version`/`promote()`, misure non additive sommate in
  `promote()`, fuga fra scenari AC15, `side`/`status` non verificati alla
  promozione): tutte confermate presenti nel codice attuale come descritte
  (validazione a due fasi in `recalculate()`, `_EDIT_VALIDATORS`,
  `ORDER BY` + somma in Python in `materialize_version`/`promote.py`,
  `SideMismatchError`/`CellVersionMismatchError`/`MismatchedBaseVersionError`
  in `ibp/scenario/errors.py`) — coerenti con "chiuso", non riaperte da
  modifiche successive. Suite completa verde: `python -m pytest -q` →
  **187 passed**, nessun fallimento, ~112s su questa macchina.

## Test Coverage Gaps

**Transazioni annidate (debito #3):**
- Nessun file in `tests/` contiene `BEGIN TRANSACTION` o esercita il caso
  "chiamare `branch()`/`record_edit()`/`promote()` dentro una transazione
  già aperta dal chiamante" — verificato con una ricerca su tutto `tests/`.
  Rischio: alto una volta che T10 introduce un layer HTTP che aggrega più
  operazioni scenario in una transazione, perché la prima integrazione
  romperebbe a runtime con `TransactionException`, non a test.

**Conteggio query della costruzione del motore (debito #2):**
- Nessun test oggi verifica un tetto massimo di query per
  `RecalcEngine.__init__` (T10.0 lo introdurrà con una connessione-proxy) —
  la regressione di performance, se qualcuno la reintroducesse dopo un
  futuro fix, non sarebbe rilevata automaticamente finché quel test non
  esiste.

**`neighbors()` per node type diversi da `item` (debito #6):**
- `tests/test_semantic_graph.py` copre `neighbors()` prevalentemente su
  nodi `item`; non risultano casi che chiamino `neighbors("plant", ...,
  as_of=<data passata>)` per verificare il comportamento attuale (che
  solleva anche quando non dovrebbe). La correzione futura rischia quindi
  di essere fatta senza un test di regressione preesistente che ne provi
  il comportamento "prima".

---

*Verifica debito: 2026-09-19.*
