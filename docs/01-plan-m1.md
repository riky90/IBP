<!-- PRECEDENZA: SUPERSEDED in parte. Per i task, gli acceptance criteria e il backlog
     di M1 vale docs/02-spec-m1-corrente.md (rigenerato 2026-09-12). Questo documento
     resta autorevole solo per: contesto di business, misura Gartner, programma a tre
     milestone M1/M2/M3, e le decisioni di architettura che devono reggere M2/M3. -->

# Piano — Piattaforma IBP ACMELIFT

Programma in **tre milestone**. Questo piano descrive M1 in dettaglio eseguibile e M2/M3 a
livello di architettura, perché le decisioni di M1 devono già reggerli.

## Context

ACMELIFT ha un processo S&OP maturo e una tecnologia che non lo regge. La misura è interna:
Gartner Score 2024, 25 rispondenti — **processo S&OP 4-**, **planning technology, analytics e
culture 1**, complessivo **2** contro un benchmark manifatturiero di **3-**.

Il ciclo mensile P/R/A/C gira su Infor dEPM, si alimenta da SAP S/4 e si riporta in Power BI.
Funziona. Manca tutto ciò che o9, Kinaxis Maestro e DELMIA Quintiq danno per scontato: ricalcolo
immediato invece di batch, scenari illimitati, baseline statistica, vincoli come dati, eccezioni
che risalgono da sole.

E mancano due dei cinque review IBP — confermato da Oliver Wight, da Gartner e dall'utente:
**Portfolio Review** assente (`Plan New Products` scora **1+**: *"receive new product plans with
final volume targets"*); **Integrated Reconciliation** assente come forum (quello che oggi si
chiama reconciliation è il carry-forward `3600`, cioè *anchoring*); **MBR** spezzato in due gate.

Ma l'indagine ha trovato qualcosa di più grande del gap IBP.

### Quello che il modello attuale non rappresenta

Emerso dalle risposte dell'utente, non dai documenti. L'S&OP di oggi è una **semplificazione
consapevole** su cinque punti, e ognuno è lavoro manuale che qualcuno fa ogni mese:

1. **Planning model ↔ manufacturing key è many-to-many** nelle due direzioni (es. Timber &
   Recycling). Il modello lo tratta come attributo singolo `Linked Manufact Key`.
2. **Lo stesso manufacturing key si produce in più plant**, con regole di region. Il modello ha
   `Targeted Plant`, singolo.
3. **Esistono percorsi produttivi multi-step.** Due meccanismi distinti:
   - *Obbligatorio, guidato dal modello*: Cerritos compra ILK/ILT semi-finiti da Ganderkesee e
     finisce in casa; Niagara compra semi-finito perché non può produrre tutto. Non è una scelta.
   - *Elettivo, guidato dall'orderbook*: LC 10000 NAM può essere tutto-Northfield oppure
     pre-assemblato a Northfield e finito a Niagara, **secondo la configurazione venduta**.
4. **Il passo di ri-allocazione centrale non esiste nel sistema.** Il planner di region pianifica
   tutto sul modello della sua region; poi il team centrale, prima dell'handover a Operations,
   ri-alloca a Northfield **leggendo l'orderbook reale**. Sistematico, mensile, invisibile.
5. **La domanda dipendente del semi-finito è fatta in Excel.** Si prende la richiesta del finito e
   la si anticipa di 2 mesi (lead time + transit), **con file Excel che scrivono sul database**.

Tre conseguenze che vale la pena guardare in faccia:

> **L'offset di 2 mesi è lo stesso meccanismo in due posti.** Il vault documenta "Ableitung Basic
> Assemblies: clusterizza e applica un offset di 2 mesi"; l'utente descrive il semi-finito come
> "richiesta del finito anticipata di 2 mesi". È **domanda dipendente con lead-time offset** —
> nome, teoria e implementazione standard. Da voi è a mano.

> **Excel che scrive sul database è il rischio operativo più concreto emerso.** Nessun controllo di
> integrità, nessun audit, nessuna ripetibilità — e un errore produce un numero plausibile, non un
> errore. Sostituzione prioritaria in M1.

> **Oltre l'orizzonte dell'orderbook non si splitta.** Il piano a due anni alloca la produzione al
> plant di default della region. Il carico di Northfield nel medio termine non è quello vero — e il
> medio termine è l'orizzonte su cui si decidono capacità e investimenti.

### E la rete che l'S&OP vede a un solo livello

A monte: i dealer interni esistono ma sono **schiacciati al livello della region**; le
installazioni sono tracciate **solo** per i mounting competence center — quelle fatte dai dealer
interni non si vedono affatto. A valle: i plant ordinano componenti a fornitori esterni **e
interni** (partecipate), alcuni al 100% interni, altri con percentuali di **double sourcing**, e
niente di tutto ciò è in S&OP.

Questo, detto francamente, è l'argomento più forte a favore dell'overlay a grafo. Uno star schema
non tiene una rete multi-tier con nodi eterogenei — plant, region, dealer, importatore,
installatore, concessionario, fornitore. Passa da "utile" a "necessario".

