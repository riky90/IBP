# Project State

> **Nota sulla lingua.** Contenuti in italiano. Restano in inglese, verbatim, le intestazioni e i
> nomi di campo che i workflow GSD leggono e riscrivono (`## Current Position`, `Phase:`, `Plan:`,
> `Status:`, `Last activity:`, `Progress:`, `## Accumulated Context`, `### Decisions`,
> `### Blockers/Concerns`, `## Session Continuity`). Sono identificatori, non prosa.

## Project Reference

See: `.planning/PROJECT.md` (aggiornato 2026-09-19)

**Core value:** Il planner cambia un numero e vede subito, sull'intero piano, cosa ne consegue — su uno scenario che può confrontare e promuovere senza perdere né la base né la tracciabilità.
**Current focus:** Phase 6 — Grana region nel motore (T6.0)

## Current Position

Phase: 6 of 16 (Grana region nel motore — T6.0)
Plan: 0 of 5 eseguiti (06-01 … 06-05, in 4 wave)
Status: Planned — pronta per `/gsd:execute-phase 6`
Last activity: 2026-09-19 — Pianificata la Phase 6: 5 piani, plan-checker PASS con una riserva chiusa (ANY_SCOPE marcato provvisorio)

Progress: [██▌░░░░░░░] 25% (4 fasi su 16 complete)

## Performance Metrics

**Velocità:**
- Piani completati sotto GSD: 0
- Durata media: n/d
- Tempo di esecuzione totale: n/d

**Per fase:**

| Phase | Plans | Totale | Media/piano |
|---|---|---|---|
| 1-4 (pre-GSD, `/software-house`) | n/d | n/d | n/d |

**Trend recente:**
- Nessun piano GSD completato: la baseline si stabilisce con la Phase 5.
- Riferimento pre-GSD: T1-T4 consegnati fra il 2026-09-10 e il 2026-09-12, suite a 187 test.

*Aggiornata dopo ogni completamento di piano.*

## Accumulated Context

### Decisions

Registro completo in `PROJECT.md` (blocco `<decisions>` ADR-001 + tabella Decisioni chiave).
Decisioni che toccano il lavoro imminente:

- **D-001** (Phase 9): capacità a Northfield = vincolo **doppio**, slot **E** ore, controlli indipendenti; due modi di esaurimento da testare separatamente.
- **D-006** (Phase 8): routing elettivo NAM su un **insieme** aperto di attributi; tensione da risolvere con `routing.variant_key`, disegnata come chiave singola.
- **D-007** (Phase 9): `Average Assembly Hours` è popolato ma stale — input sì, riferimento di test no; da revisionare prima del go-live.
- **D-008** (Phase 11): job `3000` = carry-forward **alternato** preliminary↔requested.
- **R-001** (Phase 13): Step A dentro M1 e additivo; Step B rinviato a M2 perché collide con `DVERSIONS.version_name UNIQUE`, letto come stringa dalle misure DAX.
- **Roadmap** (Phase 6): T6.0 resta una fase isolata; il suo gate d'uscita è **AC10 di nuovo verde**.

### Pending Todos

Nessuno.

### Blockers/Concerns

- **Phase 5** — il percorso di forecasting non è **mai stato eseguito**: il pin `statsforecast==2.1.1` è risolvibile e wheel-installabile (verificato), ma l'ordine di import OpenMP va provato a runtime. Un errore lì è un SIGSEGV senza traceback, non un'eccezione.
- **Phase 5** — pool di modelli con storia corta: il seed cappa i fatti a 4 cicli chiusi + corrente, l'ordine ARIMA è appena identificabile. Misurare la copertura **prima** di scegliere il pool.
- **Phase 6** — T6.0 riapre un motore chiuso e verde, e il difetto è più profondo della sua descrizione breve: la region è già persa nell'aggregazione a monte (`engine.py:347-366`, `492-499`). Il fix non è locale a `_eligible_plant_for`.
- **Phase 8** — `routing.variant_key` (chiave singola opzionale) contro D-006 (insieme estendibile senza modifiche di schema): verificare esplicitamente in T6.d, non assumere.
- **Phase 14** — se la latenza per richiesta di ricalcolo supera 200ms, la partizione del DAG per product family torna sul tavolo.
- **Phase 15** — `UI-SPEC.md` è prerequisito dichiarato: produrlo con `/gsd:ui-phase` prima di `/gsd:plan-phase 15`.
- **Trasversale** — la suite richiede `data/ibp.duckdb` prodotto da `python db/build_db.py`; su checkout pulito i test che dipendono dal DB reale vengono skippati, non falliti.

## Deferred Items

| Categoria | Elemento | Stato | Differito il |
|---|---|---|---|
| Scenari | **R-001 Step B** — grana piena di `overlay`/`edits`, `promote()` come spostamento di puntatore, risoluzione ricorsiva fino a root esplicita | Rinviato a M2 (collide con `version_name UNIQUE` / DAX Power BI) | 2026-09-19 |
| Rete a monte | REQ-F11, REQ-F12, stock di canale a partita doppia | Scope M2 | 2026-09-19 |
| Rete a valle | REQ-F13, componenti critici, `sourcing_split` | Scope M3 | 2026-09-19 |
| Motore | Partizione del DAG per product family | Solo se la Phase 14 misura >200ms | 2026-09-19 |
| Piattaforma | Multi-utente enterprise (locking a cella, SSO/RLS, orchestratore) e solver esterno | Fuori scope M1 | 2026-09-19 |

## Session Continuity

Last session: 2026-09-19
Stopped at: Creazione di `PROJECT.md`, `REQUIREMENTS.md`, `ROADMAP.md`, `STATE.md` dopo l'ingest documentale e la mappatura del codebase — migrazione da `/software-house` (run `20260910-0830-ibp-platform`, commit `d54a453`) a GSD.
Resume file: None
Prossimo passo: `/gsd:plan-phase 5`
