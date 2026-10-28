# Roadmap: IBP ACMELIFT

> **Nota sulla lingua.** I contenuti sono in italiano. Restano in inglese, verbatim, solo le
> etichette strutturali che i workflow GSD leggono a valle (`### Phase N:`, `**Goal**`,
> `**Depends on**`, `**Requirements**`, `**Success Criteria**`, `**Plans**`, `**UI hint**`, i
> valori di stato della tabella Progress). Sono identificatori, non prosa.

## Overview

M1 parte da una fondazione già a terra e verde — schema e seed, dominio e semantic layer, motore di
concurrent planning, scenari (Phase 1-4, consegnate sotto `/software-house`, commit `d54a453`, 187
test verdi) — e la porta fino a una piattaforma che un planner può usare: forecast statistico con
FVA, rete produttiva multi-plant con routing e domanda dipendente, capacità e allocatore, ciclo
P/R/A/C con i due review mancanti, confine di sistema, API, workbench e demo offline.

Il percorso non è lineare, per scelta. Tre cose lo piegano:

1. **Il debito si paga prima, non dopo.** Sei pacchetti verificati contro il codice reale
   (Phase 6, 7, 10, 13) stanno **prima** dei consumatori che li romperebbero. Costruire l'API su un
   costruttore da 14.397 query, o il workbench su un `compare()` che fa sparire `CAPACITY_UTIL` in
   silenzio, significherebbe costruire due volte.
2. **Un motore chiuso e verde si riapre una volta sola.** La Phase 6 (T6.0) allarga la grana con la
   region: è isolata in una fase propria e non chiude finché **AC10** non è di nuovo verde.
3. **R-001 arriva prima del workbench, non dopo.** Se il tronco unico si costruisse dopo la UI, la
   UI andrebbe rifatta. Step A (additivo) è la Phase 13; Step B è rinviato a M2 perché collide con
   `DVERSIONS.version_name UNIQUE`, letto come stringa dalle misure DAX di Power BI.

Criterio di chiusura di ogni fase: **il suo acceptance criteria ha un test che passa in `tests/`**,
con il nome `test_<area>_ac<N>_<slug>.py`, e la suite completa resta verde.

## Phases

**Numerazione:**
- Fasi intere (1, 2, 3): lavoro di milestone pianificato
- Fasi decimali (2.1, 2.2): inserimenti urgenti (marcati INSERTED)

- [x] **Phase 1: Schema DuckDB e seed isomorfo (T1)** - Il DB si ricostruisce da zero, idempotente, con le regole di capacità come master data
- [x] **Phase 2: Dominio, semantic layer, DAG dichiarato, grafo (T2)** - La fondazione su cui motore e scenari diventano verificabili
- [x] **Phase 3: Motore di concurrent planning (T3)** - Un edit ripropaga subito, con early cutoff misurato e incrementale ≡ completo
- [x] **Phase 4: Scenari — event log, overlay, confronto, promozione (T4)** - Branch, modifica, confronto e promozione a nuova versione senza mutare nulla
- [ ] **Phase 5: Forecast statistico e FVA (T5)** - La baseline precompila il P e lo stairstep FVA si ricostruisce a lag costante
- [ ] **Phase 6: Grana region nel motore (T6.0)** - La region sopravvive fino alla scelta del plant; gate d'uscita: AC10 di nuovo verde
- [ ] **Phase 7: Tenuta del livello scenario (T10.1 + T11.0)** - Transazioni rientranti e nessuna misura che sparisce dal confronto
- [ ] **Phase 8: Rete produttiva (T6)** - Mapping N:N, eleggibilità per region, routing obbligatorio ed elettivo, back-allocation
- [ ] **Phase 9: Capacità e allocatore (T7)** - Doppio vincolo slot/ore a Northfield e split multi-plant proposto dal sistema
- [ ] **Phase 10: Costruzione del motore in bulk (T10.0)** - Da 14.397 query a meno di 25, senza cambiare un solo risultato
- [ ] **Phase 11: Ciclo P/R/A/C e i due review mancanti (T8)** - Portfolio Review e Integrated Reconciliation come oggetti di prima classe
- [ ] **Phase 12: Adapter, viste e confine di sistema (T9)** - Import read-only, write-back come file, master data reale normalizzato
- [ ] **Phase 13: Tronco unico e provenienza (R-001 Step A + T11.1 + T11.2)** - Piani e scenari diventano rami dello stesso tipo, e ogni riga promossa risale alla sua origine
- [ ] **Phase 14: API HTTP interna (T10)** - Motore, scenari e processo raggiungibili da un client locale, atomicamente
- [ ] **Phase 15: Workbench e demo CLI (T11 + T12)** - Un planner guida la piattaforma end-to-end, offline
- [ ] **Phase 16: Documentazione e diagrammi (T13)** - Diagrammi navigabili e coerenti col codice finale

