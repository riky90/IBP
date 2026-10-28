# Vincoli (SPEC)

Fonte primaria: `docs/02-spec-m1-corrente.md` — tipo SPEC, `precedence: 1`, rigenerato 2026-09-12 da
`sh-architect`. Il documento dichiara di **supersedere** `docs/01-plan-m1.md` per dettaglio di task,
acceptance criteria e backlog (non per contesto di business/architettura M2-M3, che resta in
`requirements.md`). Dove ADR-001 (precedence 0, LOCKED) parla, **ADR-001 vince su questo documento**
— i punti toccati sono annotati inline e in `decisions.md`.

## D1 — Semantic layer: mirror dEPM + graph overlay

type: schema | source: docs/02-spec-m1-corrente.md

Star schema dEPM rispecchiato come nucleo canonico (`TSOP_DEMAND`, `TSOP_OPS`,
`TWSC_PAR_CALWEEK`, `DPLANT`, `DSALES_DIVISION`, `DVERSIONS`, `DMEASURE_DEMAND/OPS`, `DIM_DATE`),
esteso con **una** tabella di archi tipizzati `edge(from_type, from_key, rel_type, to_type, to_key,
valid_from, valid_to, attrs_json)`. `from_type`/`to_type` testo libero: M2/M3 aggiungono nodi senza
migrazione.

**Correzione rispetto al piano vecchio**: `DSALES_PRODUCT`/`DMANUFACT_KEY` non esistono come tabelle;
T1 le ha collassate in `item(item_key, role, region, is_sellable, manufacturing_category, …)` +
`item_identifier` (identità datate: `element_name`, `caption`, `sap_material`, `legacy`).
`db/schema.sql` è la verità.

**Contratto vincolante per i task a valle**: ogni numerico dal semantic layer è `float`, mai
`Decimal` (chi espone una colonna `DECIMAL`, es. `rate_card`, casta nel row constructor);
`neighbors()` solleva `GraphSnapshotLimitationError` per `as_of` strettamente passato sui `rel_type`
derivati da `item_link` — per una risposta datata si usa `resolve_manufacturing_items()`.

## D2 — Rete produttiva: relazioni, non attributi (`item_link`)

type: schema | source: docs/02-spec-m1-corrente.md

Quattro tabelle sostituiscono due attributi (`Linked Manufact Key`, `Targeted Plant`):

```
item_link(from_item, to_item, link_type, period, quota_pct, quota_source,
          quota_window_months, offset_months, override_by, override_at, valid_from, valid_to)
production_eligibility(manufacturing_key, plant, region_scope, priority, valid_from, valid_to)
routing(manufacturing_key, variant_key?, step_no, plant, operation_type,
        lead_offset_months, mandatory)
bill_of_resource(manufacturing_key|variant_key, resource_id, qty_per_unit,
                 offset_periods, spread_profile_json) + resource + resource_capacity
```

`quota_source ∈ {rule, observed_history, manual_override}`. `region_scope ∈
{APAC,CIS,EMEA,LATAM,NAM,GLOBAL}`. La quota degli split **oltre l'orderbook** è il mix osservato a
consuntivo (`quota_source='observed_history'`), non una percentuale a mano. Invariante verificata da
`build_db.py`: le quote di ogni `(from_item, link_type, period)` sommano a 100.

**Grana del nodo del DAG: `(manufact_key, region, date_key)`, non `(manufact_key, date_key)`** —
modifica di design resa obbligatoria dal codice reale: `derived_manufacturing_demand` perde la
region se aggregata senza di essa, e `_eligible_plant_for` (`ibp/engine/engine.py:209`) non ha il
dato per filtrare `region_scope`. Corretto oggi solo perché il seed lascia
`production_eligibility.valid_to` NULL. Va estesa la grana (pacchetto **T6.0**, prerequisito
bloccante di T6/T7), non aggiunta una risoluzione a posteriori.

