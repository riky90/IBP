# IBP M1 — domande aperte per Mario

Raccolta al 2026-10-12 da `concept/CONCEPT-ibp-m1.md` (rev 9.9.1), `spec/SPEC-ibp-m1-ux.md` e
`spec/SPEC-ibp-m1-master-data.md`. Nessuna blocca il pilota M1: ognuna ha un default **[AD]**
su cui il progetto gira finché non rispondi.

Come compilare: per ogni voce spunta `accetto il default` **oppure** scrivi dopo `Risposta:`.
Lascia vuoto ciò che non sai: resta il default. Le note tornano come input alla prossima revisione.

---

## A. Azioni esterne (servono dati o persone fuori dal tool)

### U1 — Order book di metà mese con configurazione per riga d'ordine
Serve un feed del portafoglio ordini a metà mese, a LE × regione × PM × mese, con le opzioni di
configurazione di ogni riga. Senza: la Planning BOM gira solo su rate manuali ("rates only") fino a M2.
- [x] accetto il default (niente feed in M1)
- Chi/quando può fornirlo:
- Note:

### U4 — Lista frozen zone di Operations
Lunghezza della frozen zone per ogni MK (per plant dove differisce). Vedi anche MD-Q-7.
- [ x] richiesta inviata a Operations
- Risposta / file:
- Note:

### U5 — Estrazioni ERP (IT)
Quale sistema, quali misure, layout, grana, chiavi, frequenza, owner. Non serve per il pilota.
- Referente IT:
- Note: da definire

### U6 — Snowflake (IT)
Quali oggetti, grana, chiavi, refresh, owner, accesso da tool Windows che deve funzionare offline.
Non serve per il pilota.
- Referente IT:
- Note: da definire

### U7 — Login e utenti
Fonte identità (directory aziendale, gruppo `SG-APP-IBP`, o account locali del tool), host Windows
che fa girare il server, lista utenti con ruolo e scope. Default: account locali + lista inserita dal data manager.
- [x ] accetto il default
- Risposta:
- Note:

### U9 — Contenuto della Planning BOM e owner
Per ogni MK: routing group, component group, componenti, rate iniziali, offset; quali phantom SAP
si usano. Owner di default: data manager. (Vedi anche MD-Q-21, UX-Q-24.)
- [x ] accetto owner = data manager
- Chi fornisce i contenuti:
- Note:

### U10 — Export `OrderBook_units` (cubo ops) a grana fatto
Serve per capire da dove arriva. Può farlo l'orchestratore se gli dai accesso al modello Operations.
- [ ] lo faccio io / [ ] fallo tu con il PBIP in `IBP/`
- Note: ciao si fallo fare all'orchestratore, gli do accesso al modello operations, anche se ad oggi orderbook del modello ops e' uguale a orderbook sales. non abbiamo un OpsOrderbook_units e' uno dei pain point.

---

## B. Domande UX (`SPEC-ibp-m1-ux.md`, § Open questions)

