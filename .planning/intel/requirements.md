# Requisiti (PRD)

Fonte primaria: `docs/01-plan-m1.md` — tipo PRD, `precedence: 2` (per-manifest). Il documento porta
un header di supersessione parziale: **resta autorevole solo per** contesto di business, la misura
Gartner 2024, il programma a tre milestone M1/M2/M3, e le decisioni di architettura A1-A11 che
devono reggere M2/M3. Per il dettaglio di task, acceptance criteria e backlog di M1, l'autorità
passa a `docs/02-spec-m1-corrente.md` (SPEC, precedence 1) — vedi `constraints.md` per quel
contenuto e `INGEST-CONFLICTS.md` per la supersessione registrata come INFO.

## Contesto di business (autorevole da questo documento)

ACMELIFT ha un processo S&OP maturo (Gartner Score 2024, 25 rispondenti: **S&OP 4-**, **planning
technology/analytics/culture 1**, complessivo **2** contro benchmark manifatturiero **3-**) su una
tecnologia che non lo regge. Il ciclo mensile P/R/A/C gira su Infor dEPM, si alimenta da SAP S/4 e si
riporta in Power BI — funziona, ma manca ricalcolo immediato, scenari illimitati, baseline
statistica, vincoli come dati, eccezioni che risalgono da sole.

Due dei cinque review IBP mancano (confermato da Oliver Wight, Gartner e utente): **Portfolio
Review** assente, **Integrated Reconciliation** assente come forum (l'anchoring `3600` non è
reconciliation), **MBR** spezzato in due gate.

Cinque punti di semplificazione manuale emersi dall'utente (non dai documenti), motore delle
decisioni F1-F13 sotto: mapping planning-model↔manufacturing-key many-to-many trattato come
attributo singolo; stesso manufacturing key producibile in più plant trattato come singolo
`Targeted Plant`; percorsi produttivi multi-step (obbligatori e/o elettivi) non modellati;
ri-allocazione centrale sull'orderbook invisibile al sistema; domanda dipendente del semilavorato
calcolata in Excel con file che scrivono sul database.

Esito voluto: un sistema che preserva P/R/A/C, innesta i due review mancanti, automatizza i cinque
punti manuali, e apre la strada alla rete completa (M2/M3) senza doverlo rifare.

*(Dettaglio completo: source docs/01-plan-m1.md; sintesi comparativa delle piattaforme di
riferimento in `context.md`, fonte docs/00-research-brief.md.)*

## Programma — REQ-programma-milestone

source: docs/01-plan-m1.md | scope: programma

Tre milestone, ciascuna eseguibile e utilizzabile da sola:
- **M1 — Core + rete produttiva** (in corso): modello dati, motore concurrent, scenari,
  forecast+FVA, ciclo P/R/A/C con i 5 review, mapping N:N, routing multi-step, domanda dipendente,
  allocazione automatica su orderbook. È tutto il lavoro manuale che oggi si fa a mano.
- **M2 — Rete a monte**: dealer interni de-schiacciati, sell-in intercompany, stock di canale a
  partita doppia, nodi di capacità installazione (MCC + dealer interni).
- **M3 — Rete a valle**: componenti critici, fornitori interni come nodi con capacità,
  percentuali di double sourcing.

## Decisioni fissate (F1-F13) — requisiti vincolanti per M1

Ogni voce: id, decisione, conseguenza. source: docs/01-plan-m1.md per tutte.

- **REQ-F1** — La domanda si pianifica al modello commerciale; le opzioni non entrano nel piano di
  vendita ma rientrano dalla supply (la configurazione determina il routing): le opzioni servono
  come mix per l'allocazione, non come BOM.
- **REQ-F2** — La baseline statistica precompila il P (versione forecast distinta); l'FVA nasce per
  costruzione. Modellato come cambio di **modello dati**, non di reporting.
- **REQ-F3** — Nessuna soglia di eccezione documentata: soglie = dato configurabile, default
  dichiaratamente provvisori. Chiuso nello SPEC (2026-09-12): seed con ±20% w/w e tre livelli,
  marcati provvisori **nel dato** (`exception_rule.is_provisional`) — vedi `constraints.md`.
- **REQ-F4** — Seed sintetico ma isomorfo: nessun dato ACMELIFT reale nel repo.
- **REQ-F5** — Due forum board, nessun MBR unificato: MBR = forum unico di cui i due gate sono fasi.
- **REQ-F6** — Run = architettura + diagrammi + scheletro eseguibile: i documenti sono il
  deliverable primario, il codice li rende verificabili.
- **REQ-F7** — PM↔MK many-to-many, split a percentuali definite a priori + aggiustamento manuale
  del planner; tabella di mapping time-phased con override tracciato e distinguibile dal valore di
  regola. *(Nello SPEC: `item_link`, non `product_mapping` — vedi `constraints.md` D2.)*
  Acceptance: **AC4**.
- **REQ-F8** — Allocazione multi-plant: il sistema deve **proporla**, non registrare una decisione
  umana. Acceptance: **AC8**.
