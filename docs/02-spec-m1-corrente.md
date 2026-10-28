<!-- PRECEDENZA: questo documento SUPERSEDE docs/01-plan-m1.md per il dettaglio dei task,
     degli acceptance criteria e del backlog di M1. Rigenerato da sh-architect il 2026-09-12
     dopo la chiusura di T1-T4 e la revisione del modello dati. docs/01-plan-m1.md resta
     valido solo per il contesto di programma (M1/M2/M3) e la motivazione di business.
     Origine: .software-house/20260910-0830-ibp-platform/plan.md (cartella gitignored). -->

# Plan — Piattaforma IBP ACMELIFT, M1 (core + rete produttiva)

> **Rigenerato il 2026-09-12.** La versione precedente era stale e contraddittoria: numerava 9 task
> con una corrispondenza sbagliata (T5=processo, T6=adapter, T7=API, T8=workbench, T9=CLI), elencava
> 12 AC inventati qui invece dei 26 del piano approvato, e descriveva un modello dati che il codice
> ha smentito (`product_mapping`, `scenario_delta`, `DSALES_PRODUCT`/`DMANUFACT_KEY` come tabelle).
> **Cosa cambia in questa versione:** (a) numerazione e AC riallineati a `docs/01-plan-m1.md` —
> 13 task, AC1-AC26, 6 ondate; (b) `product_mapping` → `item_link` (N:N time-phased) e
> `scenario_delta` → `edits`+`overlay` in tutto il Design; (c) stato reale dei task (T1-T4 done,
> 187 test verdi); (d) T5 **sbloccato** (la diagnosi "serve MSVC" era sbagliata) con i due vincoli
> operativi dello stack 2.x; (e) i cinque debiti tecnici aperti diventano **pacchetti di piano
> numerati con dipendenze esplicite**, non note a margine; (f) T5 e T6 **esplosi in pacchetti**
> chiudibili in 120-150 turni; (g) chiuse le open question su back-allocation, offset di domanda
> dipendente, split oltre l'orizzonte e soglie di eccezione.

## Understanding

ACMELIFT ha un processo S&OP maturo (Gartner 4-) su una tecnologia che sta a 1. M1 non costruisce
un prodotto: costruisce l'**architettura** — modello di dominio, modello dati, modello di processo —
resa verificabile da uno scheletro eseguibile offline su un portatile Windows. Il ciclo P/R/A/C non
si riscrive: si preserva, ci si innestano i due review IBP mancanti (Portfolio, Integrated
Reconciliation) come oggetti software, e si sostituisce il collo di bottiglia tecnologico (scenari,
ricalcolo incrementale, forecast+FVA, eccezioni).

Il cuore di M1 è però la **rete produttiva**: i cinque punti che oggi qualcuno fa a mano ogni mese —
mapping planning model ↔ manufacturing key many-to-many, produzione dello stesso manufacturing key
in più plant con regole di region, percorsi multi-step obbligatori ed elettivi, ri-allocazione
centrale sull'orderbook, domanda dipendente del semilavorato generata in Excel con file che
scrivono sul database. Il landscape SAP S/4 → Infor dEPM → Power BI resta il padrone di casa: si
consuma, non si sostituisce; il write-back è un file.

## Acceptance criteria

I 26 criteri sono quelli approvati in `docs/01-plan-m1.md`. **Non sono stati rinumerati né
riscritti**, tranne AC6, da cui è stato tolto il condizionale sull'offset (decisione F10, chiusa:
offset fisso a 2 mesi letto da `routing.lead_offset_months`).

**Modello dati e regole**
- [x] **AC1** — `python db/build_db.py` ricostruisce il DB da zero, idempotente, con nomi dEPM
  preservati e cardinalità isomorfe (~1.661 / ~1.346 / 52 / 62).
- [x] **AC2** — `Max Slots`, granularità e la soglia `<500` sono **master data**: aggiungere un
  plant non richiede modifiche a codice. Un test fallisce se `30`, `8` o `500` compaiono nel codice
  di calcolo.
- [ ] **AC3** — `Average Assembly Hours` ha un consumatore reale (seconda valuta di capacità).

**Rete produttiva — il cuore di M1**
- [ ] **AC4** — Un planning model si distribuisce su **più** manufacturing key con percentuali
  time-phased, e più planning model **aggregano** sulla stessa manufacturing key. L'override manuale
  è tracciato e distinguibile dal valore di regola.
- [ ] **AC5** — Lo stesso manufacturing key è producibile in **più plant** secondo `region_scope`, e
  il sistema **rifiuta** un'allocazione a un plant non eleggibile.
- [ ] **AC6** — Il routing **obbligatorio** (ILK/ILT: Ganderkesee → Cerritos) genera **domanda
  dipendente** sul semilavorato, anticipata di **2 mesi fissi** (`routing.lead_offset_months`,
  master data — non una matrice per lane, non un parametro per cluster), e consuma capacità in
  **entrambi** i plant.
- [ ] **AC7** — Il routing **elettivo** (NAM) produce split diversi al variare del mix di
  configurazione, e il carico di Northfield cambia di conseguenza.
- [ ] **AC8** — L'allocatore **propone** lo split multi-plant: dall'orderbook dentro l'orizzonte,
  dal mix osservato oltre. Il planner può correggere; l'override è tracciato.
- [ ] **AC9** — Il percorso Excel→DB è sostituito: la domanda dipendente si genera dal routing, non
  da un file.

**Motore**
- [x] **AC10** — `recalculate(changed)` propaga il dirty e **il risultato è identico al ricalcolo
  completo**, su sequenze casuali di edit *(il test cardine)*.
- [x] **AC11** — L'early cutoff è osservabile e misurato: un edit che non cambia un aggregato
  **non** sporca i dipendenti.
- [x] **AC12** — Min/max/ratio sono ricalcolati sul gruppo, non delta-aggiornati.

**Scenari**
- [x] **AC13** — Branch → modifica sparsa → confronto → **promozione** che crea una **nuova**
  istanza `DVERSIONS`. Nessuna istanza esistente viene mai mutata.
- [x] **AC14** — Tombstone: una riga cancellata in uno scenario **non ricompare** dal base.
- [x] **AC15** — La cache key include lo stack: A **non** serve mai aggregati di B.
- [x] **AC16** — Promozione con base mossa dal branch time → **conflitto**, non sovrascrittura.

**Forecast**
- [ ] **AC17** — La baseline precompila la P; l'override del planner è distinguibile dal valore
  generato.
- [ ] **AC18** — L'FVA stairstep si calcola **a lag costante** da `forecast_snapshot`.
- [ ] **AC19** — Il forecast riconciliato è **coerente** lungo la gerarchia prodotto.

**Processo**
- [ ] **AC20** — Ciclo P→R→A→C con `STAT_01/02/03`; scrivere su fase `STAT_03` è **rifiutato**.
- [ ] **AC21** — Portfolio Review: output approvato = input della Demand Review **e** consumo di
  capacità; `PortfolioApproved` precondizione per aprire P.
- [ ] **AC22** — Integrated Reconciliation genera l'agenda **dai gap sopra soglia**, in unità e
  valore, e produce decisioni/escalation; l'MBR riceve un solo set di piani.
- [ ] **AC23** — `confirm_back_to_sales(cycle)` esiste come funzione nominata e distinta,
  documentata come *anchoring*.

**Confine e ambiente**
- [ ] **AC24** — Nessuna scrittura verso SAP o dEPM; il write-back è un **file**. Nessun oggetto
  ordine/BOM/MRP.
- [ ] **AC25** — Tutto **offline** su Windows: `pip install -e .` + un comando, nessun cloud,
  nessuna licenza, nessun CDN, extension DuckDB pre-installate.
- [ ] **AC26** — I diagrammi archify sono navigabili e coerenti con il codice finale.

### Estensioni decise il 2026-09-12

Cinque criteri **aggiuntivi**, non sostitutivi: nascono da difetti misurati sul codice reale, ognuno
rompe un task a valle se non viene chiuso prima. Numerati da AC27 per non perturbare AC1-AC26.
`sh-docs` (T13) li riporta in `docs/01-plan-m1.md` a fine run.

