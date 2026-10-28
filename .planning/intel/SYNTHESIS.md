# Synthesis — IBP Platform doc ingest

Modalità: `new` (nessun `.planning/` preesistente). Precedenza applicata: per-doc manifest override
(ADR-001=0, SPEC=1, PRD=2, DOC=3/4/5), coerente con il default ADR>SPEC>PRD>DOC.

## Documenti sintetizzati: 6

- **ADR** (1): `docs/ADR-001-decisioni-dominio.md` — LOCKED, precedence 0, 2026-09-19.
- **SPEC** (1): `docs/02-spec-m1-corrente.md` — precedence 1, rigenerato 2026-09-12.
- **PRD** (1): `docs/01-plan-m1.md` — precedence 2, parzialmente superseded (dichiarato).
- **DOC** (3): `docs/00-research-brief.md` (precedence 3), `docs/03-consegna-t1-t4.md`
  (precedence 4), `README.md` (precedence 5).

Tutte le classificazioni sono a confidenza `high`; nessun documento `UNKNOWN`.

## Decisioni locked: 9 (da 1 fonte ADR)

D-001..D-008 + R-001, tutte `locked: true`, in `.planning/intel/decisions.md`. Una di queste
(R-001) apre una tensione di design non auto-risolvibile — vedi Conflitti sotto. Una (D-001) portava
un'ambiguità esplicita ("DA CONFERMARE") lasciata dalla fonte stessa.

## Requisiti estratti: 24 (dalla PRD)

13 decisioni fissate (`REQ-F1`..`REQ-F13`) + 11 vincoli di architettura per M2/M3 (`REQ-A1`..
`REQ-A11`), in `.planning/intel/requirements.md`. Il dettaglio di acceptance criteria (AC1-AC31) e
backlog è autorevole nello SPEC — vedi `constraints.md`.

## Vincoli estratti: 7 design sections + 31 acceptance criteria + backlog a 19 righe (dallo SPEC)

D1-D7 (schema/protocol/nfr) + AC1-AC31 con stato corrente (`[x]`/`[ ]`) + tabella backlog 13 task
canonici + 6 pacchetti preparatori (T5.a-c, T6.0, T6.a-d, T10.0, T10.1, T11.0-2), in
`.planning/intel/constraints.md`.

## Topic di contesto: 3 (dai DOC)

- **Stato di consegna T1-T4 / debito tecnico** (source: `docs/03-consegna-t1-t4.md`) — **leggere
  per primo**: T1-T4 done e verdi (commit `d54a453`, 176→187 test), T5-T13 pendenti, tutto il
  debito tecnico già convertito in pacchetti di backlog numerati nello SPEC. Il roadmap non deve
  ripianificare T1-T4.
- **Confronto piattaforme di riferimento e stato Acmelift** (source: `docs/00-research-brief.md`).
- **Setup locale e ambiente Windows** (source: `README.md`).

Tutto in `.planning/intel/context.md`.

## Rilevamento cicli

Rilevato un ciclo di cross-reference (01-plan-m1.md ↔ 02-spec-m1-corrente.md, esteso a un
triangolo con README.md) — classificato **benigno**: corrisponde a riferimenti di supersessione
dichiarati esplicitamente da entrambi i documenti, non a una dipendenza circolare che renda la
sintesi indeterminata. Sintesi proceduta su tutti i 6 documenti. Dettaglio in INFO nel report
conflitti.

## Conflitti: 0 blocker, 2 warning, 8 auto-risolti

- **0 BLOCKER** — nessuna contraddizione LOCKED-vs-LOCKED, nessun UNKNOWN a bassa confidenza,
  nessun ciclo pericoloso.
- **1 WARNING** (richiede decisione in fase di roadmap):
  1. Modello scenari a tronco-e-rami (ADR-001 R-001) vs modello branch-di-versione-base (SPEC D3,
     già implementato in T4) — l'ADR stesso la definisce estensione da pianificare, tocca T4/T11/T12.
- **9 INFO** (auto-risolti per precedenza o corroborati, trasparenza): supersessione SPEC>PRD su
  task/AC/backlog; AC6 senza condizionale; ADR D-007/D-008/D-006 chiudono le open question SPEC
  1/4/3 (quest'ultima con implicazione di design su `routing.variant_key`); ADR D-005 corrobora
  il design di back-allocation SPEC; ciclo di cross-ref classificato benigno; ADR D-003/D-004
  toccano master data T1 già consegnato, non verificabile in questo ingest.

Dettaglio completo: `.planning/INGEST-CONFLICTS.md`.

## File prodotti

- `.planning/intel/decisions.md` — ADR-001, D-001..D-008, R-001.
- `.planning/intel/requirements.md` — REQ-F1..F13, REQ-A1..A11, contesto di business, programma.
- `.planning/intel/constraints.md` — D1-D7, AC1-AC31, backlog 13 task + 6 pacchetti.
- `.planning/intel/context.md` — stato di consegna, research brief, setup/ambiente.
- `.planning/INGEST-CONFLICTS.md` — report conflitti a tre bucket.