- **REQ-F9** — Il routing elettivo è guidato dalla configurazione venduta, letta dall'orderbook:
  serve un mix di configurazione nel piano supply, alimentato dall'orderbook reale. Acceptance:
  **AC7**. *(Vedi decisions.md D-006 per l'estensione: insieme di attributi, non singolo.)*
- **REQ-F10** — Il semi-finito ha domanda propria (domanda dipendente), offset uniforme a 2 mesi
  (parametro unico configurabile, non una matrice per lane). Acceptance: **AC6**, **AC9**. Chiuso
  nello SPEC come offset **fisso** da `routing.lead_offset_months` — vedi `constraints.md` D2/T6.c.
- **REQ-F11** — L'unità pianificata restano le vendite esterne; la richiesta dei dealer interni è
  sales intercompany + richiesta aggiuntiva della region, nello stesso mese — nessun doppio
  conteggio. Scope: **M2**.
- **REQ-F12** — Installazioni: mounting competence center e dealer interni sono nodi di capacità con
  un limite. Scope: **M2**.
- **REQ-F13** — Fornitori interni = nodi con capacità propria, non sorgenti infinite. Scope: **M3**.

## Architettura che deve reggere M2/M3 (A1-A11) — autorevole da questo documento

source: docs/01-plan-m1.md per tutte. Queste non sono implementate ora ma vincolano le scelte di M1.

- **REQ-A1** — Il vocabolario ACMELIFT (`DSALES_PRODUCT → DMANUFACT_KEY → plant slot`) mappa 1:1 su
  planning bill/ATO model → planning config → risorsa RCCP `SLOT_POOL`. Va nominato e reso
  configurabile, non reinventato.
- **REQ-A2** — Rete produttiva modellata a relazioni (item_link/production_eligibility/routing/
  bill_of_resource), non ad attributi. Slot-equivalence factor per manufacturing key (es. ×2 di
  Westvale come `factor=2`, non literal). *(Realizzato nello SPEC come D2 — vedi `constraints.md`.)*
- **REQ-A3** — L'allocatore si innesta fra R e A, all'handover a Operations del giorno 10; due
  orizzonti (dentro/oltre l'orderbook, quest'ultimo su mix osservato a consuntivo);
  `AllocationStrategy` resta un'interfaccia sostituibile con un solver esterno (fuori scope M1).
- **REQ-A4** — Semantic layer: star schema dEPM rispecchiato 1:1 + **una** tabella di archi tipizzati
  `edge`. M2/M3 aggiungono nodi (dealer, importatore, installatore, fornitore) senza migrazioni.
  Corollario: le regole di capacità escono dal codice e diventano master data (**AC2**).
- **REQ-A5** — Motore concurrent planning: DAG dichiarativo con `graphlib`, altezza + min-heap,
  early cutoff sull'hash, pull-based sui nodi osservati, granularità (misura, partizione) non
  cella. Test cardine: incrementale ≡ ricalcolo completo (**AC10**).
- **REQ-A6** — Persistenza DuckDB + Polars + Arrow, in-process single-user per M1; enterprise
  (multi-utente, locking a cella, versioning nativo, SSO/RLS, orchestratore) è fuori scope M1 ma il
  modello di dominio/stati/interfacce deve sopravvivere alla migrazione.
- **REQ-A7** — Scenari come event log → overlay → layer stack (`edits` append-only, tombstone
  esplicito a tre stati mai-NULL, promozione come three-way merge che materializza nuova istanza
  `DVERSIONS`, annidamento max 2-3 livelli). **Nota: ADR-001 R-001 (vedi `decisions.md`) estende
  questo requisito con un modello a tronco-e-rami — WARNING in `INGEST-CONFLICTS.md`.**
- **REQ-A8** — Forecast statistico + FVA: pool di modelli selezionato per MASE, `forecast_snapshot`
  a lag costante nello schema dal giorno 1, riconciliazione `MinTrace` con `BottomUp` come
  confronto. FVA negativo allo step planner è atteso, non un difetto.
- **REQ-A9** — I due review mancanti (Portfolio Review, Integrated Reconciliation) come entità di
  prima classe con gate/agenda/decisioni; il carry-forward `3600` resta e viene nominato
  (`confirm_back_to_sales`), distinto dalla Reconciliation.
- **REQ-A10** — Confine di sistema: SAP S/4 consumato read-only; Infor dEPM riceve il piano promosso
  come **file**; Power BI non toccato, solo viste; ERP/MRP fuori confine. Acceptance: **AC24**.
- **REQ-A11** — Architettura M2 (rete a monte: dealer/importatore/installatore/MCC, stock di canale
  a partita doppia con invariante somma-zero) e M3 (rete a valle: componenti critici, fornitori
  interni con capacità, `sourcing_split` per double sourcing) — non implementata in M1, ma M1 non
  deve richiedere di essere rifatto per accoglierla.

## Acceptance criteria — stato canonico

Gli **AC1-AC26** sono stati approvati in questo documento (PRD) ma il **testo corrente,
la spunta di stato e le estensioni AC27-AC31 sono autorevoli in `docs/02-spec-m1-corrente.md`**
(SPEC, precedence 1) — vedi `constraints.md` per l'elenco completo con stato `[x]`/`[ ]` e le cinque
estensioni. Unica differenza di testo registrata: **AC6** nel PRD portava un condizionale
sull'offset di domanda dipendente; lo SPEC lo rimuove (F10 chiusa: offset fisso a 2 mesi). Questa è
una supersessione dichiarata, non una contraddizione — vedi INFO in `INGEST-CONFLICTS.md`.

## Backlog — puntatore

Il backlog a 13 task + 6 pacchetti preparatori, con owner/path/dipendenze/stato, è autorevole in
`docs/02-spec-m1-corrente.md` (SPEC). Lo stato di consegna effettivo (T1-T4 fatti, T5-T13 pendenti)
è registrato in `context.md` (source: docs/03-consegna-t1-t4.md). Non ripianificare qui: vedi
entrambi i file.
