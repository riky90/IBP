# IBP Platform — M1 (ACMELIFT, reference implementation locale)

Sistema di pianificazione IBP: preserva il ciclo P/R/A/C esistente (SAP S/4 →
Infor dEPM → Power BI), ci innesta i due review IBP mancanti (Portfolio,
Integrated Reconciliation), e sostituisce il collo di bottiglia tecnologico
(scenari, ricalcolo, rete produttiva, forecast+FVA, eccezioni).

Il piano approvato è in `docs/01-plan-m1.md`. Questo README copre solo il
setup locale e lo strato dati (`db/`), di competenza del task T1.

## Requisiti

- Python 3.11+ (sviluppato e verificato su 3.13, Windows).
- Nessun servizio esterno, nessun account cloud, nessuna licenza: tutto
  offline (AC25).

## Setup

```powershell
pip install -e .
python db/build_db.py
```

`pip install -e .` installa tutto ciò che serve per M1 (schema, seed, API,
workbench). Lo stack di forecasting che userà T5 (forecast statistico + FVA)
è in un extra separato, non nelle dipendenze base — vedi "Gotcha Windows" per
il motivo:

```powershell
pip install -e ".[forecast]"
```

Il comando ricostruisce `data/ibp.duckdb` **da zero** ad ogni esecuzione:
elimina e ricrea tutte le tabelle, rigenera il seed sintetico con un RNG a
seed fisso, ricarica e valida. Rilanciarlo produce sempre lo stesso
contenuto — non esiste un percorso di migrazione incrementale perché non
c'è un DB reale da preservare: il file è interamente derivato, e in questo
caso "idempotente" significa "riproducibile", non "aggiornato in place".

`data/` (il `.duckdb` e la directory temp di DuckDB) è in `.gitignore`:
non entra mai nel repo.

## Cosa costruisce `db/build_db.py`

1. **Un master di item + il mirror dei fatti dEPM** (`db/schema.sql`):
   `item` (con `role`, `region`, `is_sellable`) sostituisce
   `DSALES_PRODUCT`, `DMANUFACT_KEY` e il layer semilavorati — erano tre
   tabelle per la stessa entità, e il legame fra loro finiva nei suffissi del
   nome (`-BA`, `-BR`, `_Plant`). `item_identifier` tiene le identità datate
   (`element_name`, `caption`, `sap_material`, `legacy`), che è ciò che
   chiude il caption drift e il caso Steyr. I nomi dei fatti restano quelli
   del cubo reale (`TSOP_DEMAND`, `TSOP_OPS`, `TWSC_PAR_CALWEEK`), più
   `DPLANT`, `DSALES_DIVISION`, `DVERSIONS`, `DMEASURE_DEMAND/OPS`,
   `DIM_DATE`; cardinalità isomorfe (~1.661 / ~1.346 / 52 / 62 / ~466).
   `TSOP_OPS` porta la **grana piena**: oltre a manufacturing key e plant
   anche `product_key`, `division_key` e `region`, tutti NOT NULL — è la
   correzione del difetto per cui la conferma finiva sul planning model
   `Dummy` e le coordinate di vendita si ricostruivano pro-rata a posteriori.
2. **Overlay a grafo** (`edge`): archi tipizzati sopra il mirror
   (plant→region con `plant_type`, item→item per ogni `link_type`,
   project→item, assumption→measure, resource→plant). `from_type`/`to_type`
   sono testo libero: M2/M3 aggiungono `dealer`/`importer`/`installer`/
   `supplier` senza migrazione.
3. **Rete produttiva** (`item_link`, `production_eligibility`, `routing`,
   `bill_of_resource`, `resource`, `resource_capacity`): `item_link` è una
   sola tabella di legami tipizzati e datati (`produces`, `aggregates`,
   `splits`, `dependent_demand`) al posto di `product_mapping`. La quota
   degli split è il **mix osservato a consuntivo** (`quota_source =
   'observed_history'`, con `quota_window_months`), non una percentuale
   mantenuta a mano: oltre l'orizzonte dell'orderbook è l'unica base ancorata
   ai fatti. L'override del planner resta possibile e resta distinguibile.
   La domanda dipendente del semilavorato è una riga con `offset_months = 2`,
   non un file Excel che scrive sul DB. I terzisti (`plant_type =
   'subcontractor'`) sono plant con capacità propria: si saturano come gli
   altri, ma sono esterni per dichiarazione.