**Esito voluto**: un sistema che preserva P/R/A/C, ci innesta i due review mancanti, **automatizza
i cinque punti manuali**, e apre la strada alla rete completa senza doverlo rifare.

---

## Decisioni fissate

| # | Decisione | Conseguenza |
|---|---|---|
| **F1** | La **domanda** si pianifica al modello commerciale; le opzioni non entrano nel piano di vendita | Ma **rientrano dalla supply**: la configurazione determina il routing (punto 3). Le opzioni servono come *mix per l'allocazione*, non come BOM |
| **F2** | La **baseline statistica precompila il P** | Versione forecast distinta; l'FVA nasce per costruzione |
| **F3** | Nessuna soglia documentata | Soglie = dato configurabile, default dichiaratamente provvisori |
| **F4** | Seed **sintetico ma isomorfo** | Nessun dato ACMELIFT nel repo |
| **F5** | Due forum board, nessun MBR unificato | MBR = forum unico di cui i due gate sono fasi |
| **F6** | Run = architettura + diagrammi + **scheletro eseguibile** | I documenti sono il deliverable; il codice li rende verificabili |
| **F7** | **PM↔MK many-to-many**, split a percentuali definite a priori + aggiustamento manuale del planner | Tabella di mapping time-phased, con override tracciato e distinguibile dal valore di regola |
| **F8** | **Allocazione multi-plant: il sistema deve proporla** | Non registrare una decisione umana: calcolarla. È il punto 4, automatizzato |
| **F9** | Il **routing elettivo è guidato dalla configurazione venduta**, letta dall'orderbook | Serve un mix di configurazione nel piano supply, alimentato dall'orderbook reale |
| **F10** | Il **semi-finito ha domanda propria** (domanda dipendente), offset **uniforme a 2 mesi** | Un solo parametro configurabile, non una matrice per lane |
| **F11** | L'unità pianificata restano le **vendite esterne**; la richiesta dei dealer interni è **sales intercompany + richiesta aggiuntiva della region**, nello stesso mese | Nessun doppio conteggio; il canale interno è un livello, non un secondo piano |
| **F12** | Installazioni: **mounting competence center e dealer interni sono nodi di capacità** con un limite | Il vincolo può essere a valle del plant, ed è oggi invisibile |
| **F13** | **Fornitori interni = nodi con capacità propria**, non sorgenti infinite | Il collo di bottiglia può essere dentro il gruppo |

---

## Le tre milestone

| | Contenuto | Perché in quest'ordine |
|---|---|---|
| **M1 — Core + rete produttiva** | Modello dati, motore concurrent, scenari, forecast+FVA, ciclo P/R/A/C con i 5 review, mapping N:N, routing multi-step, domanda dipendente, allocazione automatica su orderbook | È **tutto il lavoro manuale che fate oggi**. Gira da solo e sostituisce Excel |
| **M2 — Rete a monte** | Dealer interni de-schiacciati, sell-in intercompany, stock di canale con la partita doppia, nodi di capacità installazione (MCC + dealer) | Priorità dell'utente. Dà il segnale di domanda più pulito, e scopre un vincolo che oggi non si vede |
| **M3 — Rete a valle** | Componenti critici, fornitori interni come nodi con capacità, percentuali di double sourcing | Risponde a "il piano è fattibile lato materiale?". Dipende dal grafo che M1 e M2 hanno costruito |

Ogni milestone gira e si usa da sola. M1 è il run che parte ora.

---

## Cosa dice il vault (e cosa non dice)

I blank contano quanto i fatti: il sistema non deve inventare fatti ACMELIFT.

### Prodotto
- `DSALES_PRODUCT` ~1.661 membri — `Product Division ▶ Product Line ▶ Category/Class ▶ model`.
- `DMANUFACT_KEY` ~1.346 membri — `Product Line ▶ Manufacturing Category ▶ Family ▶ model`;
  include i **Cluster 10–15, 31–33, 38**. Porta **`Average Assembly Hours`**, che **nessuna misura
  legge**.
- Il bridge oggi è un **attributo** (`Linked Manufact Key`, `Targeted Plant`) — **e F7/F8 lo
  smentiscono**: la realtà è many-to-many in entrambe le direzioni.
- **Blank totale sui configurabili**: `KMAT`, `characteristic`, `variant`, `option` non compaiono
  mai in contesto ACMELIFT. Nessuna BOM a nessun livello.

### Capacità — dove il sistema guadagna di più
Due valute: **rate** (`Production units/day` ÷ `Average maximum capacity per day` =
`Capacity utilization`) e **slot** (`Weeks Production` da `CIT_PUTTHROUGHTIME`, spalmata su due
mesi: `Current = IF(W<=4, W/4, 1)`, `Previous = IF(W>4, (W-4)/4, 0)`).

I cinque literal che il vault segnala — **ognuno, sbagliando, produce un numero plausibile anziché
un errore**:

| Literal | Cosa succede quando sbaglia |
|---|---|
| `Max Slots` = 30 se `"Westvale (FR)"` else 8 | Aggiungere un plant richiede modificare il codice |
| `×2` sugli slot dello stesso plant | Conversione di unità invisibile, fuori dal model doc |
| `PLval2`: se piano < **500**, usa il budget | Magic number senza razionale |
| `SOP_SEP_BL_2026` hard-typed | Anno sbagliato in silenzio al rollover |
| `TODAY() - 31` come "mese scorso" | Deriva sui mesi da 30 giorni |

Significato dietro `Max Slots` (fonte: Mario, verbale — **non** nel model documentation): altri
plant = **isole a 8 postazioni**; Westvale = **linea a flusso, 30 unità/mese**. Il ×2 è
**conversione di unità lato domanda**, per questo `Capacity utilization` resta corretta.

`DPLANT` ~52 membri, 5 Region, **nessun attributo di capacità**. È lì che i literal devono atterrare.

**Blank**: nessun algoritmo di allocazione, nessuna policy di prioritizzazione, nessuna provenienza
per `Capacity_avg_max`, nessun consumatore di `Average Assembly Hours`.

### Carry-forward
Job: `2000` crea istanza · `3000` Init Sales Plan (P **e** R) · `3100` Inventory & FMS · `3300`
Actuals · **`3600` "Confirmation back to Sales"** · `4000` Allocated + Ableitung · `4100` Confirmed
· `5000` WSC · `6000`/`6200` Budget · `7200` SEP/MTP.

**`3600` è il carry-forward descritto dall'utente.** Il vault lo nomina e non lo specifica mai.
Da non confondere con l'altro, che il vault *sì* documenta: gli **actuals** atterrano nel **P** del
ciclo successivo (`3000`). Il vault **non dice** da quale istanza `3000` copi — non assumerlo.

Incidente noto: rollover 2023→2024, inventario non calcolato perché Cycle 01 non aveva mesi actual
2024. Patch a `3000` via TRN→TST→PRD, con avviso che **può ripetersi**.

### Forecast — il blank è la premessa di F2
Ogni documento descrive **inserimento manuale**. **Nessun job genera un forecast; nessuna misura
DAX contiene una baseline; nessun membro di `DVERSIONS` è una versione statistica.** L'unica
evidenza contraria è una riga della self-assessment Gartner (score **2** vs peer 3), non
corroborata da alcun documento di sistema — affermazione, non fatto.

`open-questions.md`: se `DVERSIONS` trattenga la baseline separatamente decide se l'**FVA** è un
cambio di reporting o di modello dati. **F2 la risolve: modello dati.**

Già in DAX: `Bias`, `MAPE`, `WMAPE`, `Forecast Accuracy`, `Plant Reliability`, e il metodo
**N-Value** (4 o 6 mesi) che raggiunge indietro **ricostruendo il nome dell'istanza come stringa**.
Misure: `Order Book` (**STO/WSO/CCO**), `Requested Production`, `Inventory`, **FMS**,
`Order Entry`, `Order Coverage`, `Sales to Remain`, **L&O**, **Frozen Zone**.

### Versioni ed eccezioni
`DVERSIONS` ~466 membri, 4 per ciclo. Power BI: `Version 2` primario, `Version 1` confronto — **il
lettore sceglie entrambi i lati di ogni varianza**, quindi la notazione IBCS non è decidibile a
design time. Stati `STAT_01/02/03`. RLS **dall'email** via `vw_gt_access_snops_region/_product`
(fallimento noto: email cambiata → report vuoto, non errore).

**Exception-based planning: nulla di documentato.** `Manage Out-of-Plan Exceptions` **2+**;
`Manage Execution Priorities` **1,83** con **leader 4,33 vs team 1,83** — la divergenza più ampia
dell'assessment. Soglie a tre livelli e ±20% w/w sono **letteratura Gartner**. Conferma **F3**.

---

## Architettura

### A1 — Il vocabolario ACMELIFT è già quello standard
`commercial model → manufacturing key → plant slots` mappa **1:1** sul pattern industriale
documentato:

| Livello ACMELIFT | Concetto standard |
|---|---|
| `DSALES_PRODUCT` | Planning bill / ATO model — portatore del forecast |
| `DMANUFACT_KEY` | Planning config — **classe di equivalenza per conseguenza manifatturiera** |
| Plant slot | Risorsa RCCP `SLOT_POOL` — vincolo cumulativo intero per bucket |

`DMANUFACT_KEY` è già la mossa che la letteratura raccomanda contro l'esplosione configurazionale:
collassare 10⁶ configurazioni in 10²–10³ chiavi equivalenti *dal punto di vista della capacità*.
ACMELIFT lo fa senza chiamarlo così. Il sistema lo nomina, non lo sostituisce.

Corollario: lo spread su due mesi di `Weeks Production` è un **resource profile RCCP con lead-time
offset** — la più sofisticata delle tre varianti RCCP. Va nominato e reso configurabile, non
reinventato.

