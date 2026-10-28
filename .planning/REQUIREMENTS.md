# Requisiti: IBP ACMELIFT

**Definiti:** 2026-09-19 (ingest documentale + verifica contro il codice)
**Valore centrale:** Il planner cambia un numero e vede subito, sull'intero piano, cosa ne
consegue — su uno scenario che può confrontare e promuovere senza perdere né la base né la
tracciabilità.

## Note sulla numerazione

Il set di requisiti v1 è il set di **acceptance criteria AC1..AC31**, già approvato in
`docs/01-plan-m1.md` e reso canonico (testo, stato, estensioni AC27-AC31) in
`docs/02-spec-m1-corrente.md`. Non sono stati rinumerati né riscritti: la suite di test li mappa
uno a uno per nome di file (`test_<area>_ac<N>_<slug>.py`, vedi `.planning/codebase/TESTING.md`), e
rinominarli romperebbe quella corrispondenza.

A questi si aggiungono **cinque requisiti di consolidamento** emersi dalla verifica del codice
(`GRANA-01`, `GRAFO-01`, `MDATA-01`, `API-01`, `UX-01`): lavoro necessario che non aveva un AC
proprio. E **R-001**, requisito nuovo e LOCKED dall'ADR, di cui M1 realizza lo **Step A**.

I requisiti `REQ-F1..F13` (decisioni fissate) e `REQ-A1..A11` (architettura che deve reggere
M2/M3) restano in `.planning/intel/requirements.md`: sono **vincoli trasversali**, non unità di
consegna, e non compaiono nella tracciabilità per fase. Dove vincolano una fase specifica, la fase
li cita.

---

## Requisiti v1 (milestone M1)

### Modello dati e regole

- [x] **AC1** — `python db/build_db.py` ricostruisce il DB da zero, idempotente, cardinalità isomorfe.
- [x] **AC2** — `Max Slots`, granularità e soglia `<500` sono master data; test anti-literal.
- [ ] **AC3** — `Average Assembly Hours` ha un consumatore reale (allocatore). *Vincolato da D-007: input da revisionare prima del go-live; i test verificano la meccanica, non il valore assoluto.*

### Rete produttiva

- [ ] **AC4** — Mapping planning-model ↔ manufacturing-key many-to-many time-phased, override tracciato e distinguibile dal valore di regola.
- [ ] **AC5** — La stessa manufacturing key è producibile in più plant per `region_scope`; un plant non eleggibile viene rifiutato.
- [ ] **AC6** — Il routing obbligatorio genera domanda dipendente a offset **fisso 2 mesi** (`routing.lead_offset_months`), con consumo di capacità in entrambi i plant.
- [ ] **AC7** — Il routing elettivo (NAM) produce split diversi al variare del mix. *Vincolato da D-006: insieme di attributi di configurazione, estendibile senza modifiche di schema.*
- [ ] **AC8** — L'allocatore **propone** uno split multi-plant (orderbook dentro orizzonte, mix osservato a consuntivo oltre); override tracciato.
- [ ] **AC9** — Il percorso Excel→DB è sostituito dalla domanda dipendente generata dal routing.

### Motore

- [x] **AC10** — `recalculate(changed)` ≡ ricalcolo completo (test cardine).
- [x] **AC11** — Early cutoff osservabile e misurato.
- [x] **AC12** — `min`/`max`/`ratio` ricalcolati sul gruppo, non delta-aggiornati.
- [ ] **AC29** — `RecalcEngine.__init__` esegue **< 25 query** (oggi 14.397 misurate) e completa in **< 5s** (oggi 42,7s nella spec, 15,5s misurati su una macchina diversa — il conteggio di query è la soglia riproducibile, non il tempo).
- [ ] **GRANA-01** — La grana `(manufact_key, region, date_key)` sopravvive da `derived_manufacturing_demand` fino a `_eligible_plant_for`, che risolve il plant per `(manufact_key, region, date_key)` con validità temporale reale. *Precondizione bloccante di AC5; gate d'uscita: AC10 di nuovo verde.*

### Scenari

- [x] **AC13** — Branch → modifica → confronto → promozione crea una nuova istanza `DVERSIONS`.
- [x] **AC14** — Tombstone esplicito: una cella cancellata non ricompare dal base.
- [x] **AC15** — La cache key include lo stack; nessuna fuga fra scenari su basi diverse.
- [x] **AC16** — Promozione con base mossa → conflitto rilevato prima di qualunque scrittura.
- [ ] **AC28** — `compare()` restituisce una riga per **ognuna** delle 26 misure reali (19 `sum`, 1 `max`, 3 `avg`, 3 `ratio`); `avg`/`ratio` come `not_comparable` **con motivo esplicito**, mai invisibili.
- [ ] **AC30** — Transazioni rientranti: nessun `TransactionException` annidato, nessun COMMIT/ROLLBACK proprio se già dentro una transazione del chiamante.
- [ ] **AC31** — Ogni riga promossa risale a origine (`copied` / `overlay_override` / `prorated`), `scenario_id` ed `edit_id`; `TSOP_DEMAND`/`TSOP_OPS` restano isomorfe al mirror dEPM (tabella laterale).
- [ ] **R-001 (Step A)** — Piani salvati e scenari salvati sono **rami dello stesso tronco**: un solo tipo di puntatore al genitore, i due assi di stato (`SCENARIO_STATE` e fase di ciclo `P`/`R`/`A`/`C`) portabili indipendentemente dallo stesso nodo, una sola API uniforme di navigazione e lettura. *Step B (grana piena, `promote()` come spostamento di puntatore, risoluzione ricorsiva fino a root) rinviato a M2 — vedi v2.*

### Forecast

- [ ] **AC17** — La baseline statistica precompila la versione P; un override manuale resta distinguibile.
- [ ] **AC18** — FVA stairstep a **lag costante** ricostruibile da `forecast_snapshot`.
- [ ] **AC19** — Il forecast riconciliato è coerente lungo la gerarchia commerciale.

### Processo

- [ ] **AC20** — Ciclo P→R→A→C; una scrittura su `STAT_03` è rifiutata.
- [ ] **AC21** — Portfolio Review: l'output è input della Demand Review più consumo di capacità; gate come precondizione.
- [ ] **AC22** — Integrated Reconciliation genera un'agenda dai gap sopra soglia (unità e valore).
- [ ] **AC23** — `confirm_back_to_sales(cycle)` è nominata e distinta dalla Reconciliation. *Vincolato da D-008: il job `3000` è un carry-forward alternato.*
- [ ] **AC27** — Back-allocation job 3000: nessun planning model con contributo forward non nullo riceve zero; la somma ripartita coincide **esattamente** col totale confermato.

### Confine, ambiente e consumo

- [ ] **AC24** — Nessuna scrittura verso SAP o dEPM; il write-back è un **file**.
- [ ] **AC25** — Tutto offline su Windows.
- [ ] **AC26** — Diagrammi archify navigabili e coerenti col codice finale.
- [ ] **GRAFO-01** — `neighbors()` non rifiuta un `as_of` storico per node type che non possono avere archi derivati da `item_link` (oggi `graph.py:148` guarda solo `is_historical` e `rel_type`, mai `node_type`).
- [ ] **MDATA-01** — L'adapter di master data reale tratta Southport e Rivermouth come **un solo sito** (al più con alias) e `Eastbrook SEA` come **plant**. *Da D-003 / D-004: vincolo di go-live sull'adapter, non sul seed sintetico (verificato 2026-09-19: nessuno dei tre è nel seed).*
- [ ] **API-01** — Un'API HTTP interna espone motore, scenari e processo: creare un ramo, applicare edit, confrontare e promuovere passano da lì, atomicamente per richiesta.
- [ ] **UX-01** — Il workbench elenca tronco e rami come oggetti dello **stesso tipo** e permette di navigarli, confrontarli e promuoverli senza cambiare modello mentale.

---

## Requisiti v2 (M2 / M3 — fuori dalla roadmap corrente)

### Tronco unico, modifiche strutturali (M2)

- **R-001 Step B/1** — Grana di `overlay`/`edits` allargata alla grana piena dei fatti
  (`division_key`, `region`, `manufact_key`), così che un ramo possa rappresentare una riga completa
  e `UnmaterializableCellError` smetta di essere strutturale.
- **R-001 Step B/2** — `promote()` da copia materializzante a **spostamento di puntatore** (O(1)).
- **R-001 Step B/3** — Risoluzione ricorsiva omogenea fino a una **root esplicita**, senza salto a
  una tabella densa a un livello arbitrario dell'albero.

> Motivo del rinvio: tutte e tre collidono con `DVERSIONS.version_name` — colonna `UNIQUE` con
> grammatica fissa, letta come **stringa** dalle misure DAX di Power BI. Trasformare quel nome in
> un'etichetta applicabile a un nodo qualunque significa rinegoziare un contratto di consumo
> esterno, che M1 non può fare.

### Rete a monte (M2)

- **REQ-F11** — Dealer interni de-schiacciati; la richiesta è sales intercompany + richiesta
  aggiuntiva della region nello stesso mese, senza doppio conteggio.
- **REQ-F12** — Mounting competence center e dealer interni come nodi di capacità con un limite.
- **REQ-A11 (M2)** — Stock di canale a partita doppia con invariante somma-zero.

### Rete a valle (M3)

- **REQ-F13** — Fornitori interni come nodi con capacità propria, non sorgenti infinite.
- **REQ-A11 (M3)** — Componenti critici e `sourcing_split` per il double sourcing.

---

## Fuori scope

