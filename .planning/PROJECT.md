# IBP ACMELIFT

## Che cos'è

Una piattaforma di **Integrated Business Planning** per ACMELIFT: una libreria Python con CLI
(più, a valle, un'API HTTP interna e un workbench web) costruita su un unico file DuckDB locale.
Preserva il ciclo S&OP mensile P/R/A/C che l'azienda già esegue bene, gli innesta i due review IBP
mancanti (Portfolio Review e Integrated Reconciliation) come oggetti software di prima classe, e
automatizza i cinque punti che oggi si fanno a mano: mapping planning-model↔manufacturing-key N:N,
eleggibilità multi-plant, routing multi-step, ri-allocazione sull'orderbook, domanda dipendente del
semilavorato oggi calcolata in Excel.

È in corso la milestone **M1 — Core + rete produttiva**: schema e seed, motore di concurrent
planning, scenari, forecast statistico + FVA, ciclo e review, rete produttiva, capacità, API,
workbench, demo.

## Valore centrale

**Il planner deve poter cambiare un numero e vedere subito, sull'intero piano, cosa ne consegue —
su uno scenario che può confrontare e promuovere senza perdere né la base né la tracciabilità.**

Se tutto il resto fallisce, questo deve funzionare: è la sostituzione del collo di bottiglia
tecnologico misurato da Gartner (tecnologia/analytics/cultura **1**, processo **4-**, complessivo
**2** contro un benchmark manifatturiero **3-**). Il processo è già maturo: non va reinventato, va
retto da una tecnologia che regga.

## Requisiti

### Validati (consegnati e verdi)

Consegnati sotto il run `/software-house` `20260910-0830-ibp-platform`, commit `d54a453`, suite
verde (`python -m pytest -q` → **187 passed**), riverificati contro il codice il 2026-09-19.

- ✓ **AC1** — `python db/build_db.py` ricostruisce il DB da zero, idempotente, cardinalità isomorfe — Phase 1 (T1)
- ✓ **AC2** — `Max Slots`/granularità/soglia `<500` sono master data; test anti-literal via scan AST — Phase 1 (T1)
- ✓ **AC10** — `recalculate(changed)` ≡ ricalcolo completo (test cardine) — Phase 3 (T3)
- ✓ **AC11** — Early cutoff osservabile e misurato (`CutoffStats`, con il quarto termine `absent`) — Phase 3 (T3)
- ✓ **AC12** — `min`/`max`/`ratio` ricalcolati sul gruppo, mai delta-aggiornati — Phase 3 (T3)
- ✓ **AC13** — Branch → modifica → confronto → promozione crea una nuova istanza `DVERSIONS` — Phase 4 (T4)
- ✓ **AC14** — Tombstone esplicito: una cella cancellata non ricompare dal base — Phase 4 (T4)
- ✓ **AC15** — `cache_key()` include lo stack; nessuna fuga fra scenari fratelli — Phase 4 (T4)
- ✓ **AC16** — Promozione con base mossa → conflitto rilevato prima di qualunque scrittura — Phase 4 (T4)
- ✓ **Semantic layer e dominio** — `ibp/db.py` unico entrypoint DuckDB, `MEASURE_DAG` dichiarato
  come dato, macchine a stati dichiarative, nessun `Decimal` esposto — Phase 2 (T2)

### Attivi (scope M1 in corso)

Elenco completo e checkabile in `.planning/REQUIREMENTS.md`. In sintesi, i 22 acceptance criteria
ancora aperti (AC3-AC9, AC17-AC31 meno quelli validati sopra) più cinque requisiti di
consolidamento emersi dalla verifica del codice (`GRANA-01`, `GRAFO-01`, `MDATA-01`, `API-01`,
`UX-01`) e **R-001 Step A** (tronco unico, parte additiva).

Metrica di successo lato sviluppo: **ogni AC1..AC31 ha un test che passa in `tests/`**, con la
convenzione di naming `test_<area>_ac<N>_<slug>.py` documentata in
`.planning/codebase/TESTING.md`. La metrica di business dietro al progetto resta lo spostamento
dell'asse tecnologia della misura Gartner 2024.

### Fuori scope

- **R-001 Step B — le tre modifiche strutturali del tronco unico** (grana di `overlay`/`edits`
  allargata alla grana piena dei fatti; `promote()` da copia materializzante a spostamento di
  puntatore; risoluzione ricorsiva fino a una root esplicita) — **rinviate a M2**. Motivo: tutte e
  tre collidono con il vincolo duro `DVERSIONS.version_name UNIQUE`, letto come **stringa** dalle
  misure DAX di Power BI. Spostare il nome a essere un'etichetta applicabile a un nodo qualunque
  dell'albero significa toccare un contratto esterno di consumo che M1 non può rinegoziare. Step A
  (Phase 13) è additivo e non richiede questo.
- **REQ-F11 / REQ-F12 — rete a monte** (dealer interni de-schiacciati, sell-in intercompany, stock
  di canale a partita doppia, nodi di capacità installazione) — scope M2.
- **REQ-F13 — rete a valle** (componenti critici, fornitori interni come nodi con capacità, double
  sourcing) — scope M3.
- **Enterprise multi-utente** (locking a cella, versioning nativo, SSO/RLS, orchestratore esterno) —
  M1 è in-process single-user (REQ-A6); il modello di dominio deve sopravvivere alla migrazione, non
  anticiparla.
- **Solver esterno di ottimizzazione** — `AllocationStrategy` resta un'interfaccia sostituibile
  (REQ-A3); M1 non implementa un ottimizzatore.
- **Scritture verso SAP S/4, Infor dEPM, ERP/MRP** — confine di sistema (AC24): SAP consumato
  read-only, dEPM riceve un **file**, Power BI non toccato.
- **Partizione del DAG per product family** — resta per-cella in M1; si partiziona solo se la
  Phase 14 (API) misura latenza >200ms.
- **Riscrittura di T1-T4** — consegnati, verdi e verificati. Nessuna fase li ripianifica.

## Contesto

**Stato di build reale (verificato 2026-09-19).** Il progetto ha girato fino a M1/T4 sotto
l'orchestratore `/software-house` (run `20260910-0830-ibp-platform`) ed è migrato a GSD oggi. T1
(schema+seed), T2 (dominio+semantic+DAG+grafo), T3 (motore concurrent), T4 (scenari) sono **done,
reviewed, verificati**; suite verde a 187 test in ~111s; un solo commit su `master`, `d54a453`.
Pendenti: T5, T6, T7, T8, T9, T10, T11, T12, T13 più sei pacchetti di debito espliciti (T6.0,
T10.0, T10.1, T11.0, T11.1, T11.2).

**Debito tecnico verificato contro il codice, non preso sulla fiducia** (`.planning/codebase/CONCERNS.md`):

| # | Debito | Dove | Nota di verifica |
|---|---|---|---|
| 1 | `_eligible_plant_for` cachea per `manufact_key` e ignora `region_scope` | `ibp/engine/engine.py:209-226` | **Più profondo del previsto**: la region è già persa a monte, nell'aggregazione `(manufact_key, date_key)` di `derived_manufacturing_demand` (`engine.py:347-366`, `492-499`). Il fix non è locale. Oggi corretto solo perché il seed lascia `production_eligibility.valid_to` NULL → **T6.0** |
| 2 | N+1 sulla costruzione del motore | `engine.py:289` → `graph.py:223` | 3.492 chiamate a `resolve_manufacturing_items`, **14.397 query** per `RecalcEngine.__init__`, riprodotte a runtime. **Più un N+1 annidato non segnalato prima**: `resolve_identity()` (`graph.py:287`) spara altre 3.498 query → **T10.0** |
| 3 | `BEGIN TRANSACTION` nudo, nessun annidamento | `scenario/branch.py:81,113,127`, `edits.py:93`, `promote.py:332` | `TransactionException: cannot start a transaction within a transaction` riprodotta; DuckDB non ha SAVEPOINT; nessun helper rientrante in `ibp/db.py` → **T10.1** |
| 4 | `compare()` filtra a `agg_method='sum'`: le misure non additive spariscono in silenzio | `scenario/overlay.py:123-179` | Catalogo verificato su `db/seed/dimensions.py`: **19 `sum`, 1 `max`, 3 `avg`, 3 `ratio`** → **T11.0** |
| 5 | Nessuna provenienza sopravvive alla promozione | `db/schema.sql:115-128` | `overlay_touched_slices()` conosce già l'informazione in memoria e la butta via → **T11.1 + T11.2** |
| 6 | Guardia `as_of` di `neighbors()` troppo ampia per node type | `ibp/semantic/graph.py:148` | Blocca query storiche legittime plant→region; si materializza quando `ibp/network/` (T6.b) userà `neighbors()` su nodi `plant` → **GRANA/GRAFO, Phase 6** |

**Chiuso, da non ripianificare:** il blocco d'installazione Windows di `statsforecast` è stato
risolto il 2026-09-12 (pin a `statsforecast==2.1.1`, installabile da wheel, nessun MSVC). **T5 è
genuinamente sbloccato**, ma il percorso di forecasting non è mai stato esercitato.

**Riferimenti di piattaforma:** o9 (Enterprise Knowledge Graph), Kinaxis Maestro/RapidResponse
(concurrent planning, scenari illimitati, "like a version control system for data" — è il modello
di R-001), DELMIA Quintiq. Il differenziatore comune è un livello semantico L2 unico e condiviso:
il modello Infor dEPM esistente è l'ontologia già concordata globalmente e resta il candidato
naturale, non va buttato.

## Vincoli

- **Runtime**: Python 3.13 (dichiarato `>=3.11`) + `duckdb==1.1.3` come unico datastore, file
  singolo locale `data/ibp.duckdb` (gitignored, sempre ricostruito da `python db/build_db.py`, mai
  migrato in place). Libreria + CLI, nessun server applicativo fino a T10.
- **Contratto esterno duro**: uno strato di consumo Power BI / DAX legge
  `DVERSIONS.version_name` come **stringa**, con grammatica fissa `SOP_{YYYY}_{MM}_{SIDE}_{STATUS}`
  e colonna `UNIQUE`. Nessuna fase M1 può cambiarlo. È il motivo per cui R-001 Step B è rinviato.
- **Offline totale su Windows (AC25)**: nessuna rete a runtime, nessun account, nessuna licenza.
  Extension DuckDB con `autoinstall_known_extensions=false` / `autoload_known_extensions=false`;
  `temp_directory` esplicito in `data/tmp/`; DuckDB single-writer con lock di processo (una sola
  connessione condivisa fra thread, mai `fork()`).
- **Determinismo**: RNG via `hashlib.sha256`, mai `hash()` builtin; letture con `ORDER BY` su PK
  piena e somma in Python, mai `SUM(...) GROUP BY` parallelo; confronti del motore `==`, mai a
  tolleranza.
- **`pyproject.toml` è proprietà esclusiva di T1**, riaperto una sola volta (2026-09-12) per il pin
  `statsforecast` e l'extra `[forecast]`. Versioni pinnate con `==` esatto, `polars` inclusa
  (regressioni di memoria note su Windows). `numpy` **deliberatamente non è una dipendenza**.
- **`tests/**` è proprietà esclusiva del ruolo tester**; nessun mocking (`unittest.mock`,
  `monkeypatch` assenti dalla suite): si testa contro il DB DuckDB reale o una sua copia
  scrivibile.
- **Due task nella stessa ondata non toccano mai lo stesso file.** È il vincolo che detta gran
  parte dell'ordinamento delle fasi (vedi ROADMAP.md).
- **Vincolo di import critico in `ibp/forecast/`**: `from hierarchicalforecast._lib import
  reconciliation as _hf_lib` deve essere la **prima riga** del package, altrimenti il processo
  termina con **SIGSEGV senza traceback** (due runtime OpenMP distinti). Test di regressione in
  subprocess, verifica `returncode == 0`. API 1.x: `reconcile(S_df=...)`, non `S=`.
- **Errori tipizzati sempre**: `ibp.domain.errors`, `ibp.engine.errors`, `ibp.scenario.errors` —
  mai `ValueError` generico, mai `pytest.raises(Exception)`.
- **Seed sintetico ma isomorfo (REQ-F4)**: nessun dato ACMELIFT reale nel repo. Volume fatti
  cappato a 4 cicli chiusi + corrente + `SOP_BP_2027` — meno storia di quella di produzione (rischio
  noto per T5.b).

## Decisioni bloccate (ADR-001)

Fonte unica: `docs/ADR-001-decisioni-dominio.md`, `status: accepted`, `locked: true`,
`precedence: 0`, 2026-09-19, autore product owner. **Non sovrascrivibili** da SPEC, PRD o DOC: solo
da un altro ADR che le rimpiazzi esplicitamente. Dettaglio integrale in
`.planning/intel/decisions.md`.

<decisions locked="true" source="docs/ADR-001-decisioni-dominio.md" date="2026-09-19">

<decision id="D-001" scope="capacità / allocatore T7" status="locked">
I tre Basic Assemblies consumano **sia uno slot sia ore del pool** a Northfield. Il vincolo di capacità
è **doppio** e i due controlli sono **indipendenti**: l'allocatore deve poter respingere una riga di
Basic Assembly perché sono finiti gli slot della assembly island **oppure** perché sono finite le
ore del pool mensile. Gli AC della Phase 9 esprimono entrambi i limiti; i test coprono i due modi di
esaurimento **separatamente**. Confermata dal product owner il 2026-09-19; supersede la lettura
precedente "solo slot".
</decision>

<decision id="D-002" scope="master data / governance" status="locked">
Le convenzioni di naming `_Plant` e `-BA` sono mantenute dal product owner: nessun owner terzo,
nessun processo esterno di cambio senza preavviso. Il codice può trattarle come stabili, ma restano
logica applicativa portante (le misure DAX ricostruiscono i nomi come stringhe): vanno
centralizzate in un solo punto, mai replicate.
</decision>

<decision id="D-003" scope="master data plant / go-live, Phase 12 (T9)" status="locked">
Southport e Rivermouth sono **lo stesso sito**, non due plant distinti: una sola entità con, al più,
un alias. Qualunque logica che li conta come due sedi sovrastima la capacità disponibile.
Verificato il 2026-09-19 su `db/seed/data/plant_master.json`: il seed contiene nove plant e
**nessuno** è Southport o Rivermouth → **nessun rework di T1**; è un vincolo sull'adapter di master
data reale (T9) e sul go-live.
</decision>

<decision id="D-004" scope="master data plant / go-live, Phase 12 (T9)" status="locked">
`Eastbrook SEA` **è un plant** (SEA = segmento marino), non uno scope di vendita: va modellato come
plant con proprio scope produttivo, non come attributo commerciale. Stessa verifica di D-003:
assente dal seed → vincolo su T9 e go-live, nessun rework di T1.
</decision>

<decision id="D-005" scope="back-allocation, T6.d" status="locked">
La specifica ANA-050 §3.3 **è live**. Le regole di back-allocation e la correzione a resto massimo
che il design D2 eredita da ANA-050 descrivono il comportamento di produzione **corrente**, non una
proposta. Corrobora (non contraddice) `docs/02-spec-m1-corrente.md` §D2/AC27.
</decision>

<decision id="D-006" scope="rete produttiva, T6.d" status="locked">
Il routing elettivo NAM è guidato da un **insieme** di attributi di configurazione valutati
insieme — il colore è certamente uno dei driver, ma ci sono anche jib e altri — non da una singola
colonna discriminante. L'elenco è **deliberatamente aperto**: il modello deve essere estendibile
**senza modifiche di schema**.
**Tensione di design da risolvere quando si pianifica T6.d**: `routing.variant_key` nello schema D2
è disegnata come chiave singola opzionale (`variant_key?`). Può ancora bastare se **incapsula**
l'insieme (hash/composizione), ma il contratto "estendibile senza modifiche di schema" va
verificato esplicitamente contro il design attuale, non assunto.
</decision>

<decision id="D-007" scope="capacità, T7 / AC3" status="locked">
`Average Assembly Hours` esiste ed è popolato, ma il dato **non è aggiornato**. Si usa come input
(il sistema lo consuma normalmente) e si marca come **da revisionare prima del go-live**. I test di
accettazione verificano la **meccanica**, mai il valore assoluto del campo.
</decision>

<decision id="D-008" scope="processo, T8" status="locked">
Il job `3000` è un **carry-forward alternato**: creando un'istanza **preliminary** copia dalla
precedente **requested**; creando un'istanza **requested** copia dalla precedente **preliminary**.
Non è una copia dall'istanza omonima precedente.
</decision>

<decision id="R-001" scope="scenari — Phase 13 (Step A, M1) + M2 (Step B)" status="locked">
Il modello degli scenari deve presentarsi come un **tronco centrale** sul quale sia i **piani
salvati** sia gli **scenari salvati** sono **rami dello stesso tipo di oggetto** — il modello
Kinaxis. Oggi non lo sono: vivono in tabelle diverse (`scenario` vs `DVERSIONS`), con PK di tipo
diverso, modello di contenuto diverso (sparso con riparto vs denso materializzato), meccanica di
risoluzione diversa (stack `COALESCE` vs lettura diretta) e macchine a stati diverse o assenti.

**Fasatura decisa in questa roadmap** (la decisione di fasatura è presa, non va rilitigata):

**Step A — dentro M1, Phase 13, prima della Phase 15 (workbench). Additivo: non riscrive T4.**
1. **Unificare il puntatore al genitore**: oggi `branch()` ha due meccanismi diversi
   (`base_version_key: int` verso `DVERSIONS`, `parent_scenario_id: str` dentro `scenario`), tenuti
   coerenti **a mano** via `MismatchedBaseVersionError`. Ogni nodo deve avere un solo riferimento al
   genitore, di un solo tipo.
2. **Disaccoppiare le due macchine a stati**: `SCENARIO_STATE` (Draft/Evaluated/Promoted/Discarded)
   e `DVERSIONS.status` (`P`/`R`/`A`/`C`, la fase del ciclo S&OP) sono **assi ortogonali** che oggi
   vivono ciascuno su una sola tabella. Un nodo deve poterli portare entrambi, indipendentemente.
3. **Assorbire T11.1 e T11.2 in questa fase**: la tabella di provenienza della promozione **è**
   l'arco tronco→ramo. Costruirla separatamente e poi di nuovo per R-001 sarebbe lavoro duplicato.
4. **Esporre una sola API uniforme di navigazione/lettura**, così che il workbench veda un solo tipo
   di nodo.
5. `ScenarioStack` / `cache_key()` (`ibp/scenario/models.py:94-109`) **generalizza già
   correttamente**: va esteso, non riscritto.

**Step B — M2, non M1.** Le tre modifiche strutturali (grana di `overlay`/`edits` = grana piena dei
fatti; `promote()` come spostamento di puntatore invece che copia materializzante; risoluzione
ricorsiva fino a una root esplicita) collidono con `DVERSIONS.version_name UNIQUE` letto come
stringa dalle misure DAX di Power BI. Registrate come scope differito, con quella motivazione.
</decision>

</decisions>

## Decisioni chiave (registro di progetto)

| Decisione | Motivazione | Esito |
|---|---|---|
| Migrare da `/software-house` a GSD a T4 completato | Il lavoro residuo ha molte dipendenze di ordinamento e sei pacchetti di debito: serve governo per fasi con gate osservabili, non un altro run monolitico | — In corso |
| R-001 spezzato in Step A (M1, Phase 13) e Step B (M2) | Step A è additivo sopra T4; Step B tocca `version_name UNIQUE`, contratto esterno di Power BI | — In corso |
| T6.0 è una fase a sé, non un pacchetto dentro T6 | Riapre un motore chiuso e verde; il suo gate d'uscita è AC10 (`incrementale ≡ full recalc`) di nuovo verde | — Pendente |
| T11.1 + T11.2 assorbiti nella fase R-001 Step A | La tabella di provenienza *è* l'arco tronco→ramo: costruirla due volte sarebbe lavoro duplicato | — Pendente |
| T10.1 e T11.0 nella stessa fase | Entrambi scrivono in `ibp/scenario/`: non possono correre in parallelo, e T11.0 dipende da T10.1 | — Pendente |
| T11 (workbench) e T12 (CLI+demo) nella stessa fase | Sono lo stesso confine di consegna — il consumo end-to-end della piattaforma — ed entrambi dipendono solo da T10 | — Pendente |
| AC1..AC31 usati come set di requisiti v1 | Sono già il contratto di accettazione approvato, e la suite li mappa uno a uno per nome di file | ✓ Buona |
| Grana del nodo DAG `(manufact_key, region, date_key)` | Senza region il plant eleggibile è indeterminato: produrrebbe un numero plausibile ma sbagliato, in silenzio | — Pendente (Phase 6) |
| `statsforecast==2.1.1` da wheel, extra `[forecast]` separato | La diagnosi "serve MSVC" era sbagliata: il pin `1.7.8` non esiste su PyPI. L'extra resta separato solo perché tira ~11 pacchetti che il resto di M1 non usa | ✓ Buona |
| Nessun mocking nella suite | Il valore dei test sta nel DB reale deterministico: un mock di DuckDB verificherebbe il mock | ✓ Buona |

---
*Ultimo aggiornamento: 2026-09-19, dopo l'ingest della documentazione e la mappatura del codebase (migrazione a GSD).*