- [ ] **AC27** — **Back-allocation (job `3000`, OPS→Sales).** Sulle manufacturing key aggreganti,
  nessun planning model con contributo forward non nullo riceve zero. La quantità confermata torna
  indietro dai **contributi effettivi del passaggio forward**, non da `SalesModel` né da una
  `quota_pct` ricalcolata; il secondo stadio (planning model → division/region) è pro-rata sulla
  requested production con correzione a **resto massimo**. La somma ripartita è uguale al totale
  confermato, esattamente.
- [ ] **AC28** — **Misure non confrontabili, non invisibili.** `compare()` restituisce una riga per
  ogni misura del catalogo: `sum`/`min`/`max` con delta calcolato; `avg`/`ratio` con stato
  `not_comparable` e motivo. Nessuna misura sparisce dal risultato. Test sulle 26 misure reali
  (19 `sum`, 1 `max`, 3 `avg`, 3 `ratio`).
- [ ] **AC29** — **Costo di costruzione del motore.** `RecalcEngine.__init__` sul DB seed standard
  emette **meno di 25 query** verso DuckDB (oggi 14.394) e converge in **meno di 5 s** (oggi 42,7 s).
  La soglia primaria è il conteggio di query, non il tempo: il tempo dipende dalla macchina, il
  conteggio no.
- [ ] **AC30** — **Transazioni rientranti.** Una funzione di scrittura di `ibp/scenario/` chiamata
  dentro una transazione già aperta dal chiamante non solleva
  `TransactionException: cannot start a transaction within a transaction` e non emette COMMIT o
  ROLLBACK propri; un rollback del chiamante annulla anche il suo effetto.
- [ ] **AC31** — **Provenienza della riga promossa.** Per ogni istanza `DVERSIONS` prodotta da
  `promote()`, ogni riga è risalibile a: origine (`copied` | `overlay_override` | `prorated`),
  scenario di provenienza e `edit_id` quando esiste. `TSOP_DEMAND`/`TSOP_OPS` restano isomorfe al
  mirror dEPM: la provenienza vive in una tabella laterale.

## Design

### D1 — Semantic layer: mirror dEPM + graph overlay

Lo star schema dEPM è **rispecchiato** come nucleo canonico (i nomi dei fatti restano quelli del
cubo reale: `TSOP_DEMAND`, `TSOP_OPS`, `TWSC_PAR_CALWEEK`, più `DPLANT`, `DSALES_DIVISION`,
`DVERSIONS`, `DMEASURE_DEMAND/OPS`, `DIM_DATE`) ed esteso con **una** tabella di archi tipizzati
`edge(from_type, from_key, rel_type, to_type, to_key, valid_from, valid_to, attrs_json)`.

**Correzione rispetto alla versione precedente del piano**: `DSALES_PRODUCT` e `DMANUFACT_KEY`
**non esistono come tabelle**. T1 le ha collassate in `item(item_key, role, region, is_sellable,
manufacturing_category, …)` più `item_identifier` per le identità datate (`element_name`, `caption`,
`sap_material`, `legacy`) — erano tre tabelle per la stessa entità, con il legame nascosto nei
suffissi del nome (`-BA`, `-BR`, `_Plant`). `item_identifier` è ciò che chiude il caption drift e il
caso Steyr. Ogni prompt verso un implementatore deve dire che `db/schema.sql` è la verità.

*Perché mirror e non EKG:* lo star schema è l'ontologia già concordata e Power BI ci si appoggia;
riscriverla romperebbe l'unico asset semantico condiviso. Ma il grafo è necessario, non ornamentale:
la rete multi-tier di M2/M3 (dealer, importatore, installatore, fornitore) non entra in uno star
schema. `from_type`/`to_type` sono testo libero: M2/M3 aggiungono nodi senza migrazione.

**Contratto già in vigore, da non violare a valle:** ogni numerico restituito dal semantic layer è
`float`, mai `Decimal` (chi espone una colonna `DECIMAL` — p.es. `rate_card` — casta nel row
constructor); `neighbors()` solleva `GraphSnapshotLimitationError` per `as_of` strettamente passato
sui `rel_type` derivati da `item_link`, e per una risposta datata si usa
`resolve_manufacturing_items()`.

### D2 — Rete produttiva: da attributi a relazioni (e `item_link`, non `product_mapping`)

Quattro tabelle sostituiscono due attributi (`Linked Manufact Key`, `Targeted Plant`):

```
item_link(from_item, to_item, link_type, period, quota_pct, quota_source,
          quota_window_months, offset_months, override_by, override_at, valid_from, valid_to)
     → F7. UNA sola tabella di legami tipizzati e datati
       ('produces' | 'aggregates' | 'splits' | 'dependent_demand'),
       al posto del `product_mapping` che il piano vecchio descriveva e che non esiste.
       quota_source ∈ {rule, observed_history, manual_override} distingue regola da override.

production_eligibility(manufacturing_key, plant, region_scope, priority, valid_from, valid_to)
     → F8. Chi PUÒ fare cosa, per quale region. region_scope ∈ {APAC,CIS,EMEA,LATAM,NAM,GLOBAL}.

routing(manufacturing_key, variant_key?, step_no, plant, operation_type,
        lead_offset_months, mandatory)
     → F9/F10. mandatory=true → Cerritos/ILK, Niagara: non è una scelta.
       mandatory=false → caso NAM: lo step dipende dalla configurazione venduta.

bill_of_resource(manufacturing_key|variant_key, resource_id, qty_per_unit,
                 offset_periods, spread_profile_json) + resource + resource_capacity
     → capacità per step, con l'offset. È lo spread esistente, generalizzato.
```

**La quota degli split è il mix osservato a consuntivo** (`quota_source='observed_history'` con
`quota_window_months`), non una percentuale mantenuta a mano: oltre l'orizzonte dell'orderbook è
l'unica base ancorata ai fatti. L'override del planner resta possibile e resta distinguibile — è
esattamente AC4. Invariante verificata da `build_db.py`: le quote di ogni
`(from_item, link_type, period)` sommano a 100.

**Grana del nodo del DAG: `(manufact_key, region, date_key)`, non `(manufact_key, date_key)`.**
È l'unica modifica di design che il codice reale ha reso obbligatoria: oggi
`derived_manufacturing_demand` aggrega su `(manufact_key, date_key)` e **perde la region della
domanda**, quindi `_eligible_plant_for` (`ibp/engine/engine.py:209`) non ha nemmeno il dato con cui
filtrare per `region_scope` — sceglie il plant a priorità minima e lo cachea per `manufact_key`
soltanto, ignorando `date_key`. È corretto oggi solo perché il seed lascia
`production_eligibility.valid_to` NULL, ed è silenziosamente sbagliato appena AC5 è vera. La region
va portata fino al punto in cui serve: si estende la grana, non si aggiunge una caccia alla region a
posteriori. Vedi T6.0.

**Domanda dipendente (F10, AC6/AC9)**: il semilavorato è un `item` con domanda propria, generata dal
routing con offset **fisso a 2 mesi**, letto da `routing.lead_offset_months` come master data. Un
solo parametro, non una matrice per lane, nessun ramo condizionale nel codice. È la sostituzione
diretta del file Excel che scrive sul database.

**Back-allocation (job `3000`, OPS→Sales) — AC27.** La regola ANA-050 §3.3 risolve il planning model
via l'attributo `SalesModel` di `DMANUFACT_Key`, che è **monovalore**: sulle 7 manufacturing key
aggreganti attribuisce l'intera quantità confermata a un solo planning model e gli altri ricevono
zero, e la correzione si fa a mano in Excel ogni ciclo. Il nostro modello non ha quel limite perché
`item_link` registra tutte le quote N:N time-phased. La back-allocation è quindi il **cammino
inverso in due stadi**: (a) manufacturing key → planning model sui **contributi effettivi del
passaggio forward** (non `SalesModel`, non una `quota_pct` ricalcolata: i contributi veri, quelli
che il forward ha usato); (b) planning model → division/region pro-rata sulla requested production,
con correzione a **resto massimo** come in ANA-050. È l'inverso della risoluzione N:N che T6
possiede, e sta in T6.

### D3 — Scenari: event log → overlay → layer stack

```
edits(append-only) → overlay(scenario_id, …, value, is_deleted) → COALESCE(l3, l2, l1, base)
```