**Domanda dipendente (AC6/AC9)**: il semilavorato è un `item` con domanda propria, offset **fisso a
2 mesi** letto da `routing.lead_offset_months` come master data — un solo parametro, nessun ramo
condizionale.

**Back-allocation job 3000 OPS→Sales (AC27)**: cammino inverso in due stadi — (a) manufacturing key
→ planning model sui **contributi effettivi del passaggio forward** (non `SalesModel`, monovalore e
difettoso su 7 manufacturing key aggreganti; non una `quota_pct` ricalcolata); (b) planning model →
division/region pro-rata sulla requested production con correzione a **resto massimo** (ANA-050
§3.3). *Confermato come comportamento di produzione corrente, non proposta, da ADR-001 D-005 —
vedi `decisions.md` (INFO, nessuna contraddizione).*

**Nota ADR-001 D-006** (routing elettivo su insieme di attributi, non singolo — vedi
`decisions.md`): la colonna `routing.variant_key` in questo schema è disegnata come chiave singola
opzionale (`variant_key?`). D-006 richiede che il modello sia estendibile a un **insieme** di
attributi di configurazione senza modifiche di schema. Implicazione di design per **T6.d** da
valutare in pianificazione: `variant_key` come chiave opaca può ancora bastare se incapsula
l'insieme (es. hash/composizione), ma il contratto "estendibile senza modifiche di schema" va
verificato esplicitamente contro il design attuale — vedi INFO in `INGEST-CONFLICTS.md`.

## D3 — Scenari: event log → overlay → layer stack

type: schema + protocol | source: docs/02-spec-m1-corrente.md

```
edits(append-only) → overlay(scenario_id, …, value, is_deleted) → COALESCE(l3, l2, l1, base)
```

`edits` (verità append-only: undo/redo, audit FVA, ricostruzione deterministica) + `overlay` (cache,
tombstone esplicito `is_deleted`, mai `NULL` come sentinella). `promote()` materializza una **nuova**
istanza `DVERSIONS`; nessuna istanza esistente viene mai mutata.

Contratti a terra (T4, done):
1. Determinismo lettura/scrittura: `ORDER BY` su PK piena + somma in Python (non `SUM(...) GROUP BY`
   parallelo); `promote()` distingue "fetta mai toccata" (copiata byte per byte) da "toccata, stesso
   valore".
2. Isolamento fra scenari su basi diverse (AC15): `MismatchedBaseVersionError`,
   `CellVersionMismatchError`, filtro `version_key` come difesa in profondità.
3. `base_snapshot_id` è impronta di contenuto, non etichetta: `_stamp_base_snapshots` la sostituisce
   col digest vero via `ibp.scenario.overlay.base_content_digest`; `_validate()` fallisce il build su
   sentinella residuo o digest non combaciante.

Contratti aggiunti il 2026-09-12 (AC28, AC31):
- **Misure non additive `not_comparable`, non invisibili** (AC28): `min`/`max` confrontabili (si
  ricombinano alla grana overlay), `avg`/`ratio` `not_comparable` con motivo esplicito — mai
  sparire dal risultato di `compare()`. Catalogo reale: 19 `sum`, 1 `max` (`SLOTS_AVAILABLE`), 3
  `avg` (`AVG_MAX_CAPACITY`, `WEEKS_PRODUCTION`, `FROZEN_ZONE`), 3 `ratio` (`ORDER_COVERAGE`,
  `CAPACITY_UTIL`, `PLANT_RELIABILITY`). `NonAdditiveMeasureError` su `resolve_cell()` resta.
- **Provenienza della riga promossa** (AC31): tabella laterale `(version_key, slice, origin ∈
  {copied, overlay_override, prorated}, scenario_id, edit_id?)` — non una colonna su
  `TSOP_DEMAND`/`TSOP_OPS`, che devono restare isomorfe al mirror dEPM.
- **Transazioni rientranti** (AC30): `ibp/db.py` deve esporre un context manager rientrante — DuckDB
  non supporta SAVEPOINT; chi apre la transazione la chiude, i cinque `BEGIN TRANSACTION` nudi
  (`branch.py:81,113,127`, `edits.py:93`, `promote.py:332`) passano da lì.