### A2 — Rete produttiva: da attributi a relazioni
Il cuore di M1. Quattro tabelle sostituiscono due attributi.

```
product_mapping(planning_model, manufacturing_key, period, pct, source, override_by)
      → F7. Many-to-many time-phased. `source` distingue regola da override manuale.

production_eligibility(manufacturing_key, plant, region_scope, priority, valid_from, valid_to)
      → F8. Quali plant POSSONO fare cosa, per quale region. Non chi lo fa: chi può.

routing(manufacturing_key, variant_key?, step_no, plant, operation_type,
        lead_offset_months, mandatory)
      → F9/F10. `mandatory=true`  → Cerritos/ILK, Niagara: non è una scelta.
        `mandatory=false` → il caso NAM: lo step dipende dalla configurazione venduta.

bill_of_resource(manufacturing_key | variant_key, resource_id, qty_per_unit,
                 offset_periods, spread_profile)
      → capacità per step, con l'offset. È lo spread esistente, generalizzato.
```

**Slot-equivalence factor** per manufacturing key: una gru 33t consuma 1,8 slot standard. Il ×2 di
Westvale diventa il caso particolare `factor = 2` — il literal sparisce dentro il dato.

**Domanda dipendente (F10)**: il semi-finito è un `manufacturing_key` con domanda propria, generata
dal routing con offset **uniforme a 2 mesi** (parametro unico, configurabile). È la sostituzione
diretta del file Excel che scrive sul database.

### A3 — L'allocatore: il passo che oggi è manuale
Il pezzo con il ritorno più immediato (**F8**). Innesto: **fra R e A**, all'handover a Operations
del giorno 10 — esattamente dove il team centrale lavora oggi.

Due orizzonti, due criteri:
- **Dentro l'orderbook**: split derivato dagli **ordini reali già configurati**. È il dato migliore
  che esista e voi lo usate già; il sistema smette solo di farvelo fare a mano.
- **Oltre l'orderbook**: oggi non si splitta affatto (tutto sul plant di default della region), che
  è il buco strutturale. *Raccomandato:* **mix di configurazione osservato a consuntivo** sugli
  ultimi N mesi, proiettato e vincolato dalla capacità eleggibile — così il mix non lo mantiene
  nessuno a mano e la deriva è visibile. Vedi questione aperta 1.

L'allocatore **propone**; il planner accetta o corregge; l'override è tracciato e distinguibile dal
valore calcolato. `AllocationStrategy` resta un'interfaccia: la default è greedy a priorità, e un
solver CP-SAT stile Quintiq si innesta sostituendo l'implementazione — **fuori scope M1**.

### A4 — Semantic layer: mirror + graph overlay
Star schema dEPM **rispecchiato 1:1** come nucleo canonico, esteso con **una** tabella di archi
tipizzati `edge(from_type, from_key, rel_type, to_type, to_key, valid_from, valid_to, attrs_json)`.

*Perché:* lo star schema è l'ontologia già concordata e Power BI ci si appoggia; riscriverla in un
EKG romperebbe l'unico asset semantico condiviso. Ma il grafo è **necessario**, non ornamentale: la
rete multi-tier di M2/M3 — plant, region, dealer, importatore, installatore, concessionario,
fornitore — non entra in uno star schema. M1 costruisce il grafo con due tipi di nodo (plant,
region) e M2/M3 ne aggiungono senza migrazioni.

**Corollario obbligato: le regole escono dal codice.** `Max Slots`, granularità e la soglia `<500`
diventano master data. AC: *aggiungere un plant non richiede modifiche a codice*.

### A5 — Motore: concurrent planning
DAG dichiarativo di misure con propagazione dirty. ~300 righe:

1. Nodi = misure; DAG statico validato aciclico con **`graphlib`** (stdlib, zero dipendenze).
2. Ogni nodo ha **height** = 1 + max(height input); ricalcolo in **min-heap per height** → elimina
   i glitch e il diamante: un nodo con due percorsi si ricalcola **una volta**, a input correnti.
3. **Early cutoff**: dopo il ricalcolo confronta l'hash; se invariato, **non** sporca i dipendenti.
   L'ottimizzazione a leva più alta — un edit in una region lascia intatto il 90% dei plant.
4. **Pull-based sui nodi osservati**: marca dirty su edit, calcola solo ciò che la griglia guarda.

**Granularità `(misura, partizione)`, non cella.** Per-cella = milioni di oggetti Python e
l'interprete domina l'aritmetica; per-misura = 2M righe per un edit. Partizione naturale:
**product family**. Il ricalcolo vettorizzato di una slice da 50k righe è ~1 ms.

**Trappole da progettare via:**
- *Aggregazione*: delta-update **solo** sum/count. Min/max/ratio/media pesata sono non invertibili
  → ricalcolo sul gruppo. Dichiarato nei metadati della misura.
- *Cicli*: capacità ↔ produzione pianificata li vuole davvero. Rilevati alla registrazione;
  incapsulati in **un** nodo con punto fisso iterato e guardia di max-iterazioni. Mai nella
  propagazione generale.