`scenario_delta` del piano vecchio non esiste: sono due tabelle, `edits` (verità append-only, che dà
undo/redo, audit per l'FVA e ricostruzione deterministica) e `overlay` (cache, con tombstone
esplicito `is_deleted` — mai `NULL` come sentinella). La promozione materializza una **nuova**
istanza `DVERSIONS` conforme alla convenzione di naming; nessuna istanza esistente viene mai mutata.
La convenzione di naming è logica applicativa portante (le misure DAX ricostruiscono i nomi come
stringhe), ed è il motivo per cui i what-if non nascono come membri `DVERSIONS`.

**Tre correzioni già a terra, da conoscere:**
1. Determinismo di lettura e scrittura: `materialize_version` non usa `SUM(...) GROUP BY` (somma
   parallela non riproducibile nell'ultimo bit) ma `ORDER BY` sulla PK piena + somma in Python;
   `promote()` distingue "fetta mai toccata" (copiata byte per byte) da "toccata, stesso valore".
2. Isolamento fra scenari su basi diverse (AC15): `MismatchedBaseVersionError`,
   `CellVersionMismatchError`, filtro su `version_key` come difesa in profondità.
3. `base_snapshot_id` è un'**impronta di contenuto**, non un'etichetta. Chiuso il 2026-09-12: il
   seed emette il sentinella `PENDING_DIGEST`, `db/build_db.py::_stamp_base_snapshots` lo sostituisce
   con il digest vero riusando `ibp.scenario.overlay.base_content_digest` (una sola implementazione
   dell'algoritmo, non due che divergono), e `_validate()` fa fallire il build se un sentinella
   sopravvive o se il digest non combacia. Prima di questo, AC16 non verificava nulla sui due
   scenari seminati — gli unici promuovibili spediti, quelli che la demo di T12 attraversa.

**Due contratti da aggiungere (AC28, AC31), decisi il 2026-09-12:**

- **Misure non additive: `not_comparable`, non invisibili.** Oggi `materialize_version` filtra a
  `agg_method='sum'`, quindi `compare()` **non le vede affatto** e la UI di T11 mostrerebbe "nessuna
  differenza" per l'utilizzo di capacità — un falso negativo silenzioso su una delle misure che il
  planner guarda per prime. Catalogo reale: 19 `sum`, 1 `max` (`SLOTS_AVAILABLE`), 3 `avg`
  (`AVG_MAX_CAPACITY`, `WEEKS_PRODUCTION`, `FROZEN_ZONE`), 3 `ratio` (`ORDER_COVERAGE`,
  `CAPACITY_UTIL`, `PLANT_RELIABILITY`). Decisione: `min`/`max` **sono** ricombinabili alla grana di
  overlay e vanno confrontate; `avg`/`ratio` no — la loro ricombinazione richiede i denominatori,
  che `overlay` non traccia. `CompareRow` guadagna uno stato esplicito `not_comparable` con motivo,
  invece di far sparire la riga. Il contratto va riflesso in `UI-SPEC.md` prima che T11 scriva
  markup.
- **Provenienza della riga promossa.** `promote()` sa già distinguere riga copiata bit-identica,
  override da overlay e valore ripartito (`overlay_touched_slices()` calcola esattamente
  quell'insieme), ma **butta via l'informazione** dopo aver scritto la nuova istanza. Si persiste in
  una **tabella laterale** — non una colonna su `TSOP_DEMAND`/`TSOP_OPS`, che sono mirror dEPM e
  devono restare isomorfe — con origine, scenario di provenienza e riferimento all'edit. Serve a T11
  per colorare la cella modificata, quindi si decide prima di T11 e si riflette in `UI-SPEC.md`.

**Transazioni rientranti (AC30).** Tutti gli helper di scrittura di `ibp/scenario/` emettono un
`BEGIN TRANSACTION` nudo (`branch.py:81,113,127`, `edits.py:93`, `promote.py:332`). Verificato:
DuckDB solleva `TransactionException: cannot start a transaction within a transaction` e **non
supporta SAVEPOINT**, quindi appena T10 avvolge una di queste chiamate in una propria transazione,
fallisce. Serve un context manager rientrante in `ibp/db.py` che, se una transazione è già aperta,
**non la possiede** (niente COMMIT/ROLLBACK propri) e lascia decidere al chiamante più esterno.
Essendo `ibp/db.py` l'unico punto di accesso a DuckDB, è il posto giusto e l'unico.

### D4 — Motore: DAG dichiarato, height, early cutoff, preload bulk

Il DAG è **dichiarato** in `ibp/semantic/measures.py` (`MEASURE_DAG`, che non calcola nulla) ed
**eseguito** in `ibp/engine/`. Due nodi sorgente (`requested_production` da `TSOP_DEMAND`,
`confirmed_production` da `TSOP_OPS`), quattro calcolati
(`derived_manufacturing_demand → slots_requested → gap_req_conf → value_gap`, con `gap_req_conf`
che dipende da **entrambe** le radici). Ricalcolo in min-heap per height: un nodo con due percorsi si
ricalcola una volta sola, a input correnti. Early cutoff sull'hash del valore. `CutoffStats` ha un
quarto termine `absent` perché la sparsità del master data non è risparmio di ricalcolo e un
pannello di T10 la leggerebbe come tale.

AC10 regge per costruzione: ogni cella di ogni nodo derivato ha **una sola** `_compute_*_cell()`,
chiamata identica da `full_recalculate()` e da `recalculate()`; l'unica differenza fra i due è quali
chiavi vengono visitate. Ogni arco `_downstream` rispecchia esattamente le letture della
`_compute_*_cell` corrispondente. Chi tocca il motore deve preservare questa proprietà, o AC10 smette
di essere vera per ragioni che nessun test locale mostra.

**Costo di costruzione (AC29).** Misurato il 2026-09-12: 42,7 s, di cui 95% dentro DuckDB,
**14.394 query emesse**. Ripartizione: `resolve_manufacturing_items` 3.492× = 26,3 s;
`item_identifier` 3.498× = 5,3 s; `SELECT role FROM item` 3.492× = 3,2 s; `TWSC_PAR_CALWEEK`
2.814× = 2,1 s; `production_eligibility` 469× = 1,2 s. Il master data coinvolto è minuscolo
(`item_link` 3.516 righe, `item` 3.010, `TWSC_PAR_CALWEEK` 4.257, `production_eligibility` 582,
`rate_card` 4, `routing` 16): **sta tutto in memoria**. La cura non è una cache più furba ma un
**preload bulk nel costruttore**, ~6 query invece di 14.394 — le cache lazy per-chiave spariscono.
Da fare prima di T10, che costruirebbe un layer HTTP sopra `__init__`.

### D5 — Forecast statistico e FVA

**T5 è sbloccato. La diagnosi precedente era sbagliata su entrambi i punti**: `statsforecast==1.7.8`
**non esiste su PyPI** (la serie 1.7 finisce a 1.7.6, poi salta a 2.0.3); pip non trovava la
versione, ripiegava sulla sdist e falliva in compilazione — l'errore MSVC era il **sintomo**, non la
causa. La serie 2.x ha sostituito `numba` con `coreforecast` e pubblica wheel `cp313-win_amd64`.
`pyproject.toml` è già aggiornato a `statsforecast==2.1.1`, `hierarchicalforecast==1.5.1`,
`utilsforecast==0.2.16`; installato e verificato su questa macchina (AutoETS + AutoARIMA +
SeasonalNaive, riconciliazione BottomUp + MinTrace(ols), coerenza gerarchica a 2.8e-14).
**Nessun MSVC richiesto.** L'extra `[forecast]` resta separato per un motivo modesto: tira dentro
~11 pacchetti che il resto di M1 non usa.

**Due vincoli operativi, entrambi non negoziabili:**

1. **Ordine di import — segfault, non eccezione.** `hierarchicalforecast._lib` e
   `coreforecast`/`utilsforecast` sono due estensioni C++ con runtime OpenMP distinti nello stesso
   processo. Se `utilsforecast` si carica per primo, il successivo import di
   `hierarchicalforecast.utils` termina il processo con **SIGSEGV senza traceback**; e
   `hierarchicalforecast/utils.py` importa `utilsforecast` *prima* del proprio `_lib`, quindi anche
   `import hierarchicalforecast.utils` come prima riga del programma va in crash. Nessuna variabile
   d'ambiente lo evita (`OMP_NUM_THREADS`, `KMP_DUPLICATE_LIB_OK`, `MPLBACKEND`: tutte testate,
   tutte inutili). Il modulo di forecast apre **con questa riga, prima di ogni altro import del
   pacchetto**:
   ```python
   from hierarchicalforecast._lib import reconciliation as _hf_lib  # noqa: F401
   ```
   Il test di regressione deve lanciare l'import in un **subprocess** e verificare
   `returncode == 0`: dentro il processo di pytest un segfault non è catturabile come eccezione,
   fa cadere l'intero runner.
2. **API 1.x**: `HierarchicalReconciliation.reconcile()` prende `S_df=`, non `S=`. Codice o
   documentazione scritti contro la 0.4.3 non funzionano così com'è.

**La gerarchia di riconciliazione è quella commerciale, non quella manifatturiera.** MinTrace
richiede una gerarchia **strettamente** consistente, e `item_link` è N:N per costruzione: un
manufacturing item sotto due planning model romperebbe la coerenza in silenzio, che è precisamente
il modo in cui questa classe di bug si spedisce. Si riconcilia lungo
`division ▶ product line ▶ category ▶ model` (un albero vero); l'N:N sta **a valle** del forecast,
nella risoluzione verso la produzione, dove ha una semantica di quota e non di padre.

**FVA nello schema dal giorno 1** (`forecast_snapshot(series_id, target_period, created_period, lag,
process_step, value)`, più `forecast_override` e `actual_restatement`): ha senso solo a **lag
costante**, e salvare solo l'ultimo forecast distruggerebbe l'FVA per sempre. Stairstep
`Naïve → Baseline → Rettificata → Consenso`. **FVA negativo allo step del planner è comune e
onesto** — è il risultato che rende la demo credibile, non un difetto da nascondere.

**Vincolo di scala noto da T1**: il volume dei fatti è cappato agli ultimi 4 cicli chiusi + ciclo
corrente + `SOP_BP_2027`. La baseline ha quindi meno storia di quanta ne avrebbe in produzione — con
24-36 mesi l'ordine ARIMA è già a malapena identificabile, con meno lo è ancora meno. **Verificare
la copertura effettiva prima di scegliere il pool**, non dopo (open question 2).

### D6 — Processo, i due review mancanti, confine

**Portfolio Review** giorni 1-5, prima di P; gate `PortfolioApproved` precondizione per aprire P.
Entità già a schema: `portfolio_item`, `project`, `project_resource_demand` (è ciò che rende il
piano *resourced*), `portfolio_decision`. **Integrated Reconciliation** giorni 15-16, fra A e C:
`gap` in unità **e** valore, `reconciliation_session` con agenda **generata** dai gap sopra soglia,
`decision`, `escalation`; `rate_card` finanziarizza. Output verso l'MBR: un solo set di piani più una
lista decisioni. Il carry-forward `3600` resta e viene **nominato**: `confirm_back_to_sales(cycle)`,
funzione di dominio esplicita e distinta dalla Reconciliation — il sistema non lo toglie, chiarisce
che è *anchoring*.

**Confine (AC24)**: SAP S/4 si **consuma** read-only, mai si scrive; a Infor dEPM si **restituisce il
piano promosso come file** per Application Studio; Power BI non si tocca (si espongono viste in forma
star con i nomi dEPM preservati); ERP/MRP fuori confine. È un sistema di pianificazione, non un
secondo ERP: se un oggetto ha una controparte transazionale in SAP, qui esiste solo come chiave e
attributi di pianificazione.

### D7 — Layout, ambiente, tooling

```
pyproject.toml           # tutte le dipendenze, una volta (T1, proprietà esclusiva)
db/  schema.sql  build_db.py  seed/  seed/data/*.json  views/
data/ibp.duckdb          # generato, gitignored
ibp/
  config.py  db.py       # unico punto di accesso DuckDB
  domain/      entità, macchine a stati, errori tipizzati
  semantic/    dimensions, graph, measures (DAG dichiarato), registry
  engine/      recalc incrementale (height, early cutoff, pull)
  scenario/    event log, overlay, confronto, promozione
  forecast/    baseline, riconciliazione gerarchica, FVA        (T5)
  network/     risoluzione N:N, eligibility, routing, dep. demand, back-alloc (T6)
  capacity/    bill of resource, slot equivalence, RCCP, allocatore (T7)
  process/     ciclo P/R/A/C, 5 review, gate, RACI, 3600         (T8)
  adapters/    infor_import, sap_master, powerbi_export, infor_writeback (T9)
  api/         router FastAPI                                    (T10)
  cli.py       comandi + demo end-to-end                         (T12)
web/           workbench statico (no build, no CDN)              (T11)
docs/          01-06 + diagrammi archify                         (T13)
tests/         proprietà esclusiva di sh-tester
```

**Ambiente (AC25), gotcha Windows già in `README.md`:** autoload delle extension DuckDB disattivato
(altrimenti il primo uso tenta un download e rompe la demo offline); `temp_directory` esplicito;
DuckDB single-writer con lock di processo — il server UI e i job condividono **una** connessione
(thread, non processi); niente `fork()`; RNG deterministico via `hashlib`, non `hash()` (salato per
processo); versioni pinnate, `polars` compresa.

**Deroga registrata, da non riaprire:** `pyproject.toml` è di proprietà esclusiva di T1 ed è stato
riaperto una volta il 2026-09-12 per correggere il pin di `statsforecast` e introdurre l'extra
`[forecast]`. La correzione è a terra e verificata; nessun task successivo lo tocca di nuovo.

## Open questions

1. **`Average Assembly Hours` (AC3)** — l'attributo esiste sul `DMANUFACT_KEY` reale e **nessuna
   misura lo legge**. *Consigliato:* implementarlo in T7 come **valuta alternativa agli slot** per i
   plant a isole (il pool `plant_hour_pool` è già previsto in `resource.node_type`), lasciando lo
   slot come valuta primaria. Resta da confermare con l'utente che il dato sia popolato davvero e
   non solo dichiarato: se è vuoto in produzione, AC3 si chiude con un consumatore che legge un
   attributo mai valorizzato, che è peggio di non averlo.
2. **Pool di modelli per T5, data la storia corta.** Il cap sui fatti di T1 lascia meno storia di
   quanta ne servirebbe. *Consigliato:* pool `AutoETS` + `SeasonalNaive` + `AutoTheta` +
   `CrostonOptimized` (intermittenti), con `AutoARIMA` **disabilitato di default** e attivabile da
   configurazione; selezione per MASE cross-validata, `SeasonalNaive` come fallback. Su
   riconciliazione: **`MinTrace(ols)` titolare** (verificato su questa macchina) e `BottomUp` come
   confronto; `MinTrace(mint_shrink)` solo se `fitted=True` regge su **ogni** serie — con storia
   corta è la condizione che salta per prima, e quando salta lo fa in silenzio. Decisione da
   confermare misurando la copertura effettiva nel primo pacchetto di T5, non prima.
3. **`variant_key` nel routing elettivo (AC7)** — quale attributo della configurazione venduta guida
   davvero lo split fra Northfield e Niagara. Il colore è l'esempio che gira, non la variabile.
   *Consigliato:* modellarlo come **chiave opaca alimentata dall'orderbook**, così il sistema
   funziona prima di sapere quale attributo sia e lo scopre a consuntivo. È la scelta che non
   richiede una risposta per procedere.
4. **Da quale istanza copia il job `3000` (T8)** — il vault lo nomina e non lo specifica mai, e
   l'incidente noto del rollover 2023→2024 dice che l'assunzione sbagliata non produce un errore ma
   un inventario non calcolato. *Consigliato:* parametro esplicito (`copy_from: version_ref`) invece
   di un default implicito. Una conversazione di cinque minuti lo chiude, ma va fatta prima di T8.
5. **Granularità della partizione del DAG** — il motore oggi lavora a grana di cella-chiave, non per
   partizione. *Consigliato:* mantenere così per M1 (il ricalcolo misurato regge) e introdurre la
   partizione per **product family** solo se T10 mostra latenza sopra i 200 ms; è un'ottimizzazione,
   non un requisito. Non blocca nulla.

*Chiuse il 2026-09-12, non più questioni:* split oltre l'orizzonte dell'orderbook (deciso: mix
osservato a consuntivo, già a schema come `quota_source='observed_history'` con
`quota_window_months`); offset di domanda dipendente (deciso: **fisso a 2 mesi**, da
`routing.lead_offset_months`); back-allocation `3000` (decisa: cammino inverso in due stadi, AC27);
soglie di eccezione (decise: seed con ±20% w/w e i tre livelli, marcati provvisori **nel dato** via
`exception_rule.is_provisional`, non nel commento).

## Backlog

13 task canonici, 6 ondate, più 6 **pacchetti preparatori** numerati in decimale sotto il task che
sbloccano (T6.0, T10.0, T10.1, T11.0, T11.1, T11.2): sono debiti misurati sul codice reale, ognuno
rompe un task a valle se non chiuso prima, e compaiono qui con owner, path e criterio di chiusura
come qualunque altro task.

**Vincoli invarianti**: `pyproject.toml` è di proprietà esclusiva di T1 (già riaperto una volta,
deroga registrata in D7); `tests/**` è di proprietà esclusiva di `sh-tester` e non compare mai nei
path di un implementatore; due task nella stessa ondata non toccano mai lo stesso file; tutto offline
su Windows; nessuna scrittura verso SAP o dEPM.

**Criterio di chiusura di un pacchetto** (vincolo operativo, non stilistico): le ultime due sessioni
hanno sforato il budget di contesto (171 turni e oltre 150). Ogni pacchetto si chiude con un **punto
pulito** — suite verde, commit, una riga di stato in `state.md` — e va dimensionato per 120-150
turni. Un pacchetto che non si chiude in quel budget va spezzato, non esteso.

---

### T1 — Schema DuckDB + seed isomorfo
stato: **done** (riaperto due volte: extra `[forecast]`, digest di `base_snapshot_id`)
owner: sh-data · ondata: 0 · depends_on: none
paths: `pyproject.toml`, `README.md`, `db/schema.sql`, `db/build_db.py`, `db/seed/**`, `.gitignore`
done_when: `python db/build_db.py` ricostruisce `data/ibp.duckdb` da zero, idempotente su run
consecutivi (hash di contenuto per tabella), con `_validate()` che fa fallire il build su invariante
violata. **Fatto**: AC1, AC2, AC16 lato seed.
notes: tre scelte da conoscere a valle — (1) **volume dei fatti cappato** agli ultimi 4 cicli chiusi
+ ciclo corrente + `SOP_BP_2027`, che tocca T5 (meno storia per la baseline); (2) i magic number di
capacità vivono in `db/seed/data/*.json`, e l'unico `8` residuo nei `.py` è `encoding="utf-8"` — il
test anti-literal lo esclude esplicitamente; (3) `numpy` deliberatamente non in dipendenze.
Chiuso il 2026-09-12: `db/seed/scenario.py` emette il sentinella `PENDING_DIGEST` e
`_stamp_base_snapshots` lo sostituisce col digest vero riusando
`ibp.scenario.overlay.base_content_digest` — una sola implementazione dell'algoritmo. Prima, AC16 non
verificava nulla sui due scenari seminati, che sono gli unici promuovibili spediti e quelli che la
demo di T12 attraversa.

### T2 — Dominio, macchine a stati, semantic layer, DAG dichiarato, grafo
stato: **done** (critic PASS al giro 2)
owner: sh-backend · ondata: 1 · depends_on: T1
paths: `ibp/__init__.py`, `ibp/config.py`, `ibp/db.py`, `ibp/domain/**`, `ibp/semantic/**`
done_when: fatto — registry che legge i metadati dal DB, `neighbors()`, `resolve_manufacturing_items()`,
`MEASURE_DAG` dichiarato senza calcolare.
notes: debito residuo noto, non bloccante: `graph.py:148` la guardia `as_of` è troppo larga per node
type (`neighbors("plant", …)` con data passata solleva anche se un nodo plant non può portare archi
item-link — T6 la incontrerà su una query storica plant→region legittima; fix minimo: saltare la
guardia se `node_type != "item"`); `graph.py:146` un `datetime.datetime` passato come `as_of`
solleva `TypeError`.

### T3 — Motore concurrent planning
stato: **done** (2 giri critic)
owner: sh-backend · ondata: 2 · depends_on: T2
paths: `ibp/engine/**`
done_when: fatto — AC10, AC11, AC12 verdi.
notes: quattro difetti chiusi che non vanno reintrodotti — batch non atomico (un edit malformato
bricckava il motore per sempre, e sarebbe arrivato da una richiesta HTTP di T10);
`confirmed_production` assente dal DAG dichiarato pur essendo eseguita come root;
`CutoffStats.absent` (2.352 falsi "cutoff" erano sparsità del rate card); rumore floating-point
eliminato alla sorgente, non con `math.isclose`.

### T4 — Scenari: event log, overlay, confronto, promozione
stato: **done** (2 giri critic)
owner: sh-backend · ondata: 2 · depends_on: T2
paths: `ibp/scenario/**`
done_when: fatto — AC13, AC14, AC15, AC16 verdi. Suite complessiva a 187 test.
notes: i cinque difetti chiusi sono in D3. Restano tre debiti, ora pacchetti espliciti: T10.1
(transazioni), T11.0 (`not_comparable`), T11.1/T11.2 (provenienza).

---

### T5 — Forecast statistico + riconciliazione gerarchica + FVA
stato: **sbloccato, prossimo da fare** · owner: sh-backend · ondata: 2 · depends_on: T2
paths: `ibp/forecast/**`
copre: AC17, AC18, AC19
done_when: i tre pacchetti T5.a/T5.b/T5.c sono chiusi e AC17-AC19 sono verdi.
notes: leggere D5 **per intero** prima di scrivere una riga. I due vincoli che fanno perdere una
giornata se scoperti per tentativi: l'ordine di import (segfault senza traceback, nessuna variabile
d'ambiente lo evita) e `reconcile(S_df=...)`. Lo stack è installato e verificato su questa macchina:
non re-diagnosticare l'installazione.

#### T5.a — Guardia di import, estrazione serie, gerarchia di riconciliazione
owner: sh-backend · depends_on: T2
paths: `ibp/forecast/__init__.py`, `ibp/forecast/series.py`
copre: fondamenta di AC17-AC19 + contributo ad AC25
done_when: `ibp/forecast/__init__.py` ha come **prima riga** l'import di
`hierarchicalforecast._lib` con il commento che spiega perché; esiste un test di regressione
(sh-tester) che lancia `python -c "import ibp.forecast"` in un **subprocess** e verifica
`returncode == 0`; `series.py` estrae le serie mensili da `TSOP_DEMAND` e costruisce la matrice di
somma `S_df` sulla **gerarchia commerciale** (`division ▶ product line ▶ category ▶ model`), con un
controllo che fallisce se la gerarchia non è un albero; è misurata e stampata la **copertura di
storia effettiva** per serie (mesi disponibili, distribuzione), che è l'input della decisione sul
pool. Suite verde, commit, riga in `state.md`.
notes: la gerarchia **non** è quella manifatturiera — `item_link` è N:N e romperebbe la consistenza
richiesta da MinTrace in silenzio (D5). Il subprocess non è pignoleria: dentro pytest un segfault
abbatte il runner e il fallimento si presenta come "la suite si è interrotta", non come un test
rosso.

#### T5.b — Baseline statistica e riconciliazione gerarchica
owner: sh-backend · depends_on: T5.a
paths: `ibp/forecast/baseline.py`, `ibp/forecast/reconcile.py`
copre: **AC19**, prima metà di **AC17**
done_when: `baseline(series, as_of)` produce una previsione per ogni serie con il pool deciso in
T5.a, selezione per MASE cross-validata e `SeasonalNaive` come fallback esplicito (mai un'eccezione
che interrompe il batch per una serie degenere); `reconcile()` usa `MinTrace(ols)` titolare e
`BottomUp` come confronto, chiamando `reconcile(S_df=...)`; un test verifica la **coerenza
gerarchica** — la somma dei figli riconciliati uguaglia il padre entro tolleranza numerica
(riferimento misurato: 2,8e-14). Suite verde, commit, riga in `state.md`.
notes: se `fitted=True` non regge su tutte le serie, `mint_shrink` resta fuori e la decisione va
scritta in `state.md`, non lasciata al codice.

#### T5.c — Snapshot a lag costante, override del planner, stairstep FVA
owner: sh-backend · depends_on: T5.b
paths: `ibp/forecast/snapshot.py`, `ibp/forecast/fva.py`, `ibp/forecast/override.py`
copre: **AC18**, seconda metà di **AC17**
done_when: ogni emissione di baseline scrive `forecast_snapshot` con `lag` e `process_step`
valorizzati, **e contestualmente il benchmark naïve** (calcolarlo dopo è impossibile a parità di
informazione); la baseline resta **immutabile come emessa**; l'override del planner passa da
`forecast_override` con chi/quando/reason code, ed è distinguibile dal valore generato quando
precompila la P; `fva_stairstep(series, lag)` restituisce `Naïve → Baseline → Rettificata →
Consenso` **a lag costante**, e un test lo ricostruisce dagli snapshot di più cicli. Suite verde,
commit, riga in `state.md`.
notes: un FVA negativo allo step del planner **non è un bug**: oltre metà dei forecast studiati fa
peggio di un random walk, e mostrarlo è ciò che rende la demo credibile. Il test non deve assumere
il segno.

---

### T6.0 — Grana `(manufact_key, region, date_key)` ed eleggibilità per region
stato: pending — **prerequisito bloccante di T6 e T7**
owner: sh-backend · ondata: 2b · depends_on: T3, T4
paths: `ibp/engine/engine.py`, `ibp/engine/cells.py`, `ibp/semantic/measures.py`
copre: precondizione di **AC5**
done_when: `derived_manufacturing_demand` e i nodi a valle portano la **region della domanda** nella
chiave di cella; `_eligible_plant_for(manufact_key, region, date_key)` filtra per `region_scope`
(includendo `GLOBAL`) e **non cachea più per `manufact_key` soltanto** — la cache include region e
validità temporale; un test costruisce una `production_eligibility` con `valid_to` non NULL e due
plant per region diverse e verifica che il plant scelto cambi con la region **e** con la data; AC10
resta verde (`incrementale ≡ full recalc`) sulla nuova grana, e AC11/AC12 con lei.
notes: è il primo pacchetto da fare dopo T5, o in parallelo con esso (path disgiunti). Il difetto
strutturale non è `_eligible_plant_for` (`engine.py:209`): è che l'aggregazione a
`(manufact_key, date_key)` **perde la region**, quindi il dato non è nemmeno disponibile al punto in
cui servirebbe. Non aggiungere una risoluzione di region a posteriori: estendere la grana. Oggi
funziona solo perché il seed lascia `valid_to` NULL — è corretto per caso, e T6/T7 lo renderebbero
sbagliato in silenzio. Ogni arco `_downstream` deve continuare a rispecchiare esattamente le letture
della `_compute_*_cell` corrispondente, o AC10 si rompe per una ragione che nessun test locale mostra.

### T10.1 — Context manager di transazione rientrante
stato: pending — **prerequisito bloccante di T10**
owner: sh-backend · ondata: 2b · depends_on: T4
paths: `ibp/db.py`, `ibp/scenario/branch.py`, `ibp/scenario/edits.py`, `ibp/scenario/promote.py`
copre: **AC30**
done_when: `ibp/db.py` espone un context manager di transazione **rientrante** che, se una
transazione è già aperta sulla connessione, non la possiede — nessun COMMIT né ROLLBACK propri, la
decisione resta al chiamante più esterno; i cinque `BEGIN TRANSACTION` nudi
(`branch.py:81,113,127`, `edits.py:93`, `promote.py:332`) passano da lì; un test chiama
`branch()`/`record_edit()`/`promote()` **dentro** una transazione aperta dal test stesso e verifica
che non sollevino, e che un rollback esterno annulli anche il loro effetto.
notes: DuckDB **non supporta SAVEPOINT** — verificato: non esiste una via d'uscita "annidata vera",
la semantica giusta è la proprietà (chi ha aperto chiude). Parallelizzabile con T6.0: path disgiunti
(engine vs db+scenario write path). **Non** in parallelo con T11.0, che pure sta in `ibp/scenario/`:
i file sono diversi ma `materialize_version` e `promote()` sono accoppiati nel comportamento, e due
agenti che li cambiano insieme producono un fallimento che nessuno dei due riesce ad attribuire.

### T10.0 — Preload bulk del master data nel costruttore del motore
stato: pending — **prerequisito bloccante di T10**
owner: sh-backend · ondata: 3 · depends_on: T6.0
paths: `ibp/engine/engine.py`, `ibp/semantic/dimensions.py`, `ibp/semantic/graph.py`
copre: **AC29**
done_when: `RecalcEngine.__init__` carica il master data con query **bulk** (`item`,
`item_identifier`, `item_link`, `production_eligibility`, `TWSC_PAR_CALWEEK`, `rate_card`) invece
delle cache lazy per-chiave; sul DB seed standard la costruzione emette **meno di 25 query** e
converge in **meno di 5 s**; un test (sh-tester) conta le query iniettando una connessione proxy —
quindi il motore deve continuare ad accettare la connessione dal chiamante, non aprirne una propria;
AC10/AC11/AC12 restano verdi.
notes: misurato oggi 42,7 s / **14.394 query**, di cui `resolve_manufacturing_items` 3.492× = 26,3 s.
Il master data coinvolto sta in memoria senza sforzo (`item_link` 3.516 righe, `item` 3.010,
`TWSC_PAR_CALWEEK` 4.257, `production_eligibility` 582, `rate_card` 4, `routing` 16): non serve una
cache più furba, serve smettere di fare round-trip. La soglia primaria è il **conteggio di query**,
non il tempo: il tempo dipende dalla macchina e un test a tempo diventa flaky il giorno che gira
altrove. Va **dopo** T6.0, perché la grana con region cambia quali indici servono: farlo prima
significa costruirli due volte. In ondata 3 questo pacchetto è l'unico che scrive in
`ibp/semantic/` — T6/T7/T8/T9 lì leggono soltanto.

### T11.0 — `compare()`: `not_comparable` esplicito per le misure non ricombinabili
stato: pending — **prerequisito di T11, e di `UI-SPEC.md`**
owner: sh-backend · ondata: 3 · depends_on: T10.1
paths: `ibp/scenario/compare.py`, `ibp/scenario/models.py`, `ibp/scenario/overlay.py`,
`ibp/scenario/errors.py`
copre: **AC28**
done_when: `CompareRow` guadagna uno stato esplicito (`comparable` | `not_comparable`) con motivo
leggibile; `min`/`max` sono **confrontate** (sono ricombinabili alla grana di overlay);
`avg`/`ratio` compaiono come `not_comparable` con motivo, e **non spariscono dal risultato**; un
test copre le 26 misure reali del catalogo (19 `sum`, 1 `max`, 3 `avg`, 3 `ratio`) e verifica che
ognuna produca una riga; il contratto è scritto in `UI-SPEC.md` prima che T11 parta.
notes: oggi `materialize_version` filtra a `agg_method='sum'`, quindi `compare()` non vede affatto
le altre e la UI di T11 mostrerebbe **"nessuna differenza" per l'utilizzo di capacità** — un falso
negativo su una delle misure che il planner guarda per prime. La distinzione non è stilistica:
`min`/`max` si ricombinano dai valori, `avg`/`ratio` richiedono i denominatori, che `overlay` non
traccia. Non re-introdurre la somma di ratio: `NonAdditiveMeasureError` su `resolve_cell()` resta
com'è.

### T11.1 — Tabella di provenienza della promozione (schema)
stato: pending — **prerequisito di T11**
owner: sh-data · ondata: 3 · depends_on: T4
paths: `db/schema.sql`, `db/build_db.py`
copre: prima metà di **AC31**
done_when: esiste una tabella laterale di provenienza con
`(version_key, slice, origin ∈ {copied, overlay_override, prorated}, scenario_id, edit_id?)`,
indicizzata per lettura per versione e per slice; `_validate()` non la popola dal seed ma verifica
che lo schema regga; `TSOP_DEMAND` e `TSOP_OPS` **non cambiano di una colonna**.
notes: seconda deroga consapevole sulla proprietà di T1 (come l'extra `[forecast]` e il digest):
uno schema nuovo è di `sh-data` per competenza, e la scrittura è di `sh-backend` in T11.2 — due
owner, due task, non un task con due proprietari. La provenienza **non** può essere una colonna su
`TSOP_DEMAND`/`TSOP_OPS`: sono il mirror dEPM e devono restare isomorfe, o l'export di T9 verso
Power BI smette di combaciare con i modelli semantici esistenti.

### T11.2 — `promote()` scrive la provenienza
stato: pending — **prerequisito di T11**
owner: sh-backend · ondata: 3 · depends_on: T11.1, T10.1
paths: `ibp/scenario/promote.py`
copre: seconda metà di **AC31**
done_when: `promote()` persiste, per ogni riga scritta nella nuova istanza `DVERSIONS`, l'origine
(`copied` | `overlay_override` | `prorated`), lo scenario di provenienza e l'`edit_id` quando
esiste; un test promuove uno scenario con un override e una fetta proratata e verifica che le tre
origini siano distinguibili a posteriori; le righe copiate restano **byte per byte** identiche
(nessuna regressione sul difetto di deriva già chiuso).
notes: l'informazione **esiste già** — `overlay_touched_slices()` calcola esattamente l'insieme
toccato — e viene buttata via dopo la scrittura. Non ricalcolarla in un secondo passaggio: catturarla
dove è già nota. Serve a T11 per colorare la cella modificata, e senza di essa un planner non può
verificare cosa sia stato sovrascritto e cosa derivato.

---

### T6 — Rete produttiva: N:N, eligibility, routing multi-step, domanda dipendente, back-allocation
stato: pending · owner: sh-backend · ondata: 3 · depends_on: T2, **T6.0**
paths: `ibp/network/**`
copre: AC4, AC5, AC6, AC7, AC9, AC27
done_when: i quattro pacchetti T6.a-T6.d sono chiusi e i relativi AC sono verdi.
notes: `db/schema.sql` è la verità sul modello dati: `item_link` (N:N time-phased), **non**
`product_mapping`. Il test AC2 anti-literal deve includere `ibp/network/` nella root list
(`tests/test_semantic_ac2_master_data.py:29` oggi non lo fa) — qui finiscono quota e offset, ed è
esattamente il posto dove un `2` o un `100` hardcoded farebbe danno.

#### T6.a — Risoluzione N:N e override tracciato
owner: sh-backend · depends_on: T6.0
paths: `ibp/network/__init__.py`, `ibp/network/resolve.py`, `ibp/network/errors.py`
copre: **AC4**
done_when: un planning model si distribuisce su più manufacturing key con quote time-phased, e più
planning model aggregano sulla stessa manufacturing key (entrambe le direzioni, verificate sui casi
M:N che il seed garantisce); l'override manuale (`quota_source='manual_override'` con
`override_by`/`override_at`) è **distinguibile** dal valore di regola e da quello osservato in ogni
punto dell'API di modulo, non solo nel DB; le quote di ogni `(from_item, link_type, period)`
continuano a sommare a 100. Suite verde, commit, riga in `state.md`.
notes: riusare `resolve_manufacturing_items()` di T2, non riscriverne una seconda versione: la
gestione del `period` più recente per `(from_item, link_type)` — non per singolo `to_item` — è
esattamente ciò che impedisce a un target rimosso dal mix di sopravvivere (difetto misurato a T2:
quote al 145%).

#### T6.b — Eleggibilità per region e rifiuto del plant non eleggibile
owner: sh-backend · depends_on: T6.a
paths: `ibp/network/eligibility.py`
copre: **AC5**
done_when: lo stesso manufacturing key risulta producibile in più plant secondo `region_scope`
(inclusa la semantica di `GLOBAL`) e per periodo di validità; un'allocazione verso un plant non
eleggibile è **rifiutata** con un errore tipizzato, non filtrata in silenzio; un test copre i tre
casi: plant eleggibile, plant eleggibile ma per un'altra region, plant con eleggibilità scaduta.
Suite verde, commit, riga in `state.md`.
notes: dipende da T6.0 per avere la region nella chiave. Il rifiuto deve essere un'eccezione, non un
risultato vuoto: un'allocazione che sparisce è un numero plausibile mancante, che è il modo in cui
questo sistema perde credibilità.

#### T6.c — Routing multi-step obbligatorio e domanda dipendente
owner: sh-backend · depends_on: T6.b
paths: `ibp/network/routing.py`, `ibp/network/dependent_demand.py`
copre: **AC6**, **AC9**
done_when: il routing `mandatory=true` (ILK/ILT Ganderkesee → Cerritos) genera domanda dipendente
sul semilavorato **anticipata di 2 mesi**, con l'offset letto da `routing.lead_offset_months` e
nessun `2` nel codice; la capacità è consumata in **entrambi** i plant; il percorso Excel→DB è
sostituito — la domanda dipendente si genera dal routing, e un test lo dimostra partendo dal solo
master data, senza alcun file in input. Suite verde, commit, riga in `state.md`.
notes: l'offset è **fisso**, non variabile per cluster (F10, question chiusa): un solo parametro
configurabile, nessun ramo condizionale. `dependent_demand` è un `link_type` di `item_link` e resta
fuori da `resolve_manufacturing_items()` per costruzione — è un salto successivo della rete, non
parte della risoluzione vendita→produzione. È il punto di M1 con il ritorno più immediato: sostituisce
un file Excel che scrive sul database, dove un errore produce un numero plausibile e non un errore.

#### T6.d — Routing elettivo e back-allocation OPS→Sales
owner: sh-backend · depends_on: T6.c
paths: `ibp/network/elective.py`, `ibp/network/back_allocation.py`
copre: **AC7**, **AC27**
done_when: il routing `mandatory=false` (NAM) produce split diversi al variare del mix di
configurazione, e il carico di Northfield cambia di conseguenza (test con due mix e confronto dei
carichi); `back_allocate(cycle)` risale da OPS a Sales in due stadi — (a) manufacturing key →
planning model sui **contributi effettivi del passaggio forward**, (b) planning model →
division/region pro-rata sulla requested production con correzione a **resto massimo**; un test
verifica che sulle 7 manufacturing key aggreganti **nessun planning model con contributo forward non
nullo riceva zero**, e che la somma ripartita uguagli esattamente il totale confermato. Suite verde,
commit, riga in `state.md`.
notes: la regola ANA-050 §3.3 risolve il planning model via l'attributo `SalesModel`, che è
**monovalore**: sulle chiavi aggreganti attribuisce tutto a un solo modello e gli altri prendono
zero, con correzione manuale in Excel ogni ciclo. Il nostro modello non ha quel limite perché
`item_link` ha tutte le quote. **Non** usare `SalesModel` e **non** ricalcolare `quota_pct` per
tornare indietro: si usano i contributi che il forward ha effettivamente prodotto, altrimenti si
riproduce il difetto con una formula diversa. Da citare esplicitamente nella demo di T12: è uno dei
cinque lavori manuali che M1 elimina.

### T7 — Capacità e allocatore
stato: pending · owner: sh-backend · ondata: 3 · depends_on: T2, T6
paths: `ibp/capacity/**`
copre: AC3, AC8
done_when: `bill_of_resource` e lo **slot-equivalence factor** per manufacturing key sono applicati
(il ×2 di Westvale è il caso particolare `factor = 2`, il literal sparisce dentro il dato); RCCP con
resource profile e lead-time offset; `AllocationStrategy` è un'**interfaccia** con default greedy a
priorità che **propone** lo split multi-plant — dall'orderbook dentro l'orizzonte, dal mix osservato
oltre; il planner può correggere e l'override è tracciato e distinguibile dal valore calcolato;
`Average Assembly Hours` ha un consumatore reale come seconda valuta di capacità (`plant_hour_pool`).
notes: un solver CP-SAT stile Quintiq si innesta sostituendo l'implementazione ed è **fuori scope
M1** — l'interfaccia esiste perché quel giorno non serva riscrivere il motore. AC3 dipende dalla
open question 1: se l'attributo non è popolato in produzione, il consumatore va costruito comunque
ma la cosa va scritta, non taciuta.

### T8 — Processo: P/R/A/C, i 5 review, portfolio, reconciliation, `3600`
stato: pending · owner: sh-backend · ondata: 3 · depends_on: T2
paths: `ibp/process/**`
copre: AC20, AC21, AC22, AC23
done_when: `open_cycle(year, month)` istanzia le fasi con i day range e gli stati `STAT_01/02/03`
letti da `db/seed/data/process_phases.json`; una scrittura su fase `STAT_03` è **rifiutata**; il
gate `PortfolioApproved` è precondizione per aprire P; ogni `project` approvato genera
`project_resource_demand` che consuma capacità e `portfolio_commitment` che entra nella baseline di
demand; la Integrated Reconciliation genera l'agenda **dai gap sopra soglia**, in unità e valore, e
produce `decision`/`escalation`; `confirm_back_to_sales(cycle)` esiste come funzione nominata e
distinta, documentata come *anchoring*.
notes: i due review mancanti sono **oggetti con stati e transizioni**, non tabelle di appoggio per
documenti. P/R/A/C resta invariato: i nuovi review si innestano prima e in mezzo, non lo riscrivono.
`confirm_back_to_sales` non va confuso con la Reconciliation — il sistema non toglie il carry-forward
`3600`, chiarisce che è anchoring. Open question 4 (da quale istanza copia il job `3000`) va chiusa
prima di iniziare: il parametro esplicito `copy_from: version_ref` è la raccomandazione.

### T9 — Adapter Infor/SAP, viste Power BI, sostituzione del path Excel→DB
stato: pending · owner: sh-data · ondata: 3 · depends_on: T2
paths: `ibp/adapters/**`, `db/views/**`
copre: AC24 (+ supporto ad AC9)
done_when: `infor_import` carica dimensioni ed estratti nella forma degli export dEPM (colonne
`Path`, `Element Name`, `Name`, `OrderPosition`, flag `Is …`, `LangEN`/`LangDE`) ricostruendo la
gerarchia padre/figlio; `sap_master` definisce e valida il contratto di master data in ingresso;
`powerbi_export` genera in `db/views/` le viste in forma star con i **nomi dEPM preservati**;
`infor_writeback` produce un **file** di import per Application Studio da una versione promossa;
nessun adapter apre connessioni verso SAP o dEPM, e un test lo verifica staticamente.
notes: questo task materializza il confine. Il write-back è un artefatto su disco che una persona
carica, non una connessione. Le viste devono conservare i nomi dEPM così che Power BI non vada
riscritto — ed è il motivo per cui la provenienza di T11.1 sta in una tabella laterale e non in una
colonna sui fatti.

### T10 — API HTTP
stato: pending · owner: sh-backend · ondata: 4
depends_on: T5, T6, T7, T8, T9, **T10.0**, **T10.1**
paths: `ibp/api/**`
copre: supporto ad AC11, AC22, AC29, AC30
done_when: `uvicorn ibp.api.app:app` espone e documenta in OpenAPI: ciclo e fasi (lettura, apertura,
transizione, gate), griglia di pianificazione (lettura per versione/scenario, scrittura cella con
ricalcolo), scenari (crea, modifica, confronta, promuovi), rete produttiva e routing, portfolio,
reconciliation, eccezioni; una scrittura su fase chiusa o su versione ufficiale restituisce **409**
con messaggio esplicito; un batch di edit malformato non lascia il motore in stato inconsistente.
notes: nessuna logica di dominio nei router: solo orchestrazione. Qui si congelano i nomi dei campi —
T11 ci si appoggia. DuckDB è single-writer con lock di processo: il server e i job condividono
**una** connessione (thread, non processi). I due prerequisiti non sono opzionali: senza T10.0 ogni
costruzione del motore costa 42 s e 14.394 query dietro una richiesta HTTP; senza T10.1 la prima
transazione applicativa che avvolge `promote()` solleva.

### T11 — Workbench del planner
stato: pending · owner: sh-frontend · ondata: 5
depends_on: T10, **T11.0**, **T11.2**, `UI-SPEC.md`
paths: `web/**`
copre: AC11 (manuale), supporto ad AC25
done_when: `http://localhost:8000/` mostra: timeline del ciclo con fasi, stati e gate; griglia
editabile che dopo una modifica mostra i valori a valle ricalcolati **senza reload**; confronto a due
riferimenti (`Version 1` / `Version 2`) che rende visibili sia i delta sia le misure
`not_comparable` **con il motivo**; vista di rete con il routing multi-step; lista eccezioni;
sessione di reconciliation con l'agenda dai gap. La cella promossa da un override è distinguibile da
quella copiata e da quella proratata (provenienza di T11.2). Nessun build step, nessuna risorsa da
CDN, tutto servito da FastAPI.
notes: `/gsd-ui-phase` produce `UI-SPEC.md` **prima** che si scriva markup, e quel documento deve già
contenere i due contratti decisi il 2026-09-12 (`not_comparable` con motivo; provenienza a tre
origini). È un workbench di verifica dell'architettura, non un prodotto: densità di informazione
prima dell'estetica. Il lettore sceglie entrambi i lati di ogni varianza (semantica Power BI), quindi
la notazione IBCS non è decidibile a design time: si legge `is_frozen` dall'API, non si stilizza
staticamente.

### T12 — CLI e demo end-to-end
stato: pending · owner: sh-backend · ondata: 5 · depends_on: T10
paths: `ibp/cli.py`, `scripts/**`
copre: AC9, AC25 e la verifica end-to-end di tutto il resto
done_when: `python -m ibp.cli demo` esegue su DB appena ricostruito: apertura ciclo → Portfolio
Review con NPI e phase-out risorsati → baseline statistica → P → override planner → R → mapping N:N a
manufacturing key → **allocazione multi-plant proposta su orderbook** → **routing multi-step con
domanda dipendente sul semilavorato** → **back-allocation OPS→Sales** → allocazione vincolata A →
scenario what-if, confronto, promozione → Integrated Reconciliation con agenda dai gap → decisioni →
gate → `confirm_back_to_sales` → export; stampa gap in unità e valore, eccezioni, decisioni e
**stairstep FVA**; exit code 0. Esistono i comandi granulari (`build`, `open-cycle`, `recalc`,
`forecast`, `scenario`, `export`).
notes: gira offline e senza server già avviato. È il primo posto dove si vede se un confine è
sbagliato. Lo scenario che la demo promuove è uno dei due seminati: il digest di `base_snapshot_id`
(chiuso in T1 il 2026-09-12) è ciò che rende quella promozione una verifica reale di AC16 e non un
passaggio decorativo. Citare la back-allocation esplicitamente nell'output: è uno dei cinque lavori
manuali che M1 elimina, e nella demo deve vedersi.

### T13 — Documentazione e integrazione diagrammi
stato: pending · owner: sh-docs · ondata: 6 · depends_on: T11, T12
paths: `docs/01-architecture.md` … `docs/06-adr.md`, `docs/diagrams/**`
copre: AC26
done_when: `docs/01`-`06` esistono e sono coerenti con il codice finale; i diagrammi archify
(architettura a layer, rete produttiva multi-step, ciclo P/R/A/C con i 5 review, DAG di ricalcolo,
lifecycle scenari) sono navigabili e integrati; le estensioni **AC27-AC31** sono riportate in
`docs/01-plan-m1.md` così che il piano canonico e questo restino la stessa verità.
notes: **i documenti sono il deliverable primario** (F6); il codice esiste per renderli verificabili.
Lezioni archify da non ripetere: `meta.locale` supporta solo `en`/`zh-CN` (contenuti in italiano,
viewer in inglese); dichiarare sempre `fromSide`/`toSide` sui layout a fasce; mai due archi opposti
fra gli stessi due nodi (modellare l'intermedio come nodo); `dataflow` richiede `label` su ogni flow
e righe 0..4.

---

## Ondate e parallelismo

| Ondata | Task | Parallelismo |
|---|---|---|
| 0 | T1 | — (**done**) |
| 1 | T2 | — (**done**) |
| 2 | T3, T4 (**done**), **T5.a→T5.b→T5.c** | T5 è sequenziale al proprio interno |
| 2b | **T6.0** ∥ **T10.1** | veri paralleli: `ibp/engine/` vs `ibp/db.py`+`ibp/scenario/` write path. Anche paralleli a T5 (`ibp/forecast/`) |
| 3 | **T6.a→b→c→d**, T7, T8, T9, **T10.0**, **T11.0**, **T11.1→T11.2** | T7 dopo T6; T10.0 dopo T6.0; T11.0 dopo T10.1; T11.2 dopo T11.1 e T10.1. T6/T7/T8/T9 hanno path disgiunti (`network`/`capacity`/`process`/`adapters`+`db/views`) |
| 4 | T10 | dopo T5, T6, T7, T8, T9, T10.0, T10.1 |
| 5 | T11 ∥ T12 | `web/` vs `ibp/cli.py`: disgiunti. T11 anche dopo T11.0/T11.2 e `UI-SPEC.md` |
| 6 | T13 | — |

Fuori backlog, da non dimenticare: i **tre diagrammi archify mancanti** (ciclo P/R/A/C con i 5
review, DAG di ricalcolo con dirty propagation, lifecycle scenari) e **`UI-SPEC.md`** via
`/gsd-ui-phase` prima di T11.