**⚠ Tensione aperta con ADR-001 R-001** (vedi `decisions.md`): R-001 richiede un modello a **tronco e
rami** dove piani salvati e scenari salvati sono lo stesso tipo di oggetto (rami). Questo design D3
tratta uno scenario come ramo di una versione base e un piano salvato come istanza `DVERSIONS`
promossa — due nature diverse. Dichiarato "estensione, non contraddizione" dalla fonte, ma con
conseguenze non decise (rework di T4? layer sopra?). **WARNING in `INGEST-CONFLICTS.md`, tocca T4
(già consegnato), T11, T12.**

## D4 — Motore: DAG dichiarato, height, early cutoff, preload bulk

type: nfr + protocol | source: docs/02-spec-m1-corrente.md

DAG dichiarato in `ibp/semantic/measures.py` (`MEASURE_DAG`, non calcola), eseguito in
`ibp/engine/`. Due radici (`requested_production`, `confirmed_production`), quattro nodi derivati
(`derived_manufacturing_demand → slots_requested → gap_req_conf → value_gap`). Ricalcolo in
min-heap per height; early cutoff sull'hash; `CutoffStats` con quarto termine `absent` (sparsità
master data ≠ risparmio di ricalcolo).

**Proprietà strutturale da preservare** (AC10): ogni cella ha una sola `_compute_*_cell()`, chiamata
identica da `full_recalculate()` e `recalculate()`; ogni arco `_downstream` rispecchia esattamente le
letture della `_compute_*_cell` corrispondente.

**Costo di costruzione (AC29)**: misurato 42,7s / 14.394 query (95% dentro DuckDB); soglia target
**<25 query, <5s**. Causa: query N+1 per-chiave (`resolve_manufacturing_items` 3.492× = 26,3s).
Rimedio: preload bulk nel costruttore (pacchetto **T10.0**, dopo T6.0 perché la grana con region
cambia gli indici necessari).

## D5 — Forecast statistico e FVA

type: nfr + protocol | source: docs/02-spec-m1-corrente.md, README.md

**T5 è sbloccato** — la diagnosi precedente ("serve MSVC") era sbagliata: `statsforecast==1.7.8` non
esiste su PyPI (la serie 1.7 finisce a 1.7.6, poi 2.0.3); pip falliva sulla sdist. La serie 2.x
(`statsforecast==2.1.1`, `hierarchicalforecast==1.5.1`, `utilsforecast==0.2.16`) pubblica wheel
`cp313-win_amd64`, **nessun MSVC richiesto**. Extra `[forecast]` separato solo perché tira ~11
pacchetti non usati dal resto di M1.

**Due vincoli operativi non negoziabili:**
1. **Ordine di import (segfault, non eccezione)**: `hierarchicalforecast._lib` e
   `coreforecast`/`utilsforecast` hanno runtime OpenMP distinti; se `utilsforecast` carica per primo,
   il successivo import di `hierarchicalforecast.utils` termina il processo con **SIGSEGV senza
   traceback**. Nessuna variabile d'ambiente lo evita. `ibp/forecast/__init__.py` deve aprire con
   `from hierarchicalforecast._lib import reconciliation as _hf_lib` come **prima riga**. Test di
   regressione in **subprocess**, verifica `returncode == 0`.
2. **API 1.x**: `HierarchicalReconciliation.reconcile()` prende `S_df=`, non `S=`.

Gerarchia di riconciliazione: **commerciale** (`division ▶ product line ▶ category ▶ model`), non
manifatturiera — `item_link` è N:N e romperebbe la consistenza richiesta da MinTrace in silenzio.

`forecast_snapshot(series_id, target_period, created_period, lag, process_step, value)` +
`forecast_override` + `actual_restatement`: FVA ha senso solo a lag costante, salvare solo l'ultimo
forecast lo distrugge per sempre. Stairstep `Naïve → Baseline → Rettificata → Consenso`; FVA
negativo allo step planner è atteso, non un difetto.

