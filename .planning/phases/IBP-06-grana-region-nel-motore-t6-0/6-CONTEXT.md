# Phase 6: Grana region nel motore (T6.0) - Context

**Gathered:** 2026-09-19
**Status:** Ready for planning

> **Nota sulla lingua.** Contenuto in italiano. Restano in inglese, verbatim, i nomi di tag e di
> sezione che i workflow GSD leggono (`<domain>`, `<decisions>`, `## Phase Boundary`, `D-01`…).
> Sono identificatori, non prosa. Il contesto e' stato derivato da ADR-001, dalla mappatura del
> codebase del 2026-09-19 e dal backlog dello SPEC, non da una sessione di discuss-phase.

<domain>
## Phase Boundary

La region della domanda sopravvive lungo tutto il motore fino alla scelta del plant, cosi' che
l'eleggibilita' per `region_scope` diventi esprimibile senza produrre numeri plausibili ma
sbagliati.

**Questa fase deve restare isolata.** Riapre `ibp/engine/`, che oggi e' chiuso e verde (187 test
passati al 2026-09-19). Non va infilata accanto ad altro lavoro. Precede la Phase 8 (T6) e la
Phase 10 (T10.0).

**Fuori scope:** l'eleggibilita' vera e propria per region (AC5) e' la Phase 8. Questa fase rende
AC5 *esprimibile*, non la implementa. Il preload bulk del master data (T10.0, AC29) e' la Phase 10
e non va anticipato qui, anche se la grana nuova cambia quali indici serviranno.

</domain>

<decisions>
## Implementation Decisions

### Dove sta davvero il difetto

- **D-01:** Il difetto **non e' locale a `_eligible_plant_for`**. Verificato il 2026-09-19: la
  region e' gia' persa a monte, nell'aggregazione `(manufact_key, date_key)` dentro
  `derived_manufacturing_demand` (`ibp/engine/engine.py:347-366` e `492-499`). Aggiungere un
  parametro `region` alla firma di `_eligible_plant_for` (`engine.py:209-226`) senza allargare la
  grana della cella non risolve nulla: non c'e' una region da passare.
- **D-02:** La cache di `_eligible_plant_for` e' chiavata solo su `manufact_key`, quindi la prima
  data vista fissa il plant per tutti i periodi. La chiave deve diventare
  `(manufact_key, region, date_key)` e la validita' temporale va controllata davvero.
- **D-03:** Oggi il comportamento e' corretto **solo per accidente**: il seed lascia
  `production_eligibility.valid_to` a NULL, quindi nessuna eleggibilita' scade mai. Serve un test
  che popoli `valid_to` e dimostri che lo stesso `manufact_key` risolve a plant diversi a date
  diverse — altrimenti la correzione non e' verificabile.

### Gate d'uscita

- **D-04:** **AC10 e' il cancello d'uscita.** La fase non e' chiusa finche'
  `python -m pytest tests/test_engine_ac10_recalc_equivalence.py -q` non passa sulla grana
  allargata: `recalculate()` deve restare equivalente a `full_recalculate()`, con valori identici
  confrontati con `==`, non con `math.isclose`.
- **D-05:** Nessuna regressione ammessa su AC11 (cutoff) e AC12 (aggregate). Allargare la grana
  cambia quante celle il motore tocca, quindi cambia i contatori di `CutoffStats`: se quei test
  cambiano numero, va capito **perche'** prima di aggiornarli, non aggiornato e basta.

### GRAFO-01, incluso in questa fase

- **D-06:** La guardia `as_of` di `neighbors()` (`ibp/semantic/graph.py:148`) guarda solo
  `is_historical` e `rel_type`, mai `node_type`, quindi `neighbors(con, "plant", …, as_of=<data
  passata>)` solleva `GraphSnapshotLimitationError` anche quando un nodo plant non puo' portare
  archi derivati da `item_link`. Sta in questa fase perche' la risoluzione del plant per data la
  attraversa.

### Claude's Discretion