4. **Scenari** (`scenario`, `edits`, `overlay`): event log append-only e
   overlay con tombstone esplicito (`is_deleted`), mai `NULL` come sentinella.
5. **Forecast e FVA** (`forecast_snapshot`, `forecast_override`,
   `actual_restatement`): snapshot a lag costante su più cicli, cosí lo
   stairstep FVA è ricostruibile a posteriori.
6. **Processo** (`cycle`, `cycle_phase`, `review_instance`, `task`, `raci`,
   `portfolio_item`, `project`, `gap`, `reconciliation_session`, `decision`,
   `escalation`, `rate_card`, `assumption`, `exception_rule`,
   `exception_instance`): ciclo P/R/A/C con i due review mancanti innestati,
   soglie di eccezione marcate provvisorie **nel dato** (`is_provisional`).

Tutti i generatori vivono sotto `db/seed/` (un modulo per area) e sono
orchestrati da `db/build_db.py`. Il volume dei fatti è **deliberatamente
limitato**: si popolano solo gli ultimi cicli storici completi, il ciclo
aperto e il budget dell'anno successivo, non l'intero cubo denso per tutte
le ~466 istanze `DVERSIONS` — le altre esistono come dimensione (isomorfe al
vault) ma senza fatti, coerente con un cubo raramente riletto per intero.

## AC2 — le regole di capacità sono master data, non literal

`Max Slots` (30 sul flow-line, 8 sulle isole), il fattore di granularità e il
layout di ogni plant **non compaiono come literal in nessun file `.py`**:
vivono in `db/seed/data/plant_master.json`. Allo stesso modo le fasi del
ciclo (day range, `stat_state`, gate) vivono in
`db/seed/data/process_phases.json`. Aggiungere un plant o cambiare una
soglia significa editare questi file, non il codice Python.

Nota di scope: l'unica occorrenza residua del carattere `8` nel codice è
l'idioma standard `encoding="utf-8"` (apertura file) — non è un valore di
capacità e non è quello che AC2 intende vietare.

## Gotcha Windows (A6)

- **Nessuna dipendenza da internet a runtime**: la connessione DuckDB è
  aperta con `autoinstall_known_extensions=false` e
  `autoload_known_extensions=false`. Senza questo, il primo utilizzo di
  un'extension proverebbe a scaricarla e romperebbe una demo offline.
- **`temp_directory` esplicito** (`data/tmp/`): DuckDB altrimenti userebbe
  una directory di sistema meno prevedibile su Windows.
- **Escludere `data/` da Windows Defender** se il build risulta lento: lo
  scan realtime su un file DuckDB che cresce per inserimenti bulk è una
  causa comune di rallentamento su Windows, non un problema del codice.
- **DuckDB è single-writer con lock di processo**: se `python db/build_db.py`
  fallisce con un errore di lock, verificare che non ci sia un'altra
  connessione aperta sullo stesso file (es. un notebook, `duckdb` CLI, o il
  server FastAPI di un task successivo).
- **RNG deterministico via `hashlib`, non `hash()`**: l'hash builtin delle
  stringhe di Python è salato per processo (sicurezza) e cambierebbe la
  seed ad ogni esecuzione — `db/seed/common.py` deriva le seed con
  `hashlib.sha256`, non con `hash()`, proprio per restare riproducibile fra
  un run e l'altro.
- **`pyproject.toml` pinna le versioni esatte** (inclusa `polars`, per le
  regressioni di memoria note su Windows in alcune versioni): non
  aggiornarle senza motivo in task successivi a T1.