## Phase Details

### Phase 1: Schema DuckDB e seed isomorfo (T1)
**Goal**: Esiste un database ricostruibile da zero, deterministico e isomorfo al modello dEPM, con le regole di capacità come dato e non come codice.
**Depends on**: Nothing (prima fase)
**Requirements**: AC1, AC2
**Success Criteria** (cosa deve essere VERO):
  1. `python db/build_db.py` ricostruisce `data/ibp.duckdb` da zero e produce lo stesso riepilogo su tre esecuzioni consecutive (AC1).
  2. `Max Slots`, la granularità di slot e la soglia `<500` vivono su `DPLANT` / `db/seed/data/*.json`; uno scan AST impedisce che rientrino come literal nel codice di calcolo (AC2).
  3. `_validate()` fa **fallire** il build su invariante violata — per esempio quote di `(from_item, link_type, period)` che non sommano a 100.
  4. Nessun dato ACMELIFT reale nel repository: il seed è sintetico ma isomorfo (REQ-F4).
**Plans**: n/d — consegnata prima della migrazione a GSD
**Status**: Complete (2026-09-12; riaperta due volte, per l'extra `[forecast]` e per il digest di `base_snapshot_id`)

### Phase 2: Dominio, semantic layer, DAG dichiarato, grafo (T2)
**Goal**: Esiste una fondazione su cui motore e scenari sono verificabili: entità con ciclo di vita, un solo punto di accesso al DB, e le dipendenze fra misure dichiarate come dato.
**Depends on**: Phase 1
**Requirements**: — *(nessun acceptance criteria proprio: regge AC10-AC16, coperta da test strutturali)*
**Success Criteria** (cosa deve essere VERO):
  1. `ibp/db.py` è l'**unico** punto di apertura di connessioni DuckDB in `ibp/`, verificato via scan AST e non per ispezione manuale.
  2. `MEASURE_DAG` dichiara le dipendenze fra misure come dato puro; nessuna funzione del semantic layer legge o calcola un valore di misura.
  3. Ogni macchina a stati dichiarata accetta tutte le transizioni legali e solleva un'eccezione **specifica** su quelle illegali — mai una `Exception` generica, mai un fallimento silenzioso.
  4. Ogni numerico esposto dal semantic layer è `float`, mai `Decimal`: le colonne `DECIMAL` sono convertite nel row constructor.
**Plans**: n/d — consegnata prima della migrazione a GSD
**Status**: Complete (2026-09-11, critic PASS al secondo giro)

### Phase 3: Motore di concurrent planning (T3)
**Goal**: Un edit ripropaga immediatamente sull'intero piano, con lo stesso risultato di un ricalcolo completo e con il risparmio dell'early cutoff misurato, non promesso.
**Depends on**: Phase 2
**Requirements**: AC10, AC11, AC12
**Success Criteria** (cosa deve essere VERO):
  1. `recalculate(changed)` produce valori **esattamente identici** (`==`, non a tolleranza) a `full_recalculate()`, incluse 8 sequenze casuali da 15 batch (AC10).
  2. `CutoffStats` misura l'early cutoff con l'invariante `visited == computed + cutoff + absent` verificata a ogni chiamata; il quarto termine `absent` distingue la sparsità del master data dal risparmio reale (AC11).
  3. `min`/`max`/`ratio` si ricalcolano sul gruppo, mai per delta (AC12).
  4. Un batch con una chiave non valida fallisce **prima** di scrivere stato: un edit malformato non blocca il motore per sempre.
**Plans**: n/d — consegnata prima della migrazione a GSD
**Status**: Complete (2026-09-11)

### Phase 4: Scenari — event log, overlay, confronto, promozione (T4)
**Goal**: Un planner può ramificare da una versione, modificare celle sparse, confrontare e promuovere — creando sempre una nuova istanza, senza mai mutare quella di partenza.
**Depends on**: Phase 2
**Requirements**: AC13, AC14, AC15, AC16
**Success Criteria** (cosa deve essere VERO):
  1. `branch → edit sparso → compare → promote` crea una **nuova** riga `DVERSIONS` con il nome esatto atteso dalle misure DAX; nessuna istanza esistente viene mai mutata (AC13).
  2. Una cella cancellata in uno scenario (`is_deleted=TRUE` esplicito, mai `NULL` come sentinella) non ricompare dal base (AC14).
  3. La lettura di uno scenario non include mai celle di uno scenario fratello, né in lettura diretta né lungo una catena annidata (AC15).
  4. Una promozione la cui base si è mossa dal branch time viene **rifiutata prima di qualunque scrittura**: nessuna riga parziale, nessun cambio di stato (AC16).
  5. Lettura e scrittura sono deterministiche: `ORDER BY` su PK piena e somma in Python, mai `SUM(...) GROUP BY` parallelo.
**Plans**: n/d — consegnata prima della migrazione a GSD
**Status**: Complete (2026-09-11; verifiche finali dei critic rientrate e chiuse)

### Phase 5: Forecast statistico e FVA (T5)
**Goal**: La baseline statistica precompila la versione P come dato, non come report, e il Forecast Value Added diventa ricostruibile per costruzione invece che a posteriori.
**Depends on**: Phase 2 *(indipendente dalle Phase 6-10: può correre in parallelo con Phase 6 e Phase 7)*
**Requirements**: AC17, AC18, AC19
**Success Criteria** (cosa deve essere VERO):
  1. La baseline statistica precompila la versione P, e un override manuale del planner resta **distinguibile** dal valore generato (AC17).
  2. Lo stairstep `Naïve → Baseline → Rettificata → Consenso` si ricostruisce da `forecast_snapshot` a **lag costante**; un FVA negativo allo step planner è un risultato atteso, non un difetto (AC18).
  3. Il forecast riconciliato è coerente lungo la gerarchia **commerciale** `division ▶ product line ▶ category ▶ model` — non quella manifatturiera, che è N:N e romperebbe MinTrace in silenzio (AC19).
  4. Un test di regressione lanciato **in subprocess** verifica `returncode == 0` sull'import di `ibp/forecast/`: la prima riga del package è `from hierarchicalforecast._lib import reconciliation as _hf_lib`, altrimenti il processo muore di SIGSEGV senza traceback.
  5. `pip install -e ".[forecast]"` completa su Windows **da wheel**, senza toolchain C++.
**Plans**: TBD
**Note**: `HierarchicalReconciliation.reconcile()` prende `S_df=`, non `S=` (API 1.x). Il pool di modelli va scelto **dopo** aver misurato la copertura reale della storia nel seed (4 cicli chiusi + corrente): raccomandato `AutoETS` + `SeasonalNaive` + `AutoTheta` + `CrostonOptimized`, `AutoARIMA` disattivato di default, `MinTrace(ols)` titolare. Sottopacchetti: **T5.a** guardia import + serie + gerarchia → **T5.b** baseline + riconciliazione → **T5.c** snapshot a lag costante + FVA.

### Phase 6: Grana region nel motore (T6.0)
**Goal**: La region della domanda sopravvive lungo tutto il motore fino alla scelta del plant, così che l'eleggibilità per `region_scope` diventi esprimibile senza produrre numeri plausibili ma sbagliati.
**Depends on**: Phase 3, Phase 4 *(può correre in parallelo con Phase 7 — percorsi disgiunti: `ibp/engine/` + `ibp/semantic/` contro `ibp/db.py` + il percorso di scrittura di `ibp/scenario/`)*
**Requirements**: GRANA-01, GRAFO-01
**Success Criteria** (cosa deve essere VERO):
  1. Due domande con la stessa `manufact_key` in region diverse producono **due celle distinte**: la grana `(manufact_key, region, date_key)` sopravvive da `derived_manufacturing_demand` (`engine.py:347-366`, `492-499`) fino a `_eligible_plant_for` (`engine.py:209-226`).
  2. Una `production_eligibility` con `valid_to` valorizzato produce un plant eleggibile **diverso a date diverse** per la stessa `manufact_key`: la cache non è più chiavata solo su `manufact_key`, e la validità temporale è controllata davvero.
  3. **Gate d'uscita: AC10 è di nuovo verde.** `python -m pytest tests/test_engine_ac10_recalc_equivalence.py -q` passa sulla grana allargata: `recalculate()` ≡ `full_recalculate()`, valori identici con `==`.
  4. `neighbors(con, "plant", …, as_of=<data passata>)` non solleva più `GraphSnapshotLimitationError`: la guardia di `graph.py:148` vale solo per i node type che possono avere archi derivati da `item_link` (GRAFO-01).
  5. La suite completa resta verde, senza regressioni su AC11 e AC12.
**Plans**: 5 piani in 4 wave
  - [ ] `06-01-PLAN.md` — Fondazioni: `division_key -> region` e `EligibilityIndex` per `(manufact_key, region, date_key)` (wave 1)
  - [ ] `06-02-PLAN.md` — GRAFO-01: guardia `as_of` di `neighbors()` ristretta al node type `item` (wave 1)
  - [ ] `06-03-PLAN.md` — Allargamento atomico della grana in `RecalcEngine` (wave 2)
  - [ ] `06-04-PLAN.md` — Gate d'uscita: AC10 di nuovo verde sulla grana allargata (wave 3)
  - [ ] `06-05-PLAN.md` — AC11/AC12 senza regressioni, suite completa e delta misurato (wave 4)
**Note**: **Questa fase deve restare isolata.** Riapre un motore chiuso e verde, e il difetto è un gradino più in basso di come lo descrive la sua formulazione breve: aggiungere un parametro `region` a `_eligible_plant_for` senza allargare la grana della cella non risolverebbe nulla, perché a monte l'informazione è già persa. Precede la Phase 8 (T6) **e** la Phase 10 (T10.0): la grana che porta la region cambia quali indici servono.

### Phase 7: Tenuta del livello scenario (T10.1 + T11.0)
**Goal**: Il livello scenario regge un chiamante che compone più operazioni in una transazione, e un confronto non fa più sparire in silenzio le misure che un planner guarda per prime.
**Depends on**: Phase 4 *(può correre in parallelo con Phase 5 e Phase 6)*
**Requirements**: AC30, AC28
**Success Criteria** (cosa deve essere VERO):
  1. `branch()`, `record_edit()` e `promote()` chiamate **dentro una transazione già aperta dal chiamante** completano senza `TransactionException` e senza emettere COMMIT/ROLLBACK propri: chi apre la transazione la chiude (AC30).
  2. `ibp/db.py` espone un unico context manager di transazione rientrante, e nessun `BEGIN TRANSACTION` nudo resta in `ibp/scenario/` (oggi cinque: `branch.py:81,113,127`, `edits.py:93`, `promote.py:332`).
  3. `compare()` restituisce **una riga per ognuna** delle 26 misure reali; `avg` e `ratio` compaiono come `not_comparable` **con motivo esplicito**, `min`/`max` come confrontabili — nessuna misura è mai assente dal risultato (AC28).
  4. Un confronto fra due scenari che differiscono **solo** su `CAPACITY_UTIL` produce una riga visibile, non zero righe: il falso "nessuna differenza" silenzioso diventa impossibile.
  5. `NonAdditiveMeasureError` continua a proteggere la scrittura a singola cella via `resolve_cell()`: la correzione riguarda l'aggregazione bulk, non allenta il rifiuto esplicito.
**Plans**: TBD
**Note**: I due pacchetti stanno nella stessa fase perché scrivono entrambi in `ibp/scenario/` — non possono correre in parallelo fra loro — e perché T11.0 dipende da T10.1. DuckDB non supporta `SAVEPOINT`: l'unica semantica corretta è la **proprietà** della transazione, non un contatore di annidamento ingenuo.

### Phase 8: Rete produttiva (T6)
**Goal**: La rete produttiva smette di essere un insieme di attributi e diventa relazioni: un planning model si mappa su più manufacturing key, una manufacturing key si produce in più plant, il routing genera domanda dipendente, e il ritorno verso le vendite è ripartito senza perdere nessuno.
**Depends on**: Phase 6, Phase 2
**Requirements**: AC4, AC5, AC6, AC7, AC9, AC27
**Success Criteria** (cosa deve essere VERO):
  1. Un planning model si mappa su più manufacturing key e viceversa, time-phased; un `override_by`/`override_at` del planner resta **distinguibile** dalla quota di regola (AC4).
  2. La stessa manufacturing key è producibile in più plant secondo `region_scope`, e l'assegnazione a un plant **non eleggibile** viene rifiutata con un errore tipizzato (AC5).
  3. Un routing obbligatorio genera la domanda dipendente del semilavorato a offset **fisso 2 mesi** letto da `routing.lead_offset_months` — un solo parametro, nessun ramo condizionale — e la capacità viene consumata in **entrambi** i plant (AC6).
  4. Il percorso "Excel che scrive sul database" non serve più: la domanda dipendente è generata dal routing (AC9).
  5. Un routing elettivo NAM produce split **diversi** al variare del mix di configurazione (AC7).
  6. Nella back-allocation del job `3000`, nessun planning model con contributo forward non nullo riceve zero, e la somma ripartita coincide **esattamente** col totale confermato, con correzione a resto massimo (AC27).
**Plans**: TBD
**Note**: Sottopacchetti in ordine: **T6.a** risoluzione N:N (AC4) → **T6.b** eleggibilità per region (AC5) → **T6.c** routing obbligatorio e domanda dipendente (AC6, AC9) → **T6.d** routing elettivo e back-allocation (AC7, AC27). **Da risolvere quando si pianifica T6.d**: D-006 richiede un **insieme** di attributi di configurazione estendibile senza modifiche di schema, mentre `routing.variant_key` è disegnata come chiave singola opzionale — può bastare se incapsula l'insieme, ma va verificato esplicitamente. La back-allocation segue ANA-050 §3.3, che D-005 conferma essere comportamento di produzione **corrente**.

### Phase 9: Capacità e allocatore (T7)
**Goal**: La capacità smette di essere un numero in un foglio: il sistema **propone** uno split multi-plant e sa dire per quale dei due limiti una riga non ci sta.
**Depends on**: Phase 8
**Requirements**: AC3, AC8
**Success Criteria** (cosa deve essere VERO):
  1. `Average Assembly Hours` ha un consumatore reale nell'allocatore; i test verificano la **meccanica** del consumo, mai il valore assoluto del campo, che resta marcato da revisionare prima del go-live (AC3, D-007).
  2. Una riga di Basic Assembly a Northfield viene respinta perché sono finiti gli **slot** della assembly island, con motivo esplicito (D-001, primo limite).
  3. La stessa riga viene respinta perché sono finite le **ore** del pool mensile, in un caso in cui gli slot sono ancora disponibili (D-001, secondo limite): i due modi di esaurimento sono coperti da test **separati**.
  4. L'allocatore **propone** uno split multi-plant — dentro l'orderbook sull'orderbook, oltre l'orderbook sul mix osservato a consuntivo — e l'aggiustamento manuale del planner resta tracciato (AC8).
  5. `AllocationStrategy` resta un'interfaccia sostituibile: nessun solver esterno entra in M1, ma il punto di innesto esiste (REQ-A3).
**Plans**: TBD
**Note**: D-001 è un vincolo **doppio** con controlli **indipendenti** — confermato dal product owner il 2026-09-19, supersede la lettura "solo slot". Lo slot-equivalence factor (es. ×2 di Westvale) è master data (`factor=2`), mai un literal: AC2 vale anche qui.

### Phase 10: Costruzione del motore in bulk (T10.0)
**Goal**: Costruire il motore smette di costare quattordicimila query, senza che cambi un solo risultato.
**Depends on**: Phase 6 *(la grana che porta la region cambia quali indici servono; può correre in parallelo con Phase 8, 9, 11, 12 — percorsi disgiunti)*
**Requirements**: AC29
**Success Criteria** (cosa deve essere VERO):
  1. `RecalcEngine.__init__` esegue **meno di 25 query** sul DB seed (oggi 14.397, misurate con connessione-proxy) e completa in **meno di 5 secondi** (AC29).
  2. **Entrambi** i livelli di N+1 sono chiusi: né `resolve_manufacturing_items` (`graph.py:223`, 3.492 chiamate) né `resolve_identity` (`graph.py:287`, 3.498 chiamate) vengono più interrogate per chiave.
  3. Un test con connessione-proxy conta le query e **fallisce** se la soglia viene superata di nuovo: la regressione è rilevabile automaticamente, non solo per aneddoto.
  4. I risultati del motore dopo il preload sono **identici** (`==`) a quelli di prima: AC10, AC11 e AC12 restano verdi.
**Plans**: TBD
**Note**: Il conteggio di query, non il tempo, è la soglia riproducibile: il tempo misurato varia fra 15,5s e 42,7s a seconda della macchina. Le altre cache lazy per-chiave (`_item_factor_cache`, `_plant_capacity_cache`, `_weeks_cache`, `_rate_cache`) sono lo stesso pattern su scala minore: valutare se rientrano nel preload.

### Phase 11: Ciclo P/R/A/C e i due review mancanti (T8)
**Goal**: I due review IBP che oggi non esistono — Portfolio Review e Integrated Reconciliation — diventano oggetti software di prima classe dentro il ciclo mensile che l'azienda già esegue bene.
**Depends on**: Phase 2 *(indipendente dalle Phase 6-10)*
**Requirements**: AC20, AC21, AC22, AC23
**Success Criteria** (cosa deve essere VERO):
  1. Il ciclo P→R→A→C gira con transizioni dichiarate come dato, e una scrittura su `STAT_03` viene **rifiutata** con un'eccezione tipizzata (AC20).
  2. La Portfolio Review esiste come entità con gate `PortfolioApproved` (giorni 1-5, prima di P); il suo output è input della Demand Review più consumo di capacità, e il gate è una **precondizione** verificata, non una nota (AC21).
  3. L'Integrated Reconciliation (giorni 15-16, fra A e C) genera un'**agenda dai gap sopra soglia**, in unità e in valore tramite `rate_card`, producendo `decision` ed `escalation` (AC22).
  4. `confirm_back_to_sales(cycle)` esiste, è nominata e **distinta** dalla Reconciliation: il carry-forward `3600` resta quello che è, l'anchoring non è riconciliazione (AC23).
  5. Il job `3000` esegue il carry-forward **alternato**: creando un'istanza preliminary copia dalla precedente requested, creando una requested copia dalla precedente preliminary (D-008).
**Plans**: TBD
**Note**: L'MBR resta un forum unico di cui i due gate a 15 giorni di distanza sono fasi (REQ-F5). Le soglie di eccezione sono dato configurabile con default marcati provvisori **nel dato** (`exception_rule.is_provisional`), mai literal (REQ-F3).

### Phase 12: Adapter, viste e confine di sistema (T9)
**Goal**: Il sistema legge da SAP e dEPM senza mai scriverci, restituisce il piano promosso come file, e normalizza il master data reale secondo le decisioni di dominio già prese.
**Depends on**: Phase 2 *(indipendente dalle Phase 6-11)*
**Requirements**: AC24, MDATA-01
**Success Criteria** (cosa deve essere VERO):
  1. Nessuna scrittura verso SAP S/4 né verso Infor dEPM: SAP è consumato read-only, dEPM riceve il piano promosso come **file**, ed è verificabile da test che nessun percorso di scrittura esista (AC24).
  2. Le viste per Power BI restano in forma star e `DVERSIONS.version_name` conserva la grammatica `SOP_{YYYY}_{MM}_{SIDE}_{STATUS}` leggibile come **stringa** dalle misure DAX: il contratto esterno non si muove.
  3. L'adapter tratta Southport e Rivermouth come **un solo sito** (al più con un alias): un import che li presentasse come due plant li normalizza o fallisce, mai li conta come due capacità (MDATA-01, D-003).
  4. L'adapter tratta `Eastbrook SEA` come **plant** con proprio scope produttivo, non come attributo commerciale di vendita (MDATA-01, D-004).
  5. Le convenzioni di naming `_Plant` e `-BA` sono centralizzate in **un solo punto** del codice, mai replicate (D-002).
**Plans**: TBD
**Note**: D-003 e D-004 sono vincoli sul **master data reale e sul go-live**, non sul seed: verificato il 2026-09-19 che `db/seed/data/plant_master.json` contiene nove plant e nessuno dei tre nomi. Nessun rework di T1. ERP e MRP restano fuori confine.

### Phase 13: Tronco unico e provenienza (R-001 Step A + T11.1 + T11.2)
**Goal**: Un piano salvato e uno scenario salvato diventano lo stesso tipo di oggetto — rami dello stesso tronco, elencabili, confrontabili e navigabili allo stesso modo — e ogni riga promossa risale alla propria origine.
**Depends on**: Phase 7, Phase 4
**Requirements**: R-001, AC31
**Success Criteria** (cosa deve essere VERO):
  1. Ogni nodo — piano salvato o scenario — ha **un solo** tipo di puntatore al genitore: `branch()` non deve più tenere coerenti a mano `base_version_key: int` e `parent_scenario_id: str` via `MismatchedBaseVersionError`.
  2. `SCENARIO_STATE` (Draft/Evaluated/Promoted/Discarded) e la fase di ciclo `P`/`R`/`A`/`C` sono **due assi indipendenti** che un singolo nodo può portare insieme: un ramo ufficiale può avere una fase di ciclo e contemporaneamente un proprio lifecycle di lavorazione.
  3. Una sola API di navigazione elenca piani salvati e scenari come rami dello stesso tronco: il chiamante non deve sapere in quale tabella vive un nodo per leggerlo, confrontarlo o risalirne il genitore.
  4. Ogni riga promossa risale a `origin ∈ {copied, overlay_override, prorated}`, `scenario_id` ed `edit_id` attraverso una **tabella laterale**; `TSOP_DEMAND` e `TSOP_OPS` restano isomorfe al mirror dEPM (AC31).
  5. Un planner che guarda una `DVERSIONS` promossa distingue quali righe sono un override manuale, quali sono state proratate sul mix osservato e quali sono identiche al base — oggi le tre categorie sono indistinguibili.
  6. AC13, AC14, AC15 e AC16 restano verdi: la fase è **additiva**, non riscrive T4.
**Plans**: TBD
**Note**: T11.1 (schema) e T11.2 (scrittura in `promote()`) sono **assorbiti qui**: la tabella di provenienza *è* l'arco tronco→ramo, e costruirla separatamente per poi rifarla per R-001 sarebbe lavoro duplicato. L'informazione esiste già in memoria al momento della scrittura — `overlay_touched_slices()` la calcola ed è già interrogata a `promote.py:316` — va persistita, non ricalcolata. `ScenarioStack`/`cache_key()` (`models.py:94-109`) va **esteso, non riscritto**. **Step B è fuori da M1** (grana piena di `overlay`/`edits`, `promote()` come spostamento di puntatore, risoluzione ricorsiva fino a root esplicita): collide con `DVERSIONS.version_name UNIQUE` letto come stringa dalle misure DAX.

### Phase 14: API HTTP interna (T10)
**Goal**: Tutto quello che la piattaforma sa fare diventa raggiungibile da un client locale, in modo atomico per richiesta, senza che il costo di costruzione del motore la renda inutilizzabile.
**Depends on**: Phase 5, Phase 8, Phase 9, Phase 10, Phase 11, Phase 12, Phase 13 *(è il punto in cui il lavoro parallelo converge)*
**Requirements**: API-01
**Success Criteria** (cosa deve essere VERO):
  1. Un client HTTP locale crea un ramo, applica edit, confronta due rami e promuove — l'intero giro passa dall'API, senza importare `ibp` direttamente (API-01).
  2. Più operazioni di scenario dentro **una singola richiesta** sono atomiche: o si applicano tutte o nessuna, appoggiandosi alle transazioni rientranti della Phase 7 (regge AC30).
  3. Una richiesta di ricalcolo risponde in tempi utili e restituisce `CutoffStats` osservabile dal chiamante, grazie al costruttore sotto la soglia della Phase 10 (regge AC11 e AC29).
  4. Nessun endpoint scrive verso SAP o dEPM: il confine di sistema regge anche via HTTP (regge AC24).
  5. Il server condivide **una sola** connessione DuckDB fra thread, mai fra processi: nessun `fork()`, nessun secondo writer.
**Plans**: TBD
**Note**: Se qui si misura latenza >200ms per richiesta di ricalcolo, la partizione del DAG per product family torna sul tavolo (oggi per-cella, deliberatamente). `fastapi==0.115.0`, `uvicorn==0.30.6` e `pydantic==2.9.2` sono già dichiarati in `pyproject.toml` e non ancora importati da nessun modulo.

### Phase 15: Workbench e demo CLI (T11 + T12)
**Goal**: Un planner guida la piattaforma da capo a fondo — naviga il tronco e i rami, confronta, promuove, e vede la demo girare offline — senza leggere una riga di Python.
**Depends on**: Phase 14, Phase 13, Phase 7
**Requirements**: UX-01, AC25
**Success Criteria** (cosa deve essere VERO):
  1. Il workbench elenca tronco e rami come oggetti dello **stesso tipo**, e un planner passa da un piano salvato a uno scenario senza cambiare schermata né modello mentale (UX-01).
  2. Confrontando due rami, il planner vede **anche** le misure `not_comparable`, con il motivo scritto accanto: nessuna metrica sparisce dall'interfaccia (regge AC28).
  3. L'effetto dell'early cutoff è osservabile a mano dopo un edit: il ricalcolo immediato si vede, non si deduce (AC11 in verifica manuale).
  4. La demo da riga di comando gira **end-to-end offline su Windows** — nessuna rete, nessun account, nessuna licenza — dopo `python db/build_db.py` (AC25).
  5. Il workbench è statico: nessun passo di build, nessuna CDN, nessuna dipendenza scaricata a runtime.
**Plans**: TBD
**UI hint**: yes
**Note**: T11 (`web/`) e T12 (`ibp/cli.py`, `scripts/`) stanno nella stessa fase perché sono lo stesso confine di consegna — il consumo end-to-end — e dipendono entrambi solo dalla Phase 14; i percorsi sono disgiunti, quindi i piani interni possono procedere in parallelo. `UI-SPEC.md` è prerequisito dichiarato di T11: produrlo con `/gsd:ui-phase` **prima** di `/gsd:plan-phase 15`.

### Phase 16: Documentazione e diagrammi (T13)
**Goal**: Chi arriva dopo ricostruisce il sistema e il perché delle sue scelte dai documenti, e i diagrammi dicono la verità sul codice consegnato.
**Depends on**: Phase 15
**Requirements**: AC26
**Success Criteria** (cosa deve essere VERO):
  1. I diagrammi archify sono navigabili e **coerenti col codice finale**, non con il piano iniziale (AC26).
  2. La documentazione descrive il modello a tronco e rami effettivamente consegnato nella Phase 13, non il design D3 originale che quel modello estende.
  3. Ogni decisione D-001..D-008 e R-001 è rintracciabile dalla documentazione al codice che la implementa, e `Average Assembly Hours` risulta esplicitamente marcato come da revisionare prima del go-live (D-007).
  4. Un lettore nuovo ricostruisce lo stato del progetto — cosa è fatto, cosa è differito a M2 e perché — senza aprire il codice.
**Plans**: TBD
**Note**: Ultima fase per costruzione: documenta un codice fermo. Il deliverable primario del programma resta architettura + diagrammi + scheletro eseguibile (REQ-F6): il codice rende i documenti verificabili, non il contrario.

## Dipendenze e parallelismo

**Ordine di esecuzione:** le fasi eseguono in ordine numerico. Dove la dipendenza lo permette,
queste possono correre in parallelo:

| Possono correre insieme | Perché |
|---|---|
| Phase 5, Phase 6, Phase 7 | Percorsi disgiunti: `ibp/forecast/` — `ibp/engine/` + `ibp/semantic/` — `ibp/db.py` + percorso di scrittura di `ibp/scenario/` |
| Phase 8/9 e Phase 10 | `ibp/network/` e `ibp/capacity/` contro `ibp/engine/engine.py` + `ibp/semantic/` |
| Phase 11 e Phase 12 | `ibp/process/` contro `ibp/adapters/` + `db/views/` |

**Non possono mai correre insieme:** Phase 7 e Phase 13 (entrambe in `ibp/scenario/`), e qualunque
coppia di fasi che tocchi lo stesso file — vincolo invariante del backlog.

**Catena bloccante:** Phase 6 → Phase 8 → Phase 9 → Phase 14; Phase 6 → Phase 10 → Phase 14;
Phase 7 → Phase 13 → Phase 14 → Phase 15 → Phase 16.

## Progress

**Execution Order:** le fasi eseguono in ordine numerico: 1 → 2 → … → 16.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Schema DuckDB e seed isomorfo (T1) | — (pre-GSD) | Complete | 2026-09-12 |
| 2. Dominio, semantic layer, DAG, grafo (T2) | — (pre-GSD) | Complete | 2026-09-11 |
| 3. Motore di concurrent planning (T3) | — (pre-GSD) | Complete | 2026-09-11 |
| 4. Scenari (T4) | — (pre-GSD) | Complete | 2026-09-11 |
| 5. Forecast statistico e FVA (T5) | 0/TBD | Not started | - |
| 6. Grana region nel motore (T6.0) | 0/5 | Planned | - |
| 7. Tenuta del livello scenario (T10.1 + T11.0) | 0/TBD | Not started | - |
| 8. Rete produttiva (T6) | 0/TBD | Not started | - |
| 9. Capacità e allocatore (T7) | 0/TBD | Not started | - |
| 10. Costruzione del motore in bulk (T10.0) | 0/TBD | Not started | - |
| 11. Ciclo P/R/A/C e i due review (T8) | 0/TBD | Not started | - |
| 12. Adapter, viste e confine (T9) | 0/TBD | Not started | - |
| 13. Tronco unico e provenienza (R-001 Step A) | 0/TBD | Not started | - |
| 14. API HTTP interna (T10) | 0/TBD | Not started | - |
| 15. Workbench e demo CLI (T11 + T12) | 0/TBD | Not started | - |
| 16. Documentazione e diagrammi (T13) | 0/TBD | Not started | - |

**Copertura requisiti:** 37/37 requisiti v1 mappati, nessun orfano, nessun duplicato — vedi
`.planning/REQUIREMENTS.md`.

---
*Roadmap creata: 2026-09-19, alla migrazione da `/software-house` (run `20260910-0830-ibp-platform`) a GSD.*
