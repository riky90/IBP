# IBP Platform — Research Brief

Data: 2026-09-10. Fonti: web (o9, Kinaxis, DELMIA Quintiq) + vault `Claude_Cervello` (Acmelift S&OP).

## 1. Come sono fatte le piattaforme di riferimento

### o9 Solutions — "Digital Brain"
- **Nucleo**: Enterprise Knowledge Graph (EKG) brevettato — modello a grafo dell'impresa (prodotti, clienti, plant, fornitori, risorse, misure) che funge da *digital twin* e da memoria semantica condivisa. Non è uno star schema: è un grafo su cui girano i piani.
- **Sopra il grafo**: big-data store, motori di forecasting/ottimizzazione, scenario engine, NLP/LLM, agenti.
- **Moduli**: demand planning & sensing, supply planning, S&OP/IBP, revenue/commercial planning, NPI, inventory, control tower.
- **Idea architetturale chiave**: un solo modello semantico, molte app sopra. Le "tribal knowledge" (regole di business) vivono nel grafo, non nei report.

### Kinaxis Maestro (ex RapidResponse)
- **Nucleo**: database in-memory scritto in-house + **concurrent planning** — ogni modifica di un input ricalcola e ripropaga l'intero piano in near-real-time, invece di batch sequenziali demand→supply→inventory notturni.
- **Scenari**: what-if illimitati, sandbox per planner su dati reali, confronto e promozione dello scenario.
- **Struttura**: un unico data model + una code base + una UI, con suite di app collegate (demand, supply, inventory, capacity, S&OP).
- **Idea chiave**: la latenza del ciclo di pianificazione è il vero problema. Chi ricalcola in secondi elimina la riconciliazione manuale.

### DELMIA Quintiq (Dassault)
- **Nucleo**: motore di ottimizzazione multi-tecnologia — mathematical programming, constraint programming, path optimization, graph programming — pilotato da **Quill**, linguaggio proprietario di modellazione dei vincoli.
- **Struttura a 3 strati**: (1) piattaforma SOA con optimizer + planning management, (2) template verticali di settore, (3) modello custom per cliente.
- **Idea chiave**: ogni azienda ha vincoli irriducibili. Non si configura un prodotto: si *modella* il problema e si lascia risolvere l'optimizer.

### Sintesi — cosa condividono (il pattern architetturale da copiare)
| Layer | Funzione | o9 | Kinaxis | Quintiq |
|---|---|---|---|---|
| L1 Integration | ingest ERP/CRM/esterni, master data harmonization | connectors + big data | connectors | SOA adapters |
| L2 Semantic model | il "gemello digitale" dell'azienda | EKG (grafo) | in-memory data model | modello Quill |
| L3 Engines | forecast, constraint, ottimizzazione, simulazione | AI/ML + optim | concurrent engine | 5 optimizer |
| L4 Scenario/version mgmt | versioni di piano, what-if, promozione | scenari | sandbox illimitati | scenari |
| L5 Process/workflow | i 5 review IBP, gate, stati, task, RACI | IBP workflow | playbook | workflow |
| L6 Collaboration/UX | workbench planner, commenti, assumption log | UI unica | UI unica | UI unica |
| L7 Analytics | KPI, forecast accuracy, exception-based alerts | dashboards | dashboards | dashboards |

**Il differenziatore vero non è nessun singolo layer: è che L2 è unico e condiviso.** Tutte e tre eliminano il "ogni funzione ha il suo foglio".

## 2. Dove sta Acmelift oggi (dal cervello)

**Processo** — ciclo mensile S&OP P/R/A/C su orizzonte 2 anni fiscali:
- P Preliminary (Sales) → R Requested (validazione Global Demand, gg 8-10) → A Allocated (Ops, vincolato, gg 10-15) → C Confirmed (validazione Supply, g 16) → ERP/MRP.
- Due gate Executive Board separati. Demand *unconstrained*, poi vincolata dalla capacità; il gap = opportunità persa.
- Scope annidati: WSC settimanale → S&OP mensile → Budget (nasce dal Cycle 9) → SEP/MTP 5 anni.

**Stack tecnico** — tre sistemi:
- **SAP S/4** = master data materiale (product division/class, assembly cluster, sales reporting unit).
- **Infor dEPM / CloudSuite** = DB di pianificazione OLAP. Star schema: dimensioni `DMANUFACT_KEY` (1.346), `DSALES_PRODUCT` (1.661), `DPLANT` (52), `DSALES_DIVISION` (62), `DVERSIONS` (466) + `DMEASURE_OPS`, TimeDate. Cubi `TSOP_DEMAND`, `TSOP_OPS`, `TWSC_PAR_CALWEEK`. Input via Application Studio; job numerati (2000 copy params, 3000 init istanza, 4000 transfer demand→ops); stati STAT_01/02/03.
- **Power BI** = layer di reporting su Stage Warehouse SQL, due modelli semantici, RLS da email.
- Ponte demand→supply: trasformazione `DSALES_PRODUCT → DMANUFACT_KEY` ("Ableitung Basic Assemblies") con clustering + offset temporale.

**Maturità misurata** (Gartner Score 2024, 25 rispondenti):
- Complessivo **2** vs benchmark manifatturiero **3-**.
- Processo S&OP **4-** (forte). **Planning technology, analytics e culture = 1** (il collo di bottiglia è la tecnologia, non il processo).
- `Manage Product Portfolio Planning` = **2**, `Plan New Products` = **1+**.
- `Align Plans to Business Objectives` = **3+** vs peer 3, ma con gap leader/team 4.00 vs 2.50.

**I due gap verso IBP** (Oliver Wight, corroborato da Gartner in modo indipendente):
1. **Portfolio Review assente** — nessun forum mensile che decide introduzioni/ritiri/riposizionamenti e li risorsa in un Project Master Plan. Il piano parte da un portafoglio *ricevuto*. Confermato dai numeri interni.
2. **Integrated Reconciliation assente come forum** — l'attività finanziaria è praticata (3+) ma non esiste la sessione pre-executive cross-funzionale. Il gap leader/team suggerisce che la riconciliazione avviene *dentro* la riunione executive. **Non risolto**: va chiesto a una persona.
3. **MBR parziale** — due gate separati su due piani a distanza di 15 giorni, non un unico forum su un unico set di piani.

## 3. Implicazione per il sistema da costruire

Il processo Acmelift è maturo (4-); la tecnologia è a 1. Quindi il sistema **non deve reinventare il ciclo P/R/A/C** — deve:
- **preservarlo** (P/R/A/C ≡ Demand Review + Supply Review, già allineati a IBP),
- **aggiungere i due layer mancanti** (Portfolio Review, Integrated Reconciliation) come oggetti software di prima classe,
- **sostituire il collo di bottiglia tecnologico**: scenari, ricalcolo, exception-based planning, financializzazione automatica del piano volumi.

Il modello Infor esistente (dimensioni + cubi) è il **candidato naturale per L2** e va rispettato, non buttato: è l'ontologia già concordata a livello globale.