Vincolo di scala noto da T1: volume fatti cappato a 4 cicli chiusi + corrente + `SOP_BP_2027` — meno
storia per la baseline; verificare copertura effettiva prima di scegliere il pool (open question 2).

## D6 — Processo, i due review mancanti, confine

type: protocol + nfr | source: docs/02-spec-m1-corrente.md

Portfolio Review (gg 1-5, prima di P; gate `PortfolioApproved`), Integrated Reconciliation (gg
15-16, fra A e C; agenda dai gap sopra soglia, unità e valore; `decision`/`escalation`; `rate_card`
finanziarizza). Carry-forward `3600` resta, nominato `confirm_back_to_sales(cycle)`, distinto dalla
Reconciliation.

**Confine (AC24)**: SAP S/4 consumato read-only, mai scritto; Infor dEPM riceve il piano promosso
come **file**; Power BI non toccato (viste in forma star); ERP/MRP fuori confine.

## D7 — Layout, ambiente, tooling (NFR)

type: nfr | source: docs/02-spec-m1-corrente.md, README.md

```
pyproject.toml   db/{schema.sql,build_db.py,seed/**,views/}   data/ibp.duckdb (gitignored)
ibp/{config.py,db.py,domain/,semantic/,engine/,scenario/,forecast/,network/,capacity/,
     process/,adapters/,api/,cli.py}   web/   docs/   tests/ (proprietà esclusiva sh-tester)
```

**Ambiente Windows (AC25)** — dettaglio completo anche in `context.md` (source README.md):
- Extension DuckDB: autoload/autoinstall disattivati (`autoinstall_known_extensions=false`,
  `autoload_known_extensions=false`) — altrimenti la demo offline si rompe al primo uso.
- `temp_directory` esplicito (`data/tmp/`); esclusione Windows Defender su `data/` consigliata.
- DuckDB **single-writer con lock di processo**: server UI e job condividono **una** connessione
  (thread, non processi); niente `fork()`.
- RNG deterministico via `hashlib.sha256`, non `hash()` builtin (salato per processo).
- Versioni pinnate in `pyproject.toml`, inclusa `polars` (regressioni di memoria note su Windows).

**Deroga registrata**: `pyproject.toml` è proprietà esclusiva di T1, riaperto una volta (2026-09-12)
per il pin `statsforecast` + extra `[forecast]`; nessun task successivo lo tocca.

## Acceptance criteria — elenco canonico (stato SPEC, 2026-09-12)