Come allargare la grana — se propagare `region` come colonna aggiuntiva lungo le strutture
esistenti o introdurre un tipo di chiave esplicito — e' scelta di implementazione, purche' i
criteri sopra siano veri e la suite resti verde. Anche la strategia di cache (chiave allargata
contro invalidazione per data) e' libera.

</decisions>

<specifics>
## Specific Ideas

Il vincolo di determinismo del progetto vale anche qui e non e' negoziabile: niente
`SUM(...) GROUP BY` parallela su cui poi si asserisce l'uguaglianza. Dove si aggrega, si ordina
sulla PK piena e si somma in Python, come fa gia' `materialize_version` in
`ibp/scenario/overlay.py`. I test asseriscono `==`.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Il difetto, misurato
- `.planning/codebase/CONCERNS.md` — i sei debiti verificati riga per riga il 2026-09-19; il
  punto 1 e' questa fase, con la scoperta che la perdita di region e' a monte.
- `.planning/codebase/ARCHITECTURE.md` — layer del motore, DAG dichiarato, height, early cutoff.

### Requisiti e criteri
- `.planning/REQUIREMENTS.md` — `GRANA-01` e `GRAFO-01`, piu' AC10/AC11/AC12 gia' spuntati che
  non devono regredire.
- `.planning/ROADMAP.md` §Phase 6 — i cinque success criteria, che sono il contratto di chiusura.
- `docs/02-spec-m1-corrente.md` §D4 — motore: DAG dichiarato, height, early cutoff, preload bulk.
- `docs/02-spec-m1-corrente.md` §D2 — rete produttiva e `item_link`, che e' cio' che AC5 usera'
  dopo questa fase.

### Convenzioni da rispettare
- `.planning/codebase/CONVENTIONS.md` — determinismo, errori di dominio come classi esplicite,
  divieto di magic number nei `.py`.
- `.planning/codebase/TESTING.md` — la convenzione di naming da AC a file di test, e la mappa di
  quale file copre quale AC.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ibp/semantic/graph.py` — `resolve_manufacturing_items()` e `resolve_identity()` sono il punto
  in cui il master data entra nel motore. **Attenzione:** sono anche i due N+1 misurati
  (rispettivamente 3.492 e 3.498 query per costruzione). Non e' compito di questa fase
  risolverli (e' la Phase 10), ma allargare la grana senza saperlo puo' peggiorarli.
- `tests/_engine_support.py` — `assert_matches_full_recalculate()` e `values_close()` sono gli
  helper con cui AC10 e' gia' scritto: il gate d'uscita si verifica riusando questi, non
  scrivendone di nuovi.

### Established Patterns
- Errori di dominio come classi esplicite per package (`ibp/engine/errors.py`), mai fallback
  silenziosi. Una region mancante dove serve deve sollevare, non scegliere un default.
- RNG deterministico via `hashlib`, mai il builtin `hash()` che e' salted.

### Integration Points
- `derived_manufacturing_demand` (`engine.py:347-366`, `492-499`) — dove la grana si perde oggi.
- `_eligible_plant_for` (`engine.py:209-226`) — dove la grana serve.
- `neighbors()` (`ibp/semantic/graph.py:148`) — la guardia `as_of` di GRAFO-01.
- `production_eligibility` (`db/schema.sql`) — la tabella con `region_scope` e `valid_to`.

</code_context>

<deferred>
## Deferred Ideas

- **AC5, eleggibilita' per region e rifiuto del plant non eleggibile** — Phase 8 (T6.b). Questa
  fase la rende esprimibile; implementarla qui sforerebbe il confine.
- **T10.0, preload bulk del master data** — Phase 10. Dipende da questa fase perche' la grana con
  region cambia quali indici servono.
- **D-006 e `routing.variant_key`** — il routing elettivo NAM va su un *insieme* di attributi di
  configurazione, mentre lo SPEC disegna `routing.variant_key` come chiave opaca singola. Tensione
  reale, ma appartiene a T6.d (Phase 8), non qui.

</deferred>

---

*Phase: IBP-06-grana-region-nel-motore-t6-0*
*Context gathered: 2026-09-19*