| # | Domanda (breve) | Default [AD] | Accetto default | Risposta / Note |
|---|---|---|---|---|
| UX-Q-1 | Lingua interfaccia: inglese, italiano o entrambe? |answer: Inglese | [ x] | | 
| UX-Q-3 | Scenario condiviso, il piano comune cambia prima della conferma: rebase con replay delle modifiche, o scarto e ricreazione? | answer:Rebase da S-21 | [ x] | |
| UX-Q-4 | Chi imposta le soglie (gap agenda PR-05, alert PR-06) e dove? |answer: Sola lettura su S-29/S-34 | [ x] | |
| UX-Q-5 | Cosa si rivede nella Portfolio Review (AC21)? | answer:SOP/EOP + Region Model Assignment del ciclo | [x ] |piu nuovi modelli da creare e inserire nel piano |
| UX-Q-6 | Un planner può ritirare uno scenario condiviso a Draft? | answer:No | [ x] | |
| UX-Q-7 | Gap a valore: quale base prezzo e quale valuta? | —answer: Valuta Locale che sara da trasformare in euro con degli FX rate aggiornati mensilente dal data manager| [ ] | |
| UX-Q-8 | Quali diagrammi offre S-33 oltre ai quattro attuali? |answer: I quattro attuali | [ x] | |
| UX-Q-9 | Cartella e naming del file di handoff dEPM |answer: — | [ x] | |
| UX-Q-13 | Own Region = società del gruppo stessa regione, Group = altre regioni. Corretto? | answer:Sì | [ x] | |
| UX-Q-14 | Orderbook: la quinta colonna è il Total calcolato? |answer:Sì | [x ] | |
| UX-Q-15 | Primo salvataggio in maschera: crea in automatico "Working plan · utente" o chiede un nome? | answer:Creazione automatica | [x ] | |
| UX-Q-16 | Alert: basta "Mark seen", o serve un atto esplicito "resolved"? Da chi? | "Mark seen";answer: chiusura decisa dall'engine | [ x] | |
| UX-Q-17 | Utente con più ruoli: cambio ruolo senza logout? | answer:cambio ruolo senza logout | [x ] | |
| UX-Q-18 | Data della review mensile: la cambia l'Approver su S-29, o è anagrafica calendario (S-30o)? | answer:Approver su S-29 | [ x] | |
| UX-Q-20 | Livello categoria dell'Order Intake forecast: product line "(E)" o product division? | answer: possibilita di scegliere se fare product line, product family o planning model da parte del data manager| [ x] | |
| UX-Q-21 | Pop-up "What goes where" su S-06: prima visita, una volta per ciclo, o mai automatico? | answer:una volta per ciclo| [ x] | |
| UX-Q-22 | Fabbisogno componenti: 1 decimale o unità intere? | answer:1 decimale | [x ] | |
| UX-Q-23 | Tab Planning BOM = S-30t, stessi nomi campo nelle due spec | answer:Sì | [x ] | |
| UX-Q-24 | Rate Planning BOM: solo data manager, o anche Operations / product management? | answer: data manager + operations| [x ] | |
| UX-Q-25 | S-30t descritta diversamente nelle due spec: vince master-data? | answer:Sì | [x ] | |

---

## C. Domande master data (`SPEC-ibp-m1-master-data.md`, § 13)

| # | Domanda (breve) | Default [AD] | Accetto default | Risposta / Note |
|---|---|---|---|---|
| MD-Q-1 | Cos'è un "cluster" nella maschera Ops: membri MK "(E)", Assembly Cluster (78) o Manufacturing Category (81)? | answer: si chiama assembly cluster sul power bi mentre manufacturing category in INFOR ma sono la stessa cosa e sono quello che chiamiamo cluster | [ x | |
| MD-Q-2 | A che livello di regione si inseriscono i dati sales: Region (7), nodo L-2 o paese (L-4)? | Membri marcati "planning region" dovrebbe essere l2| [x] | |
| MD-Q-3 | Significato delle lettere `Plant Activity` (F, P, A, I) | answer:Solo testo in lettura | [x ] | |
| MD-Q-4 | Dove vivono oggi Region Model Assignment e SOP/EOP? Esportabili? | Seed da coppie PM × regione; SOP/EOP vuoti |answer: ce un cubo aprameters in cui ho se un modello e' assegnato a una regione si/no e start of production end of production [x ] | |
| MD-Q-5 | Seed: viste DWH o export dEPM come fonte primaria? | answer: DWH primaria | [x] | |
| MD-Q-6 | Serve uno scope per Product Division (come la RLS Power BI)? | answer: si serve [ x] | |
| MD-Q-7 | Frozen zone (U4): per MK o per MK × plant? | answer: Per MK e plant| [ ] | |
| MD-Q-8 | I planner Ops possono modificare capacità ore e parametri dei propri plant? | answer: Solo data manager e operations| [x ] | |
| MD-Q-9 | Quali plant sono terzisti? | External = terzista, altri = propri |answer:si esatto [ x] | |
| MD-Q-10 | Link MK → plant seminato dallo storico Confirmed? | answer: Sì, una tantum e modificabile da certi ruoli lcome global supply planner e datamanger| [x ] | |
| MD-Q-11 | Quali legal entity sono attive per la pianificazione? | answer: Quelle con fatti di piano | [ x] | |
| MD-Q-12 | Serve la mappa settimane (CW53) in M1? | answer:si, prevederei un calendatio compelto, giorno, mese anno.| [ ] | |
| MD-Q-13 | Servono ordine di visualizzazione ed etichette tedesche? | answer: Ordine sì, tedesco no | [ x] | |
| MD-Q-14 | Flag dealer: company view (16) o dEPM (12)? | answer: Company view | [x ] | |
| MD-Q-15 | Riallineare la UX spec al master data (S-30, FL-16, ruoli) | answer: Sì — è lavoro già in coda | [ x] | |
| MD-Q-16 | Grana capacità ore: plant × MK, plant × cluster o entrambi? | answer:Plant ×  cluster | [ x] | |
| MD-Q-17 | Linee: 14 linee di pianificazione + 5 altri valori? | answer: Sì | [x ] | |
| MD-Q-18 | Codice dei componenti: materiale SAP, codice product management o libero? |answer: Codice da import; SAP come alias | [ x] | |
| MD-Q-19 | Tipi componente part / assembly / feature; i colori sono componenti? | answer: colore e' una feature | [x ] | |
| MD-Q-20 | Two-step `-BA` (Northfield → Niagara): chiave semilavorato + plant di finitura? | answer: Sì | x ] | |
| MD-Q-21 | Chi fornisce la Planning BOM: un file globale o uno per product line? | answer: Data manager, un file globale | [x ] | |

