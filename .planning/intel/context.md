# Contesto (DOC)

Note correnti per argomento, da documenti classificati DOC. Ogni sezione riporta la fonte.

---

## Stato di consegna — T1-T4 fatti, T5-T13 pendenti (LEGGERE PRIMA DI PIANIFICARE)

source: docs/03-consegna-t1-t4.md | tipo: registro di consegna del run software-house
`20260910-0830-ibp-platform` (non una specifica — i requisiti stanno in `constraints.md`/
`requirements.md`)

**Questo è lo stato di build reale. Il roadmap a valle non deve ripianificare lavoro già fatto e
verde.** Commit di riferimento: `d54a453` ("Commit iniziale: IBP M1 — T1-T4 completi, T5
sbloccato"). Suite al termine di T4: **176 test passed** (poi 187 dopo ulteriori fix, per numeri
puntuali vedi sotto).

### Fatto (done, verificato)

- **T1 — schema+seed** (chiuso 2026-09-10, riaperto due volte: extra `[forecast]`, digest
  `base_snapshot_id`). `python db/build_db.py` idempotente su 3 run consecutivi (hash di contenuto
  per tabella); `_validate()` fa fallire il build su invariante violata. Tre scelte da conoscere a
  valle: volume fatti cappato (4 cicli chiusi + corrente + `SOP_BP_2027` — tocca T5); magic number
  di capacità spostati in `db/seed/data/*.json` (l'unico `8` residuo nei `.py` è
  `encoding="utf-8"`, escluso dal test anti-literal); `numpy` deliberatamente non in dipendenze.
- **T2 — dominio+semantic layer** (chiuso 2026-09-11, critic PASS al giro 2). `ibp/` — 17 moduli,
  ~1.124 righe. sh-tester GREEN, **61 test**. Due giri di critic hanno chiuso difetti veri:
  `ROW_NUMBER()` che trascinava righe stale (quote misurate al 145%), `neighbors()` case-sensitive
  su `rel_type`, guardia `as_of` promettente uno stato storico che il grafo non può dare — poi, al
  giro 2, una regressione della guardia stessa (`Decimal` vs `float`, guardia troppo ampia su date
  future, path `rel_type=None` scoperto). Verdetto finale: PASS, idoneo a reggere T3/T4.
- **T3 — motore concurrent** (`ibp/engine/`). AC10 regge sotto stress mirato (chiavi nuove oltre
  l'orizzonte, division assente, 40 batch casuali). Difetti chiusi: batch non atomico (un edit
  malformato bloccava il motore per sempre — avrebbe brickato T10 via HTTP); `confirmed_production`
  mancante dal DAG dichiarato; `CutoffStats.absent` (2.352 falsi cutoff erano sparsità del rate
  card); rumore floating-point eliminato alla sorgente (asserzioni `==`, non `math.isclose`).
- **T4 — scenari** (`ibp/scenario/`). Due difetti da tester, cinque da critic, tutti chiusi:
  non-determinismo in lettura/scrittura (`ORDER BY` + somma Python invece di `SUM GROUP BY`
  parallelo); misure non additive sommate erroneamente (ora `NonAdditiveMeasureError`); fuga fra
  scenari su basi diverse (AC15, ora `MismatchedBaseVersionError`/`CellVersionMismatchError`);
  `side`/`status` non verificati alla promozione (ora `SideMismatchError`). **Verifiche finali dei
  critic lanciate ma non ancora rientrate a fine sessione** (2026-09-11) — da leggere a inizio
  sessione successiva.

Suite complessiva dopo T1-T4: **176 passed, 0 failed** (`python -m pytest -q`), poi 187 dopo la
chiusura T1-T4 (vedi header SPEC).

### Pendente (non ancora iniziato)

- **T5** forecast+FVA — sbloccato (la diagnosi "serve MSVC" era sbagliata), prossimo da fare.
- **T6** rete produttiva, **T7** capacità+allocatore, **T8** processo, **T9** adapter+viste — wave 3.
- **T10** API — wave 4.
- **T11** workbench — wave 5, richiede `UI-SPEC.md` via `/gsd-ui-phase` prima di iniziare.
- **T12** CLI+demo — wave 5.
- **T13** docs — wave 6.

### Debito tecnico aperto (fonte di questo documento) → convertito in backlog nello SPEC

Ogni voce qui sotto è stata trasformata in un pacchetto di piano esplicito e numerato nello SPEC
(`docs/02-spec-m1-corrente.md`) — vedi `constraints.md` per i dettagli operativi:

- `db/seed/scenario.py` da rigenerare: formato `base_snapshot_id` del seed diverso da quello di
  `branch()`; AC16 tollerante al formato, scenari del seed si promuovono senza verifica reale della
  base (impatta la demo T12). → **chiuso a terra in T1 il 2026-09-12** (digest via
  `_stamp_base_snapshots`, vedi `constraints.md` D3).
- T5 bloccato su `statsforecast` → **richiuso come falso allarme** nello SPEC (D5): non serve MSVC,
  serve solo la versione corretta del pacchetto.
- Costo di costruzione `RecalcEngine` (63-86s, query N+1) → pacchetto **T10.0**.
- `_eligible_plant_for` cachea per `manufact_key` ignorando `region_scope` → pacchetto **T6.0**
  (prerequisito bloccante di T6/T7).
- Guardia `as_of` di `neighbors()` troppo larga per node type → debito noto, non ancora un pacchetto
  numerato a sé; menzionato nelle note di T2 e T6.0 nello SPEC.
