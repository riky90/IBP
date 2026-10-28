<!-- TIPO: DOC (registro di consegna, non specifica).
     Stato di esecuzione del run software-house 20260910-0830-ibp-platform: cosa e' stato
     consegnato in T1-T4, quali difetti sono stati trovati e chiusi, e il debito aperto.
     Non contiene requisiti: i requisiti stanno in docs/02-spec-m1-corrente.md.
     Origine: .software-house/20260910-0830-ibp-platform/state.md (cartella gitignored). -->

# Run 20260910-0830-ibp-platform

Mode: greenfield
Programma: 3 milestone. Questo run = **M1 (core + rete produttiva)**.
Piano approvato: `docs/01-plan-m1.md` (13 task, 26 AC, 6 ondate)

| Stage | Status | Notes |
|---|---|---|
| 0 Classify | done | greenfield |
| 1 Scout | skipped | greenfield |
| 2 Plan | done | rivisto 2 volte dopo le risposte dell'utente sulla rete produttiva |
| GATE | **approvato** | |
| 3 Execute | running | wave 0: T1 |
| 4 Docs | pending | T13 |

## Task

| T | Owner | Wave | Status |
|---|---|---|---|
| T1 schema+seed | sh-data | 0 | **done** |
| T2 dominio+semantic | sh-backend | 1 | **done** (critic PASS al giro 2, 96 test) |
| T3 motore concurrent | sh-backend | 2 | **done** (2 giri critic, verifica finale in corso) |
| T4 scenari | sh-backend | 2 | **done** (2 giri critic, verifica finale in corso) |
| T5 forecast+FVA | sh-backend | 2 | pending |
| T6 rete produttiva | sh-backend | 3 | pending |
| T7 capacita+allocatore | sh-backend | 3 | pending |
| T8 processo | sh-backend | 3 | pending |
| T9 adapter+viste | sh-data | 3 | pending |
| T10 API | sh-backend | 4 | pending |
| T11 workbench | sh-frontend | 5 | pending |
| T12 CLI+demo | sh-backend | 5 | pending |
| T13 docs | sh-docs | 6 | pending |

## Fuori backlog
- Diagrammi archify: architettura, rete produttiva multi-step, ciclo P/R/A/C, DAG, scenari
- UI-SPEC.md via /gsd-ui-phase prima di T11

---

## Handoff — fine sessione 2026-09-10

### Fatto
- Dominio `dev` collegato a `IBP/.claude/` (68 skill + 47 agent, junction).
- Ricerca: `docs/00-research-brief.md` (o9 / Kinaxis / Quintiq + stato Acmelift dal vault).
- Piano M1 approvato: `docs/01-plan-m1.md` — 3 milestone, 13 task, 26 AC, 6 ondate.
- Diagrammi archify consegnati (showcase, 9/9 check, 0 errori):
  - `docs/diagrams/01-architettura.html` (+ `arch.json`)
  - `docs/diagrams/02-rete-produttiva.html` (+ `rete.json`)