- **Lo stack di forecasting è un extra separato (`[forecast]`)**, ma *non*
  perché richieda un compilatore. La diagnosi precedente ("`statsforecast`
  non ha wheel per Python 3.13, serve MSVC") era sbagliata: **la versione
  `1.7.8` non esiste su PyPI** — la serie 1.7 si ferma a 1.7.6 e riprende a
  2.0.3. pip non trovava la versione richiesta, ripiegava sulla sdist e
  falliva in compilazione; l'errore MSVC era il sintomo, non la causa. La
  serie 2.x ha sostituito `numba` con `coreforecast` e pubblica wheel
  `cp313-win_amd64`: `statsforecast==2.1.1` + `hierarchicalforecast==1.5.1`
  si installano **solo da wheel**, senza toolchain C++, e non spostano i pin
  di base (`pyarrow` resta 18.1.0). L'extra resta separato per un motivo più
  modesto: tira dentro ~11 pacchetti che M1-M4 non usano.

- **Ordine di import obbligatorio nel codice di forecast (segfault, non
  eccezione)**: `hierarchicalforecast._lib` e `coreforecast`/`utilsforecast`
  sono due estensioni C++ compilate ciascuna col proprio runtime OpenMP.
  Se `utilsforecast` viene caricato per primo nello stesso processo, il
  successivo `import hierarchicalforecast.utils` termina il processo con
  **SIGSEGV senza traceback** — e `hierarchicalforecast/utils.py` importa
  `utilsforecast` *prima* del proprio `_lib`, quindi anche il semplice
  `import hierarchicalforecast.utils` come prima riga del programma va in
  crash. Nessuna variabile d'ambiente lo evita (`OMP_NUM_THREADS=1`,
  `KMP_DUPLICATE_LIB_OK=TRUE`, `MPLBACKEND=Agg`: tutte testate, tutte
  inutili). L'unica cosa che funziona è caricare `_lib` per primo, a mano.
  Il modulo di forecast di T5 deve quindi aprire così, prima di qualsiasi
  altro import del pacchetto:

  ```python
  # DEVE restare la prima riga: due runtime OpenMP nello stesso processo.
  # Se utilsforecast/coreforecast si carica prima, il processo va in segfault.
  from hierarchicalforecast._lib import reconciliation as _hf_lib  # noqa: F401
  ```

  Un test di regressione deve lanciare l'import in un **subprocess** e
  verificare `returncode == 0`: dentro il processo di pytest un segfault non
  è catturabile come eccezione, fa cadere l'intero runner.

- **API di `hierarchicalforecast` 1.x diversa da 0.4.x**:
  `HierarchicalReconciliation.reconcile()` prende `S_df=`, non `S=`. Codice o
  documentazione scritti contro la 0.4.3 non funzionano così com'è.

## Verifica manuale

```powershell
python db/build_db.py
python db/build_db.py   # rilanciato: stesso contenuto, nessun errore
```

Il secondo run stampa lo stesso riepilogo tabelle e la stessa validazione —
`build_db.py` include controlli di integrità post-load (cardinalità attese,
`item_link` che somma a 100 per periodo, presenza dei casi M:N, della
quota da mix osservato, dell'offset di domanda dipendente, dei terzisti con
capacità, di `TSOP_OPS` senza righe orfane di planning item, e dei
due tipi di routing, tombstone presente, ecc.) e si interrompe con un
messaggio esplicito se un'invariante non regge.

## Struttura

```
pyproject.toml          # tutte le dipendenze del programma (M1-M3), una volta sola
db/
  schema.sql            # DDL, mirror dEPM + rete produttiva + scenari + forecast + processo
  build_db.py           # orchestratore: schema -> seed -> load -> validazione
  seed/
    common.py           # RNG deterministico, calendario, helper condivisi
    dimensions.py       # item, item_identifier, DPLANT, DSALES_DIVISION, DVERSIONS, misure, DIM_DATE
    network.py           # item_link, eligibility, routing, bill_of_resource, resource(_capacity)
    facts.py              # TSOP_DEMAND, TSOP_OPS, TWSC_PAR_CALWEEK
    scenario.py            # scenario, edits, overlay
    forecast.py             # forecast_snapshot, forecast_override, actual_restatement
    process.py               # cycle/cycle_phase/review_instance/.../exception_instance
    graph.py                  # edge (overlay a grafo)
    data/                      # master data che il codice legge (AC2): plant_master.json, process_phases.json
data/                          # generato da build_db.py, gitignored
```

## Cosa NON è (ancora) qui

Dominio, semantic layer, motore di ricalcolo, allocatore, API e workbench
sono task successivi (T2–T13, vedi `docs/01-plan-m1.md`). Questo repository
al termine di T1 contiene solo schema + seed: `db/build_db.py` è lo
scheletro su cui gli altri task costruiscono, non un sistema completo.