| Elemento | Motivo |
|---|---|
| Riscrittura di T1-T4 | Consegnati, reviewed, verdi (187 test) e riverificati contro il codice il 2026-09-19. Nessuna fase li ripianifica. |
| Multi-utente enterprise (locking a cella, versioning nativo, SSO/RLS, orchestratore) | M1 è in-process single-user (REQ-A6); il dominio deve sopravvivere alla migrazione, non anticiparla. |
| Solver esterno di ottimizzazione | `AllocationStrategy` resta un'interfaccia sostituibile (REQ-A3); M1 non implementa un ottimizzatore. |
| Scritture verso SAP S/4, Infor dEPM, ERP/MRP | Confine di sistema (AC24): SAP read-only, dEPM riceve un file, Power BI non toccato. |
| Partizione del DAG per product family | Resta per-cella in M1; si partiziona solo se la Phase 14 misura latenza >200ms. Non blocca nulla. |
| Reintroduzione di `numpy` come dipendenza | Esclusione deliberata e documentata in `db/seed/common.py`; il seed usa solo `random`/`math`/`hashlib` della stdlib. |
| Modifiche a `pyproject.toml` fuori da T1 | Proprietà esclusiva di T1, deroga già registrata e consumata (2026-09-12, pin `statsforecast`). |
| Mocking nella suite di test | La suite è per contratto su DB reale; un mock di DuckDB verificherebbe il mock. |

---

## Rischi aperti (da portare avanti, non bloccanti)

| Rischio | Dove morde | Nota |
|---|---|---|
| Pool di modelli forecast con storia corta | Phase 5 (T5.b) | Il seed cappa i fatti a 4 cicli chiusi + corrente: meno storia della produzione, l'ordine ARIMA è appena identificabile. Consigliato `AutoETS` + `SeasonalNaive` + `AutoTheta` + `CrostonOptimized`, `AutoARIMA` disattivato di default, `MinTrace(ols)` titolare. Verificare la copertura effettiva **prima** di scegliere il pool. |
| `routing.variant_key` in tensione con D-006 | Phase 8 (T6.d) | Lo schema la disegna come chiave singola opzionale; D-006 richiede un **insieme** di attributi estendibile senza modifiche di schema. Può bastare se incapsula l'insieme, ma va verificato esplicitamente, non assunto. |
| Partizione del DAG | Phase 14 | Per-cella in M1. Se l'API mostra latenza >200ms, la partizione per product family torna sul tavolo. |
| Percorso di forecasting mai esercitato | Phase 5 | Il pin `statsforecast==2.1.1` è risolvibile e wheel-installabile, ma nessuno ha ancora eseguito quel codice: l'ordine di import OpenMP va verificato a runtime, non solo per lettura. |

---

## Tracciabilità

| Requisito | Phase | Stato |
|---|---|---|
| AC1 | Phase 1 | Completo |
| AC2 | Phase 1 | Completo |
| AC10 | Phase 3 | Completo |
| AC11 | Phase 3 | Completo |
| AC12 | Phase 3 | Completo |
| AC13 | Phase 4 | Completo |
| AC14 | Phase 4 | Completo |
| AC15 | Phase 4 | Completo |
| AC16 | Phase 4 | Completo |
| AC17 | Phase 5 | Pendente |
| AC18 | Phase 5 | Pendente |
| AC19 | Phase 5 | Pendente |
| GRANA-01 | Phase 6 | Pendente |
| GRAFO-01 | Phase 6 | Pendente |
| AC30 | Phase 7 | Pendente |
| AC28 | Phase 7 | Pendente |
| AC4 | Phase 8 | Pendente |
| AC5 | Phase 8 | Pendente |
| AC6 | Phase 8 | Pendente |
| AC7 | Phase 8 | Pendente |
| AC9 | Phase 8 | Pendente |
| AC27 | Phase 8 | Pendente |
| AC3 | Phase 9 | Pendente |
| AC8 | Phase 9 | Pendente |
| AC29 | Phase 10 | Pendente |
| AC20 | Phase 11 | Pendente |
| AC21 | Phase 11 | Pendente |
| AC22 | Phase 11 | Pendente |
| AC23 | Phase 11 | Pendente |
| AC24 | Phase 12 | Pendente |
| MDATA-01 | Phase 12 | Pendente |
| R-001 (Step A) | Phase 13 | Pendente |
| AC31 | Phase 13 | Pendente |
| API-01 | Phase 14 | Pendente |
| UX-01 | Phase 15 | Pendente |
| AC25 | Phase 15 | Pendente |
| AC26 | Phase 16 | Pendente |

**Copertura:**
- Requisiti v1: **37** totali (31 acceptance criteria AC1..AC31 + 5 di consolidamento + R-001 Step A)
- Mappati su una fase: **37**
- Non mappati: **0** ✓
- Nessun requisito compare in più di una fase ✓
- Già completi: **9** (AC1, AC2, AC10, AC11, AC12, AC13, AC14, AC15, AC16) — Phase 1-4

> La Phase 2 (T2 — dominio, semantic layer, DAG dichiarato, grafo) non porta acceptance criteria
> propri: è la fondazione che rende verificabili AC10-AC16 ed è coperta da test strutturali
> (`test_db_single_entrypoint.py`, `test_domain_state_machines.py`,
> `test_semantic_measures_dag.py`, `test_semantic_numeric_types.py`, `test_semantic_graph.py`).
> Non è un requisito orfano: è una fase senza requisito, che è cosa diversa.

---
*Requisiti definiti: 2026-09-19*
*Ultimo aggiornamento: 2026-09-19, alla creazione della roadmap GSD*