- `datetime.datetime` come `as_of` solleva `TypeError` → debito noto, stessa nota.
- `tests/test_semantic_ac2_master_data.py:29` non include `ibp/network/` nella root list → da
  correggere quando T6 scrive in quella directory.
- `tests/conftest.py:31` — fallimento T1 pre-`data/` indistinguibile da checkout pulito.
- Provenienza riga promossa non tracciata → pacchetti **T11.1** (schema) + **T11.2** (scrittura).
- Transazioni: `BEGIN TRANSACTION` nudo negli helper di `ibp/scenario/` → pacchetto **T10.1**
  (prerequisito bloccante di T10).
- `docs/01-plan-m1.md` obsoleto su modello dati (`DSALES_PRODUCT`/`DMANUFACT_KEY`/`product_mapping`
  eliminati da T1) e numerazione task → **motivo diretto della rigenerazione** che ha prodotto
  `docs/02-spec-m1-corrente.md`.

### Sessione 2026-09-11 — nota organizzativa

`concept-forge` generato con `agent-factory` (4 agenti: `concept-investigator`, `concept-architect`,
`concept-critic`, `concept-diagrammer`), junction su `IBP/.claude/skills/concept-forge`. Non
impatta i requisiti M1.

---

## Confronto piattaforme di riferimento e stato Acmelift (research)

source: docs/00-research-brief.md | data ricerca: 2026-09-10

Confronto o9 (Digital Brain / Enterprise Knowledge Graph), Kinaxis Maestro (concurrent planning,
scenari illimitati, "like a version control system for data"), DELMIA Quintiq (motore di
ottimizzazione multi-tecnologia guidato da Quill). Pattern architetturale condiviso in 7 layer
(Integration → Semantic model → Engines → Scenario/version mgmt → Process/workflow →
Collaboration/UX → Analytics); il differenziatore comune è un livello semantico (L2) **unico e
condiviso** fra tutte le app.

Stato Acmelift misurato: ciclo P/R/A/C mensile su Infor dEPM (alimentato da SAP S/4, riportato in
Power BI); Gartner Score 2024 complessivo **2** vs benchmark **3-**; processo **4-** (forte),
tecnologia/analytics/cultura **1** (collo di bottiglia). Due gap IBP confermati indipendentemente da
Oliver Wight e Gartner: Portfolio Review assente, Integrated Reconciliation assente come forum
(l'attività finanziaria esiste al 3+ ma non la sessione cross-funzionale pre-executive — "non
risolto: va chiesto a una persona"), MBR spezzato in due gate a 15 giorni di distanza.

Implicazione dichiarata per il sistema da costruire: non reinventare P/R/A/C (è maturo), preservarlo
e aggiungere i due layer IBP mancanti come oggetti software di prima classe, sostituire il collo di
bottiglia tecnologico. Il modello Infor esistente resta il candidato naturale per il livello
semantico (L2) — non va buttato, è l'ontologia già concordata globalmente.

*(Questo research brief precede sia il PRD sia lo SPEC; il suo contenuto è già incorporato nella
sezione "Contesto di business" di `requirements.md`. Qui resta per traccia/provenienza.)*

---

## Setup locale e ambiente Windows (README)

source: README.md | tipo: DOC (setup + gotcha, non specifica — i vincoli formali equivalenti sono in
`constraints.md` D7, questa sezione è la versione narrativa/operativa)

Setup: `pip install -e .` poi `python db/build_db.py` (ricostruisce `data/ibp.duckdb` da zero,
sempre riproducibile, mai un "aggiornamento in place" perché non esiste un DB reale da preservare).
Stack forecasting in extra separato: `pip install -e ".[forecast]"`.

`db/build_db.py` costruisce, in ordine: (1) master item + mirror fatti dEPM; (2) overlay a grafo
(`edge`); (3) rete produttiva (`item_link`, `production_eligibility`, `routing`,
`bill_of_resource`, `resource`, `resource_capacity` — inclusi i terzisti come plant con capacità
propria, `plant_type='subcontractor'`); (4) scenari (`scenario`, `edits`, `overlay`); (5) forecast e
FVA (`forecast_snapshot`, `forecast_override`, `actual_restatement`); (6) processo (`cycle`,
`cycle_phase`, `review_instance`, `task`, `raci`, `portfolio_item`, `project`, `gap`,
`reconciliation_session`, `decision`, `escalation`, `rate_card`, `assumption`, `exception_rule`,
`exception_instance`).

Gotcha Windows (dettaglio operativo, riflesso come NFR in `constraints.md` D7): niente
autoload/autoinstall di extension DuckDB; `temp_directory` esplicito; escludere `data/` da Windows
Defender; DuckDB single-writer con lock di processo; RNG via `hashlib.sha256` non `hash()`; versioni
pinnate (`polars` compresa); stack di forecasting installabile **solo da wheel** sulla serie 2.x
(nessun compilatore richiesto, a differenza della diagnosi iniziale); ordine di import obbligatorio
in `ibp/forecast/` per evitare un segfault silenzioso fra due runtime OpenMP; `reconcile(S_df=...)`
non `S=` (API 1.x vs 0.4.x).

Verifica manuale: `python db/build_db.py` due volte consecutive deve produrre lo stesso riepilogo e
la stessa validazione, senza errori.

Struttura repo (livello alto): `pyproject.toml`, `db/{schema.sql,build_db.py,seed/**}`, `data/`
(gitignored). "Cosa NON è ancora qui": dominio, semantic layer, motore, allocatore, API e workbench
sono task successivi (T2-T13).