Numerazione e testo di AC1-AC26 sono quelli approvati in `docs/01-plan-m1.md`, **non rinumerati né
riscritti tranne AC6** (tolto il condizionale sull'offset: F10 chiusa, offset fisso 2 mesi). Stato
`[x]` = fatto/verificato, `[ ]` = pending.

**Modello dati e regole**
- [x] AC1 — `python db/build_db.py` ricostruisce il DB da zero, idempotente, cardinalità isomorfe.
- [x] AC2 — `Max Slots`/granularità/soglia `<500` sono master data; test anti-literal.
- [ ] AC3 — `Average Assembly Hours` ha un consumatore reale (T7). *(vedi decisions.md D-007)*

**Rete produttiva**
- [ ] AC4 — PM↔MK many-to-many time-phased, override tracciato.
- [ ] AC5 — MK producibile in più plant per `region_scope`; rifiuto plant non eleggibile.
- [ ] AC6 — Routing obbligatorio genera domanda dipendente a offset **fisso 2 mesi**
  (`routing.lead_offset_months`), consumo capacità in entrambi i plant.
- [ ] AC7 — Routing elettivo (NAM) produce split diversi al variare del mix. *(vedi decisions.md
  D-006)*
- [ ] AC8 — Allocatore propone split multi-plant (orderbook / mix osservato); override tracciato.
- [ ] AC9 — Percorso Excel→DB sostituito dalla domanda dipendente generata dal routing.

**Motore**
- [x] AC10 — `recalculate(changed)` ≡ ricalcolo completo (test cardine).
- [x] AC11 — Early cutoff osservabile e misurato.
- [x] AC12 — Min/max/ratio ricalcolati sul gruppo, non delta-aggiornati.

**Scenari**
- [x] AC13 — Branch → modifica → confronto → promozione crea nuova istanza `DVERSIONS`.
- [x] AC14 — Tombstone non ricompare dal base.
- [x] AC15 — Cache key include lo stack.
- [x] AC16 — Promozione con base mossa → conflitto, non sovrascrittura.

**Forecast**
- [ ] AC17 — Baseline precompila P; override distinguibile.
- [ ] AC18 — FVA stairstep a lag costante da `forecast_snapshot`.
- [ ] AC19 — Forecast riconciliato coerente lungo la gerarchia.

**Processo**
- [ ] AC20 — Ciclo P→R→A→C, scrittura su `STAT_03` rifiutata.
- [ ] AC21 — Portfolio Review: output = input Demand Review + consumo capacità; gate precondizione.
- [ ] AC22 — Integrated Reconciliation genera agenda dai gap sopra soglia.
- [ ] AC23 — `confirm_back_to_sales(cycle)` nominata e distinta.

**Confine e ambiente**
- [ ] AC24 — Nessuna scrittura SAP/dEPM; write-back = file.
- [ ] AC25 — Tutto offline su Windows.
- [ ] AC26 — Diagrammi archify navigabili e coerenti col codice finale.

### Estensioni decise il 2026-09-12 (AC27-AC31, non sostitutive)

- [ ] **AC27** — Back-allocation job 3000: nessun PM con contributo forward non nullo riceve zero;
  somma ripartita = totale confermato esattamente.
- [ ] **AC28** — `compare()` restituisce una riga per ogni misura (26 reali: 19 sum, 1 max, 3 avg, 3
  ratio); `avg`/`ratio` come `not_comparable` con motivo, mai invisibili.
- [ ] **AC29** — `RecalcEngine.__init__` < 25 query (oggi 14.394), < 5s (oggi 42,7s) sul DB seed.
- [ ] **AC30** — Transazioni rientranti: nessun `TransactionException` annidato, nessun COMMIT/
  ROLLBACK proprio se già dentro una transazione del chiamante.
- [ ] **AC31** — Ogni riga promossa risalibile a origine (`copied`/`overlay_override`/`prorated`),
  scenario e `edit_id`; `TSOP_DEMAND`/`TSOP_OPS` restano isomorfe (tabella laterale).

## Backlog — 13 task canonici + 6 pacchetti preparatori

Stato di consegna effettivo (done/pending, difetti chiusi) è in `context.md` (source:
docs/03-consegna-t1-t4.md) — qui solo struttura/dipendenze/scope, autorevole da questo SPEC.

**Vincoli invarianti di backlog**: `pyproject.toml` proprietà esclusiva T1 (deroga registrata);
`tests/**` proprietà esclusiva `sh-tester`; due task nella stessa ondata non toccano mai lo stesso
file; tutto offline su Windows; nessuna scrittura verso SAP/dEPM. Criterio di chiusura pacchetto:
suite verde + commit + riga di stato in `state.md`, dimensionato 120-150 turni.

| Task | Owner | Ondata | Depends on | Copre | Path |
|---|---|---|---|---|---|
| T1 schema+seed | sh-data | 0 | — | AC1,AC2,AC16(seed) | pyproject.toml, db/** |
| T2 dominio+semantic+DAG+grafo | sh-backend | 1 | T1 | — | ibp/{config,db,domain,semantic}/** |
| T3 motore concurrent | sh-backend | 2 | T2 | AC10,AC11,AC12 | ibp/engine/** |
| T4 scenari | sh-backend | 2 | T2 | AC13-16 | ibp/scenario/** |
| T5 forecast (T5.a→b→c) | sh-backend | 2 | T2 | AC17-19 | ibp/forecast/** |
| **T6.0** grana region (prerequisito bloccante T6/T7) | sh-backend | 2b | T3,T4 | precond. AC5 | ibp/engine/engine.py, cells.py, semantic/measures.py |
| **T10.1** transazioni rientranti (prerequisito bloccante T10) | sh-backend | 2b | T4 | AC30 | ibp/db.py, scenario/{branch,edits,promote}.py |
| T6 rete produttiva (T6.a→b→c→d) | sh-backend | 3 | T2, T6.0 | AC4,AC5,AC6,AC7,AC9,AC27 | ibp/network/** |
| T7 capacità+allocatore | sh-backend | 3 | T2, T6 | AC3, AC8 | ibp/capacity/** |
| T8 processo | sh-backend | 3 | T2 | AC20-23 | ibp/process/** |
| T9 adapter+viste | sh-data | 3 | T2 | AC24 (+AC9) | ibp/adapters/**, db/views/** |
| **T10.0** preload bulk (prerequisito bloccante T10) | sh-backend | 3 | T6.0 | AC29 | ibp/engine/engine.py, semantic/{dimensions,graph}.py |
| **T11.0** `not_comparable` esplicito (prerequisito T11/UI-SPEC) | sh-backend | 3 | T10.1 | AC28 | ibp/scenario/{compare,models,overlay,errors}.py |
| **T11.1** tabella provenienza — schema (prerequisito T11) | sh-data | 3 | T4 | AC31 (1/2) | db/schema.sql, build_db.py |
| **T11.2** `promote()` scrive provenienza (prerequisito T11) | sh-backend | 3 | T11.1, T10.1 | AC31 (2/2) | ibp/scenario/promote.py |
| T10 API HTTP | sh-backend | 4 | T5,T6,T7,T8,T9,T10.0,T10.1 | supporto AC11,AC22,AC29,AC30 | ibp/api/** |
| T11 workbench | sh-frontend | 5 | T10, T11.0, T11.2, UI-SPEC.md | AC11(manuale), supporto AC25 | web/** |
| T12 CLI+demo | sh-backend | 5 | T10 | AC9,AC25 | ibp/cli.py, scripts/** |
| T13 docs+diagrammi | sh-docs | 6 | T11, T12 | AC26 | docs/01-06, docs/diagrams/** |

Sotto-pacchetti T6: **T6.a** risoluzione N:N (AC4) → **T6.b** eleggibilità per region (AC5) →
**T6.c** routing obbligatorio + domanda dipendente (AC6,AC9) → **T6.d** routing elettivo +
back-allocation (AC7,AC27). Sotto-pacchetti T5: **T5.a** guardia import + serie + gerarchia →
**T5.b** baseline + riconciliazione (AC19) → **T5.c** snapshot lag costante + FVA (AC18).

## Open questions (SPEC, 2026-09-12)

Non bloccanti. Restano aperte dopo ADR-001 (che ne ha chiuse tre — vedi `decisions.md`):

1. Pool di modelli per T5 data la storia corta — consigliato `AutoETS`+`SeasonalNaive`+`AutoTheta`+
   `CrostonOptimized`, `AutoARIMA` disattivato di default; `MinTrace(ols)` titolare.
2. Granularità della partizione del DAG — mantenere per-cella in M1, partizionare per product family
   solo se T10 mostra latenza >200ms. Non blocca nulla.

*Chiuse il 2026-09-12 (nello SPEC stesso, prima di ADR-001):* split oltre l'orderbook (mix osservato
a consuntivo), offset domanda dipendente (fisso 2 mesi), back-allocation 3000 (AC27), soglie di
eccezione (seed ±20% w/w, tre livelli, `is_provisional` nel dato).

*Chiuse da ADR-001 (2026-09-19):* Average Assembly Hours/AC3 (D-007), sorgente job 3000 (D-008),
attributi routing elettivo NAM (D-006) — vedi `decisions.md`.