### T1 — chiuso 2026-09-10
`python db/build_db.py` ricostruisce `data/ibp.duckdb` da zero. Idempotenza verificata su
3 run consecutivi con hash di contenuto per tabella (RNG deterministico via `hashlib`,
non `hash()` che e' salted). `_validate()` fa fallire il batch su invarianti violate:
cardinalita', `product_mapping` che somma a 100%, presenza dei casi M:N, presenza di
**entrambi** i tipi di routing, tombstone, copertura dei lag forecast, cluster richiesti.
Verificato con duckdb 1.1.3 / polars 1.9.0 / pyarrow 18.1.0.

**Tre scelte di T1 da conoscere a valle:**
1. **Volume dei fatti cappato** agli ultimi 4 cicli chiusi + ciclo corrente + `SOP_BP_2027`,
   non l'intero cubo da ~466 versioni. Assunzione di scala documentata nel README.
   **Tocca T5**: la baseline statistica ha meno storia di quanta ne avrebbe in produzione:
   con ~24-36 mesi l'ordine ARIMA e' gia' a malapena identificabile, con meno lo e' ancora
   meno. Verificare la copertura prima di scegliere il pool di modelli.
2. **AC2 interpretata sui magic number di capacita'** (DPLANT/process), spostati in
   `db/seed/data/*.json`. L'unico `8` residuo nei `.py` e' `encoding="utf-8"` — segnalato
   e giudicato fuori scope. Giudizio corretto: il test anti-literal di T3 deve escluderlo,
   o fallira' su ogni file.
3. **numpy evitato deliberatamente** (non in lista dipendenze): solo `random`/`math` stdlib.
   `build_db.py` gira con duckdb+polars+pyarrow soli.

`db/views/` e `ibp/` non toccati (scope T9 / T2+).

### Prossimi passi, in ordine
1. Verificare l'esito di T1 (`python db/build_db.py` due volte → stesso risultato).
2. Diagrammi archify mancanti: **3** ciclo P/R/A/C con i 5 review (`workflow`),
   **4** DAG di ricalcolo con dirty propagation (`dataflow`),
   **5** lifecycle scenari (`lifecycle`).
3. Wave 1: **T2** (sh-backend, dominio + semantic layer + DAG dichiarato).
4. Wave 2 in parallelo: T3 motore, T4 scenari, T5 forecast.
5. Prima di T11: `/gsd-ui-phase` per `UI-SPEC.md`.

### Lezioni archify (per non ripeterle)
- `meta.locale` supporta solo `en` / `zh-CN`: contenuti in italiano, viewer UI in inglese.
- Dichiarare sempre `fromSide`/`toSide` espliciti sui layout a fasce: il router
  inferisce lati sbagliati quando i box si sovrappongono in X (27 errori → 5).
- Mai due archi opposti fra gli stessi due nodi: modellare l'intermedio come nodo.
- Le etichette collidono con le corsie orizzontali dei bridge: separarle con `labelDy`.
- `dataflow` richiede `label` su ogni flow, e le righe valide sono **0..4**.
- `composition/desktop-readability`: viewBox largo → sublabel sotto 6px a 1440px.
  Rimedio: ridurre la larghezza, allargare i nodi (`width`), accorciare i sublabel.


---

## Sessione 2026-09-11 (seconda)

- `concept-forge` generata con `agent-factory`: skill in `~/.claude/skill-domains/dev/concept-forge/`,
  4 agenti (`concept-investigator`, `concept-architect`, `concept-critic`, `concept-diagrammer`)
  in `~/.claude/agent-domains/dev/`, junction creata su `IBP/.claude/skills/concept-forge`.
  Diagrammi opzionali: dopo il gate sui requirements la skill propone, l'utente sceglie,
  "nessuno" e' un esito valido.

### T2 — dominio + semantic layer

**Attenzione: `plan.md` e' parzialmente obsoleto.** Il suo T2 parla ancora di `DSALES_PRODUCT`,
`DMANUFACT_KEY` e `product_mapping`, tabelle che T1 rifatto ha eliminato. `db/schema.sql` e'
la verita'; ogni prompt verso gli implementatori deve dirlo esplicitamente.

- sh-backend: creato `ibp/` (17 moduli, ~1.124 righe) — `config.py`, `db.py` (unico punto di
  accesso DuckDB), `domain/` (state machine + entita' + errori tipizzati), `semantic/`
  (`dimensions`, `graph`, `measures`, `registry`).
- sh-tester: **GREEN**, 61 test in `tests/`. AC2 verificata davvero (plant aggiunto su copia del
  DB cambia il registry senza toccare codice; AST scan contro i literal 30/8/500), AC10 verificata
  strutturalmente.
- sh-critic: **FAIL**, 3 finding bloccanti, tutti su `ibp/semantic/graph.py`:
  1. `ROW_NUMBER() PARTITION BY from_item, to_item, link_type` trascina righe stale: un target
     tolto da uno split non sparisce mai. Caso misurato: quote che sommano a **145%**.
  2. `neighbors()` case-sensitive su `rel_type` (`edge` maiuscolo, `item_link` minuscolo):
     `neighbors("item","6","produces")` restituisce `[]` invece di sollevare.
  3. `as_of` promette lo stato storico del grafo ma `edge` e' seminato solo all'ultimo periodo:
     `neighbors` e `resolve_manufacturing_items` si contraddicono alla stessa data.
- Round 1 di revisione in corso. Il finding 3 si chiude ritrattando la promessa lato T2 (il fix
  vero sarebbe in `db/seed/graph.py`, di proprieta' di T1 — da schedulare, non da dimenticare).

### Debito noto, non di T2

`pip install -e .` fallisce su Windows senza MSVC: `statsforecast==1.7.8` non ha wheel e prova a
compilare. Il pin e' in `pyproject.toml`, **di proprieta' esclusiva di T1**. Blocca l'installazione
pulita del pacchetto, non l'esecuzione (basta `duckdb`). Da risolvere prima di T5 (forecast), che
e' l'unico task che usa davvero `statsforecast`.


### T2 — chiuso 2026-09-11, critic PASS

Due giri di revisione, ognuno ha chiuso difetti veri:

**Giro 1** — tre finding bloccanti su `ibp/semantic/graph.py`:
1. `ROW_NUMBER() PARTITION BY from_item, to_item, link_type` trascinava righe stale: un target
   tolto da uno split non spariva mai. Caso misurato: quote a **145%**, contro l'invariante
   sum=100 che `build_db.py` fa rispettare. Avrebbe gonfiato `derived_manufacturing_demand`.
2. `neighbors()` case-sensitive su `rel_type` (`edge` maiuscolo, `item_link` minuscolo):
   restituiva `[]` invece di sollevare.
3. `as_of` prometteva lo stato storico del grafo che `edge` non puo' dare.

**Giro 2** — la guardia del punto 3 aveva introdotto una regressione:
1. `Decimal` vs `float`: `2.5 * slot_equivalence_factor` sollevava `TypeError`. L'accessor
   aggiunto per T3 si rompeva al primo uso previsto.
2. La guardia scattava su `as_of != today`, quindi anche **in avanti** — con orizzonte a 24 mesi
   e' la chiamata normale di T6/T7.
3. La guardia non copriva il path `rel_type=None`: la trappola del giro 1 sopravviveva li'.

**Verdetto finale**: PASS, idoneo a reggere T3 e T4. Il critic ha verificato che le quote sommano
a 100 su tutti i 1.661 planning model a quattro date, che nessun `Decimal` sopravvive su nessun
path del registry, e che lo scan AC2 scatta davvero (provato contro una root `engine/` simulata:
becca `30`, `250 * 2` ripiegato a `500`, e `"8"`).

**Contratto per i task a valle:**
- Ogni numerico che il semantic layer restituisce e' `float`, mai `Decimal`. Chi aggiunge un
  accessor su colonna `DECIMAL` casta nel row constructor. Il `rate_card` ha `DECIMAL` ma nessun
  accessor: chi lo espone in T5/T7 deve castare.
- `neighbors()` solleva `GraphSnapshotLimitationError` per `as_of` **strettamente passato** sui
  rel_type derivati da `item_link`. Le date in avanti funzionano. Per una risposta datata si usa
  `resolve_manufacturing_items()`.
- Il DAG e' dichiarato in `ibp/semantic/measures.py` e **non calcola**: `nodes()`, `edges()`,
  `topological_order()`, `dirty_set()`. L'esecuzione e' di T3.

**Debito noto, non bloccante:**
- `graph.py:148` — la guardia e' troppo larga per node type: `neighbors("plant", ...)` con `as_of`
  passato solleva, anche se un nodo `plant` non puo' portare archi item-link. T6 la incontrera'
  su una query storica plant->region legittima. Fix minimo: saltare la guardia se
  `node_type != "item"`.
- `graph.py:146` — un `datetime.datetime` passato come `as_of` (sottoclasse di `date`) solleva
  `TypeError`. Da normalizzare o rifiutare esplicitamente.
- `tests/test_semantic_ac2_master_data.py:29` — la root list non include `ibp/network/` (T6), dove
  finiscono quota e offset di 2 mesi.
- `tests/conftest.py:31` — un fallimento di T1 che aborta prima di creare `data/` resta
  indistinguibile da un checkout pulito (skip, exit 0).


---

## Fine sessione 2026-09-11 (seconda) — T3 e T4 chiusi, suite 176 verde

`python -m pytest -q` -> **176 passed, 0 failed**. Punto fermo pulito.

### T3 — motore di ricalcolo (`ibp/engine/`)

AC10 **regge**, e il critic ha provato a romperlo sul serio: chiavi `(product, date)` nuove oltre
l'orizzonte, division assente dall'indice, 40 batch casuali che mescolano le due radici. Key set
identici a ogni nodo. Il motivo strutturale, da conservare: ogni arco `_downstream` rispecchia
esattamente le letture della `_compute_*_cell` corrispondente, le altezze sono strettamente
crescenti, e una cella assente conta come cambiata.

Difetti trovati e chiusi:
1. **Batch non atomico** — gli edit venivano applicati prima di essere validati. Un edit
   malformato lasciava il primo applicato e mai propagato, e sporcava l'indice in modo che
   *ogni* `full_recalculate()` successiva rilanciasse lo stesso errore per sempre. Una richiesta
   HTTP malformata avrebbe brickato il motore di T10. Ora si valida tutto il batch prima di
   scrivere qualsiasi cosa.
2. **`confirmed_production` non era nel DAG dichiarato** — era una radice esogena vera, iniettata
   privatamente dal motore. `dirty_set("confirmed_production")` sollevava `KeyError`, e T4/T7/T10
   leggono il DAG per sapere cosa alimenta un gap. Ora e' dichiarata, `gap_req_conf` dipende da
   entrambe le radici, e l'iniezione privata e' sparita.
3. **Contatori**: `CutoffStats` ha un quarto termine `absent`. Tutti i 2.352 "cutoff" erano in
   realta' sparsita' del rate card, non ricalcoli senza effetto — un pannello di T10 avrebbe letto
   la sparsita' del master data come risparmio di ricalcolo.
4. **Rumore floating-point eliminato alla sorgente**: `_compute_dmd_cell` somma su collezioni
   ordinate. I test ora asseriscono `==`, non `math.isclose`.

### T4 — scenari (`ibp/scenario/`)

Due difetti trovati dal tester, cinque dal critic. I piu' istruttivi:

1. **Non-determinismo in lettura** — `materialize_version` usava `SUM(...) GROUP BY` parallela:
   due chiamate su dati immutati differivano nell'ultimo bit su ~3.400 valori, e uno scenario con
   **una** cella sovrascritta ne riportava 3.863 (4.243 al run dopo). Risolto **alla sorgente**
   (`ORDER BY` sulla PK piena + somma in Python), non con un epsilon: una tolleranza avrebbe
   azzerato il `delta` lasciando i due valori diversi.
2. **Lo stesso difetto persistito in scrittura** — `promote()` ricalcolava `target * share` anche
   per fette **mai toccate**: un branch con zero edit scriveva 27.019 righe su 100.224 con deriva
   fino a 5.7e-14, dentro `TSOP_DEMAND`, dove nessun ordinamento in lettura poteva piu' toglierla.
   Ora distingue "mai toccata" da "toccata, stesso valore" e copia le prime byte per byte.
3. **Misure non additive sommate** — `CAPACITY_UTIL` (rapporto, righe base fra 0,7164 e 0,9076)
   risolveva a **24,5789**; `SLOTS_AVAILABLE` (`agg_method='max'`, tutte 8.0) a **240**. Deciso:
   **rifiutare** (`NonAdditiveMeasureError`), non onorare `agg_method` — le righe non-`sum`
   passano senza essere aggregate.
4. **Fuga fra scenari su basi diverse** (AC15) — un figlio su v370 leggeva l'edit del padre su
   v353, e due read path si contraddicevano. Chiuso con `MismatchedBaseVersionError` e
   `CellVersionMismatchError`, piu' filtro su `version_key` come difesa in profondita'.
5. **`side`/`status` non verificati alla promozione** — un branch DEMAND promosso come SUPPLY
   produceva `SOP_2098_03_SUPPLY_A` con dentro 100.224 righe di domanda. Il DAX legge il nome come
   stringa, quindi sarebbe passato liscio. Ora `SideMismatchError`.

### Debito aperto, da schedulare

- **T1 deve rigenerare `db/seed/scenario.py`**: il `base_snapshot_id` seminato ha formato
  `SNAP_{version_name}_{iso_ts}`, quello di `branch()` e' `SNAP_{version_key}_{sha256}`. Oggi il
  check AC16 e' **tollerante al formato**, quindi gli scenari del seed si promuovono **senza
  verifica reale della base**. E' l'unico scenario promuovibile spedito, ed e' quello che cerchera'
  la demo di T12.
- **T5 e' bloccato**: `statsforecast==1.7.8` non ha wheel per Python 3.13 e non si installa
  nemmeno in un venv pulito (serve MSVC). Le tre librerie di forecasting sono ora in un extra
  `[forecast]`, quindi `pip install -e .` funziona di nuovo, ma T5 va deciso: Build Tools, Python
  piu' basso per quel task, o altra libreria.
- **T10**: costruire un `RecalcEngine` costa 63-86s, dominati da query N+1 (3.492 coppie
  `(product,date)` ognuna con una `resolve_manufacturing_items` che a sua volta fa una query per
  target). Due query batch sostituirebbero migliaia di round-trip. Da risolvere **prima** che T10
  costruisca un layer HTTP su `__init__`.
- **T6/T7**: `_eligible_plant_for` (`engine.py:199-216`) cachea per `manufact_key` e ignora
  `region_scope`, quindi la prima data vista fissa il plant per tutti i periodi. Corretto solo
  perche' il seed lascia `production_eligibility.valid_to` NULL. Silenziosamente sbagliato appena
  T6/T7 datano o scopano per regione l'eleggibilita' (AC5).
- **T6**: la guardia `as_of` di `neighbors()` e' troppo larga per node type — `neighbors("plant", ...)`
  con data passata solleva anche se un nodo plant non puo' portare archi item-link.
- **Provenienza**: una riga `DVERSIONS` promossa non risale allo scenario, e le righe proratate
  non si distinguono da quelle copiate. Un planner non puo' verificare cosa e' stato sovrascritto
  e cosa derivato.
- **Transazioni**: tutti gli helper di scrittura di `ibp/scenario/` emettono un `BEGIN TRANSACTION`
  nudo. Falliranno se T10 avvolge una chiamata in una propria transazione.
- **`plan.md` del run e' obsoleto** su modello dati e numerazione task. Da rigenerare con
  `sh-architect` prima di T6, invece di compensare a mano in ogni prompt.

### Verifiche finali dei critic

Lanciate su T3 e T4, non ancora rientrate alla chiusura della sessione. I finding bloccanti sono
tutti chiusi e verificati dagli implementatori su copia del DB; queste passate sono conferma
indipendente, da leggere a inizio prossima sessione.