- *Cache key*: deve includere l'identità **completa** dello stack di scenari, o A serve gli
  aggregati di B. È il bug più probabile da spedire.

**Il test cardine**: `incrementale ≡ ricalcolo completo` su sequenze casuali di edit. Più un
pulsante "full recalc".

**Onestà sulla scala**: in-process, single-user. Enterprise significa store colonnare multi-utente
con overlay versionati e invalidazione distribuita. Lo scheletro dimostra la **semantica** (ogni
input ripropaga, niente batch notturni), non la scala.

### A6 — Persistenza: DuckDB + Polars
**DuckDB** store durevole e superficie di query/pivot; **Polars** layer di calcolo caldo; **Arrow**
cucitura zero-copy.

1.700 × 52 × 24 ≈ 2,1M celle per misura per scenario, ma il cubo è **sparso** (2–10% reale). Sta in
RAM. Il vincolo è la **latenza** (<200 ms per ripropagazione), non il volume.

**Gotcha Windows, nei docs il giorno 1:**
- DuckDB **single-writer con lock di processo** → server UI e job forecast condividono **una**
  connessione (thread, non processi).
- **L'autoload delle extension richiede internet** → disattivarlo e pre-installare, per un demo
  davvero offline.
- `temp_directory` esplicito; **esclusione Windows Defender** sulla dir dati; niente `fork()` →
  threading Rust di Polars, non process pool; **versione Polars pinnata** (regressioni di memoria
  note).

*Enterprise, in breve:* motore in-memory multi-utente con locking a livello di cella e versioning
nativo, SSO con RLS dalle stesse viste `vw_gt_access_snops_*`, orchestratore al posto dei job
numerati, audit immutabile, compute orizzontale. Nulla del file DuckDB sopravvive; sopravvivono
**modello di dominio, stati e interfacce**.

### A7 — Scenari: event log → overlay → layer stack
Kinaxis descrive il proprio motore come *"like a version control system for data"*. Il design lo
riproduce.

```
edits(append-only) → overlay(scenario_id, …, value, is_deleted) → COALESCE(l3,l2,l1,base)
```

- **Event log append-only** come verità: undo/redo, audit per l'FVA, ricostruzione deterministica.
  L'overlay è **cache**, non sorgente.
- **Tombstone esplicito**: `COALESCE(delta, base)` **non sa esprimere** "riga rimossa nello
  scenario" — un NULL cade sul base. E "il planner ha messo zero" ≠ "nessun override": tre stati,
  **mai NULL come sentinella**, imposto da **una** vista certificata.
- **Overwrite vs increment dichiarato per misura**, mai misto.
- **Confronto**: full outer join sull'**unione delle chiavi**, su valori **risolti**.
- **Promozione = three-way merge** (base-al-branch, base-ora, delta): richiede di salvare la base
  version alla creazione del branch, o la promozione clobbera in silenzio. Materializza una
  **nuova** istanza `DVERSIONS` conforme; nessuna istanza esistente viene mai mutata.
- **Annidamento** = layer stack innermost-first, profondità max 2–3.

*Perché fuori da `DVERSIONS`:* la convenzione di naming è **logica applicativa portante** — le
misure DAX ricostruiscono i nomi come stringhe.

### A8 — Forecast statistico e FVA
**`statsforecast` + `hierarchicalforecast` + `utilsforecast`**, pinnati, wheel in un wheelhouse
locale. **Prophet escluso** (toolchain C su Windows, build failure ricorrenti).

Pool: `AutoETS`, `AutoTheta`, `SeasonalNaive`, `CrostonOptimized`, `TSB`, `WindowAverage`;
selezione per MASE cross-validata; `SeasonalNaive` come fallback. Con 24–36 mesi l'ordine ARIMA è a
malapena identificabile → `AutoARIMA` opzionale. 1.700 serie mensili: secondi–decine di secondi.

Riconciliazione: **`MinTrace(mint_shrink)`** titolare, `BottomUp` confronto. Trappola: MinT richiede
residui in-sample di **ogni** serie (`fitted=True`) e una gerarchia **strettamente** consistente —
un prodotto sotto due padri rompe la coerenza in silenzio.

**FVA — nello schema il giorno 1, non ricostruibile dopo:**

```
forecast_snapshot(series_id, target_period, created_period, lag, process_step, value)
```

Ha senso solo a **lag costante**. Salvare solo l'ultimo forecast **distrugge l'FVA per sempre**.
Servono anche: benchmark naïve **calcolato e salvato contestualmente**, baseline **immutabile come
emessa**, actuals **con storia di restatement** (actual tardivi cambiano l'FVA storico in silenzio),
e **metadati di override** (chi, quando, reason code).

Stairstep: `Naïve → Baseline → Rettificata → Consenso`. **FVA negativo allo step del planner è
comune e onesto** — oltre metà dei forecast studiati fa peggio di un random walk. È il risultato
che rende la demo credibile.

### A9 — I due review mancanti
**Portfolio Review** — giorni **1-5, prima di P**; gate `PortfolioApproved` precondizione per aprire
P. Entità: `portfolio_item` (lifecycle), `project` (`Proposed → … → Closed`),
**`project_resource_demand`** (plant, periodo, slot/ore — è ciò che rende il piano *resourced*),
`portfolio_decision`. Output: `portfolio_commitment` nella baseline di demand, prenotazione di
capacità, gap non coperti → Reconciliation.

**Integrated Reconciliation** — giorni **15-16, tra A e C**. `gap` (unità **e** valore, con owner,
categoria, stato), `reconciliation_session` con **agenda generata dai gap sopra soglia**,
`decision`, `escalation`. `rate_card` finanziarizza il piano volumi. Output verso l'MBR: **un solo
set di piani + una lista decisioni**.

**Il carry-forward resta e viene nominato**: `confirm_back_to_sales(cycle)` — funzione di dominio
esplicita, **distinta** dalla Reconciliation. Il sistema non lo toglie: chiarisce che è anchoring.

### A10 — Confine

| Sistema | Il sistema IBP… |
|---|---|
| SAP S/4 | **consuma** master data materiale, read-only; mai scrive |
| Infor dEPM | **consuma** dimensioni ed estratti; **restituisce** il piano promosso come **file** per Application Studio |
| Power BI | **non tocca**; espone viste in forma star |
| ERP/MRP | fuori confine |

**È un sistema di pianificazione, non un secondo ERP.** Se un oggetto ha una controparte
transazionale in SAP, qui esiste solo come chiave e attributi di pianificazione.

### A11 — Architettura di M2 e M3 (non implementata ora, ma M1 deve reggerla)

**M2 — rete a monte.** Nodi `dealer_interno`, `importatore` (interno/esterno), `installatore`,
`concessionario`, `mounting_competence_center`; archi `sells_to`, `installs`. Regole (**F11**):
l'unità pianificata restano le **vendite esterne**; la richiesta dei dealer interni è **sales
intercompany + richiesta aggiuntiva della region verso le fabbriche**, nello stesso mese — nessun
doppio conteggio.

*Stock di canale*: la partita doppia che oggi fate — financial stock su region/plant, poi
**negativo** sullo stock intercompany della region e **positivo** su quello del dealer — è una
**riconciliazione di proprietà lungo il canale**, non un attributo di magazzino. Modellata come
tale: `stock_position(node, product, period, qty, ownership_layer)` con l'invariante che la somma
degli strati intercompany sia zero. Senza questo, lo stock di canale resta invisibile dove serve.

*Capacità installazione* (**F12**): MCC **e dealer interni** sono `Resource` con limite e calendario.
Quelle dei dealer oggi non si tracciano affatto — è il vincolo che il sistema scopre.

**M3 — rete a valle.** `component`, `supplier` (interno/esterno) come **nodi con capacità propria**
(**F13**), `sourcing_split(component, supplier, period, pct)` per il double sourcing. Solo componenti
critici/long-lead: il confine "non è un ERP" resta.

---

## Layout

```
pyproject.toml              # tutte le dipendenze, una volta (T1)
db/  schema.sql  seed/  build_db.py  views/
data/ibp.duckdb             # generato, gitignored
ibp/
  domain/      entità, macchine a stati, value objects
  semantic/    registry dimensioni + misure (DAG dichiarato), overlay a grafo
  network/     mapping N:N, eligibility, routing multi-step, domanda dipendente
  capacity/    bill of resource, slot equivalence, RCCP, allocatore
  engine/      recalc incrementale, finanziarizzazione, eccezioni
  scenario/    event log, overlay, confronto, promozione
  forecast/    baseline, riconciliazione gerarchica, FVA
  process/     ciclo P/R/A/C, 5 review, gate, RACI, carry-forward 3600
  adapters/    infor_import, sap_master, powerbi_export, infor_writeback
  api/         router FastAPI
  cli.py       comandi + demo end-to-end
web/           workbench statico (no build, no CDN)
docs/          01-architecture · 02-domain-model · 03-process-model · 04-data-model
               · 05-network-model · 06-adr + diagrammi archify
tests/         (sh-tester)
```

---

## Come si esegue — skill e agenti

Orchestrazione con **`/software-house`**: io decompongo e dispaccio, non scrivo codice di prodotto.

| Stage | Chi | Cosa |
|---|---|---|
| Piano | `sh-architect` | Rigenerato con questo contesto |
| **Diagrammi** | **`archify`** | Architettura a layer, **rete produttiva multi-step**, ciclo P/R/A/C con i 5 review, DAG di ricalcolo, lifecycle scenari. **Subito dopo l'approvazione** — l'architettura si guarda mentre il codice si costruisce |
| **UI contract** | **`/gsd-ui-phase`** | `UI-SPEC.md` prima che `sh-frontend` scriva markup. È l'unico buco reale di software-house |
| Implementazione | `sh-data`, `sh-backend`, `sh-frontend` | Un task ciascuno, path esclusivi, ondate parallele |
| Test | `sh-tester` | Automatico dopo ogni implementatore; possiede `tests/**` |
| Review | `sh-critic` | Verdetto bloccante PASS/FAIL contro le AC |
| Escalation | `/gsd-debug` | Migliore di `sh-debugger`: mantiene stato fra context reset |
| Docs | `sh-docs` | `docs/01`–`06`. **È il deliverable primario** |
| **UAT** | **`/gsd-verify-work`** | Validazione conversazionale con te |

**Su GSD, il giudizio onesto**: `/software-house` copre già plan → build → test → review → docs.
Innestarci `/gsd-new-project` creerebbe `.planning/` accanto a `.software-house/` — due sistemi che
dicono le stesse cose con vocabolario diverso, e due verità che divergono. GSD **solo dove
software-house non arriva**: contratto UI, debug con stato persistente, UAT.

---

## Backlog M1

13 task, 6 ondate. Path esclusivi per ondata. `pyproject.toml` è di **proprietà esclusiva di T1**.

| T | Owner | Cosa | dep | Wave |
|---|---|---|---|---|
| **T1** | `sh-data` | Schema DuckDB + seed isomorfo (incl. mapping N:N, eligibility, routing, `forecast_snapshot`, event log, `edge`) | — | 0 |
| **T2** | `sh-backend` | Dominio, macchine a stati, semantic layer, DAG **dichiarato**, grafo di rete | T1 | 1 |
| **T3** | `sh-backend` | Motore concurrent planning (height, early cutoff, pull) | T2 | 2 |
| **T4** | `sh-backend` | Scenari: event log, overlay, confronto, promozione | T2 | 2 |
| **T5** | `sh-backend` | Forecast statistico + riconciliazione + FVA | T2 | 2 |
| **T6** | `sh-backend` | **Rete produttiva**: mapping N:N, eligibility, routing multi-step, domanda dipendente | T2 | 3 |
| **T7** | `sh-backend` | **Capacità e allocatore**: bill of resource, slot equivalence, RCCP, allocazione su orderbook | T2, T6 | 3 |
| **T8** | `sh-backend` | Processo: P/R/A/C, 5 review, portfolio, reconciliation, `3600` | T2 | 3 |
| **T9** | `sh-data` | Adapter Infor/SAP + viste Power BI + **sostituzione del path Excel→DB** | T2 | 3 |
| **T10** | `sh-backend` | API HTTP | T3–T9 | 4 |
| **T11** | `sh-frontend` | Workbench (dopo `UI-SPEC.md`) | T10 | 5 |
| **T12** | `sh-backend` | CLI + demo end-to-end | T10 | 5 |
| **T13** | `sh-docs` | `docs/01`–`06` + integrazione diagrammi | T11, T12 | 6 |

### Acceptance criteria

**Modello dati e regole**
- **AC1** — `python db/build_db.py` ricostruisce il DB da zero, idempotente, con nomi dEPM
  preservati e cardinalità isomorfe (~1.661 / ~1.346 / 52 / 62).
- **AC2** — `Max Slots`, granularità e la soglia `<500` sono **master data**: aggiungere un plant
  **non richiede modifiche a codice**. Un test fallisce se `30`, `8` o `500` compaiono nel codice
  di calcolo.
- **AC3** — `Average Assembly Hours` ha un consumatore reale (seconda valuta di capacità).

**Rete produttiva** — il cuore di M1
- **AC4** — Un planning model si distribuisce su **più** manufacturing key con percentuali
  time-phased, e più planning model **aggregano** sulla stessa manufacturing key. L'override
  manuale è tracciato e distinguibile dal valore di regola.
- **AC5** — Lo stesso manufacturing key è producibile in **più plant** secondo `region_scope`, e il
  sistema **rifiuta** un'allocazione a un plant non eleggibile.
- **AC6** — Il routing **obbligatorio** (ILK/ILT: Ganderkesee → Cerritos) genera **domanda
  dipendente** sul semi-finito, anticipata di **2 mesi**, e consuma capacità in **entrambi** i plant.
- **AC7** — Il routing **elettivo** (NAM) produce split diversi al variare del mix di
  configurazione, e il carico di Northfield cambia di conseguenza.
- **AC8** — L'allocatore **propone** lo split multi-plant: dall'orderbook dentro l'orizzonte, dal
  mix osservato oltre. Il planner può correggere; l'override è tracciato.
- **AC9** — Il percorso Excel→DB è sostituito: la domanda dipendente si genera dal routing, non da
  un file.

**Motore**
- **AC10** — `recalculate(changed)` propaga il dirty e **il risultato è identico al ricalcolo
  completo**, su sequenze casuali di edit *(il test cardine)*.
- **AC11** — L'early cutoff è osservabile e misurato: un edit che non cambia un aggregato **non**
  sporca i dipendenti.
- **AC12** — Min/max/ratio sono ricalcolati sul gruppo, non delta-aggiornati.

**Scenari**
- **AC13** — Branch → modifica sparsa → confronto → **promozione** che crea una **nuova** istanza
  `DVERSIONS`. Nessuna istanza esistente viene mai mutata.
- **AC14** — Tombstone: una riga cancellata in uno scenario **non ricompare** dal base.
- **AC15** — La cache key include lo stack: A **non** serve mai aggregati di B.
- **AC16** — Promozione con base mossa dal branch time → **conflitto**, non sovrascrittura.

**Forecast**
- **AC17** — La baseline precompila la P; l'override del planner è distinguibile dal valore generato.
- **AC18** — L'FVA stairstep si calcola **a lag costante** da `forecast_snapshot`.
- **AC19** — Il forecast riconciliato è **coerente** lungo la gerarchia prodotto.

**Processo**
- **AC20** — Ciclo P→R→A→C con `STAT_01/02/03`; scrivere su fase `STAT_03` è **rifiutato**.
- **AC21** — Portfolio Review: output approvato = input della Demand Review **e** consumo di
  capacità; `PortfolioApproved` precondizione per aprire P.
- **AC22** — Integrated Reconciliation genera l'agenda **dai gap sopra soglia**, in unità e valore,
  e produce decisioni/escalation; l'MBR riceve un solo set di piani.
- **AC23** — `confirm_back_to_sales(cycle)` esiste come funzione nominata e distinta, documentata
  come *anchoring*.

**Confine e ambiente**
- **AC24** — Nessuna scrittura verso SAP o dEPM; il write-back è un **file**. Nessun oggetto
  ordine/BOM/MRP.
- **AC25** — Tutto **offline** su Windows: `pip install -e .` + un comando, nessun cloud, nessuna
  licenza, nessun CDN, extension DuckDB pre-installate.
- **AC26** — I diagrammi archify sono navigabili e coerenti con il codice finale.

---

## Verifica

**Automatica** — `pytest`:
1. `incrementale ≡ full recalc` su sequenze casuali *(cardine)*.
2. Tombstone, cache-key per scenario, conflitto in promozione.
3. FVA a lag costante ricostruito dagli snapshot; coerenza gerarchica del forecast.
4. Routing obbligatorio → domanda dipendente a −2 mesi con doppio consumo di capacità.
5. Allocazione a plant non eleggibile → rifiuto.
6. Rifiuto di scrittura su `STAT_03` e su istanza `DVERSIONS` ufficiale.
7. Assenza di literal (`30`, `8`, `500`) nel codice di calcolo.

**End-to-end** — `python -m ibp.cli demo`: apertura ciclo → Portfolio Review con NPI e phase-out
risorsati → baseline statistica → P → override planner → R → mapping N:N a manufacturing key →
**allocazione multi-plant proposta su orderbook** → **routing multi-step con domanda dipendente sul
semi-finito** → allocazione vincolata A → scenario what-if, confronto, promozione → Integrated
Reconciliation con agenda dai gap → decisioni → gate → `confirm_back_to_sales` → export. Stampa gap
in unità e valore, eccezioni, decisioni e **stairstep FVA**.

**Manuale** — `uvicorn ibp.api.app:app` → `http://localhost:8000/`: timeline del ciclo, modifica di
una cella con i valori a valle aggiornati senza reload, confronto `Version 1`/`Version 2`, **vista
di rete con il routing multi-step**, lista eccezioni, sessione di reconciliation.

**UAT** — `/gsd-verify-work`.

---

## Questioni aperte — nessuna bloccante

1. **Split oltre l'orizzonte dell'orderbook.** Oggi non si splitta (tutto sul plant di default).
   *Consigliato:* mix di configurazione **osservato a consuntivo** sugli ultimi N mesi, proiettato e
   vincolato dalla capacità eleggibile — così nessuno lo mantiene a mano e la deriva è visibile.
   È la decisione più impattante di M1 sul medio termine.
2. **Granularità della partizione DAG** — *consigliato:* product family, perché la derivazione
   demand→manufacturing è per prodotto. Configurabile, decisa su misura nel seed.
3. **`Average Assembly Hours`** — l'attributo esiste e nessuno lo legge. *Consigliato:*
   implementarlo come valuta alternativa agli slot per i plant a isole. Da confermare che il dato
   sia popolato davvero.
4. **Da quale istanza copia il job `3000`** — il vault non lo dice. *Consigliato:* parametro
   esplicito (`copy_from: version_ref`) invece di un'assunzione. Una conversazione lo chiude.
5. **Soglie di eccezione** — nessuna documentata (**F3**). *Consigliato:* seed con ±20% w/w e i tre
   livelli Gartner, marcati **provvisori nel dato**, non nel commento.
6. **`variant_key` nel routing elettivo** — quale attributo della configurazione guida davvero lo
   split (colore è un esempio, non la variabile). *Consigliato:* modellarlo come chiave opaca
   alimentata dall'orderbook, così il sistema funziona prima di saperlo e lo scopre a consuntivo.