---

## D. Già decise, solo da applicare (nessuna azione tua)

- **OQ-28** → merge dei PM con suffisso plant + regola di sourcing regionale. Da scrivere nella rev 9.9.2.
- **OQ-29** → il filtro sales usa l'Assembly Cluster. Da scrivere nella rev 9.9.2.

---

## E. Nuove domande dalla rev 9.9.2 (aggiunte il 2026-10-12)

Testo completo in `concept/CONCEPT-ibp-m1.md`, § "Still open". Come sopra: spunta il default o scrivi.

| # | Domanda (breve) | Default [AD] | Accetto default | Risposta / Note |
|---|---|---|---|---|
| OQ-30 | Gap a valore: quale prezzo moltiplica le unità mancanti? | Prezzo medio di vendita dEPM per planning model (cubo `TSOP_PAR_DEMAND_PRICES`), in valuta locale. Finché il cubo non è esportato si mostrano solo le unità | Answer prevedere una tabella in cui inserire i prezzi medi per  modello o product class (tipo kbc 10-20tm) in valuta locale e poi una tabella fx rate da aggironare mensilemnte per la trasformazione in euro.+ [ ] | |
| OQ-31 | Order Intake: cosa vuol dire "product family"? Product Category (48), Product Class (106) o `WSC Planning Family` (49)? | answer product class| [ ] | |
| OQ-32 | Anche la capacità a slot di produzione passa a plant × cluster? | answer passa a plant x cluster| [ ] | |
| OQ-33 | Regole di sourcing regionale: (a) una routing di configurazione (es. colore fatto da un solo plant) vince sulla regola; (b) senza quote, il plant preferito prende il 100 % e gli altri sono alternative proposte se è pieno; (c) un plant fuori lista è accettato e segnalato, mai rifiutato; (d) i PM `-BA` si fondono nel modello base (alias = base + Niagara), i `-BR` restano separati; (e) le regole si precaricano solo dove lo storico nomina un plant; le altre (es. LATAM, APAC) le inserisce il global supply planner o il data manager | Tutti e cinque i punti come scritti | answer: di base i -BA rimangono per Northfield, il modello base se la richiesta arriva da NAM vanno su NIAGARE, i modelli -BR perdono suffisso, se la richiesta arriva da LATAM vanno su Pinecrest do sul. Poi siccome il routing non sara definito all'inizio il planner puo spostare richiesta da un plant a uno gemello in base a quello che vede in orderbook, oppure lo fa il sistema in automatico quando carichiamo l'orderbook, se il cleinte e' americano e il palnt e' northfield si riduce la richiesta su niagara. se hai dubbi o altre cose da chairire per gestire al emglio i vari casi segnalati dimmi.[ ] | |
| OQ-34 | Global supply planner: modifica anche le regole di sourcing, può forzare plant e accettare proposte di allocazione su tutti i plant, prepara la parte plant dei nuovi modelli, legge tutto; non tocca vendite, Confirmed, capacità e frozen zone. "Operations" = l'ops planner del plant, sui suoi plant | answe: global supply palnner puo moddificare anche la conferma, la capacita e frozen zione | [ ] | |

### U11 — Export del cubo "parameters" di dEPM (nuova azione tua)
Per ogni modello: assegnazione regione sì/no e SOP / EOP. Serve per caricare ITEM × REGION. Se OQ-30
resta al default, esporta anche il cubo dei prezzi medi `TSOP_PAR_DEMAND_PRICES`.
- [ ] fatto — file:
- Note:
