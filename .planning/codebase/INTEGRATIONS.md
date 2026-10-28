# External Integrations

**Analysis Date:** 2026-09-19

## APIs & External Services

**Nessuna integrazione a servizi esterni a runtime (M1, T1–T4).** Il sistema è per costituzione offline (AC25, `README.md`): la connessione DuckDB è aperta con `autoinstall_known_extensions=false` e `autoload_known_extensions=false` proprio per evitare che il primo uso di un'extension provi a scaricarla da internet.

**Pianificate ma non implementate (task futuri, vedi `docs/01-plan-m1.md`):**
- **Adapter Infor/SAP** (T9, owner `sh-data`) — `ibp/adapters/infor_import.py`, `sap_master.py` (directory `ibp/adapters/` non ancora presente su disco). Obiettivo dichiarato: sostituire il path manuale "Excel che scrive sul database" (rischio operativo più concreto identificato nel piano, `docs/01-plan-m1.md` righe 46-56).
- **Export viste Power BI** (T9) — `ibp/adapters/powerbi_export.py` (non ancora presente).
- **Infor writeback** (T9) — `ibp/adapters/infor_writeback.py` (non ancora presente).
- **API HTTP interna** (T10) — `ibp/api/` (router FastAPI, dipendenza `fastapi==0.115.0` già dichiarata in `pyproject.toml` ma nessun modulo la importa ancora).

## Data Storage

**Databases:**
- **DuckDB** (`duckdb==1.1.3`) — unico datastore, file singolo locale `data/ibp.duckdb`.
  - Connessione: nessuna stringa di connessione/env var — path calcolato in `ibp/config.py` (`DB_PATH = DATA_DIR / "ibp.duckdb"`) e riaperto identico da `db/build_db.py`.
  - Client/apertura: punto unico `ibp/db.py` (`connect()` / `session()`) — "Unico punto di apertura di connessioni DuckDB nel package `ibp`" (T2 done_when #5); ogni altro modulo riceve una connessione già aperta, nessuno la apre autonomamente.
  - Modalità: single-writer con lock di processo (nativo DuckDB) — più lettori `read_only=True` possono coesistere, un solo scrittore alla volta. I test usano una connessione read-only sul DB reale (`tests/conftest.py`, fixture `con`) e copie scrivibili in `tmp_path` per i test che devono mutare dati (fixture `writable_db_copy`), per non toccare mai `data/ibp.duckdb`.
  - Rigenerazione: `data/ibp.duckdb` non è mai una fonte di verità persistente da migrare — `python db/build_db.py` lo ricrea da zero ad ogni esecuzione (drop + create + reseed con RNG a seed fisso `SEED = 42` in `db/seed/common.py`), quindi non esiste un path di migrazione incrementale.
  - Il file `.duckdb` e la sua directory temporanea (`data/tmp/`) sono in `.gitignore`: mai committati.

**File Storage:**
- Solo filesystem locale. Nessun object storage (S3, Azure Blob, ecc.).

**Caching:**
- Nessuno strato di cache esterno (Redis, Memcached). Unica forma di "caching" applicativo: fixture pytest `scope="session"` che costruiscono un `RecalcEngine` una sola volta per sessione di test e lo clonano per test (`tests/conftest.py`, fixture `warm_engine`/`engine`), motivata dal costo di un `full_recalculate()` iniziale (decine di secondi).

## Authentication & Identity

**Auth Provider:**
- Nessuno. Non esiste ancora un'API esposta (T10 pendente) né un livello di autenticazione/autorizzazione nel codice attuale.

## Monitoring & Observability

**Error Tracking:**
- Nessun servizio esterno (no Sentry, no Datadog). Gli errori di dominio sono classi Python dedicate: `ibp/domain/errors.py`, `ibp/engine/errors.py`, `ibp/scenario/errors.py`.

**Logs:**
- Nessun framework di logging strutturato rilevato (no `logging` configurato centralmente, no librerie di log esterne). `db/build_db.py` stampa un riepilogo tabelle e l'esito della validazione post-load su stdout durante l'esecuzione.

## CI/CD & Deployment

**Hosting:**
- Non applicabile a M1: nessun deployment, esecuzione locale via `pip install -e .` + `python db/build_db.py`.

**CI Pipeline:**
- Nessuna pipeline CI rilevata nel repository (nessuna directory `.github/workflows/`, nessun `azure-pipelines.yml`, nessun `.gitlab-ci.yml`).

## Environment Configuration

**Required env vars:**
- Nessuna. `ibp/config.py` deriva tutti i path dalla posizione del file (`REPO_ROOT`), senza leggere variabili d'ambiente né segreti.

**Secrets location:**
- Nessun segreto nel progetto: "Nessuna dipendenza da internet a runtime" e "nessun account cloud, nessuna licenza" (AC25, `README.md`). Nessun file `.env` rilevato nel repository.

## Webhooks & Callbacks

**Incoming:**
- Nessuno.

**Outgoing:**
- Nessuno.

---

*Integration audit: 2026-09-19*
