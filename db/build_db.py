#!/usr/bin/env python
"""Ricostruisce data/ibp.duckdb da zero, in modo idempotente, con lo schema
mirror dEPM + rete produttiva + scenari + forecast/FVA + processo (M1).

Uso:
    python db/build_db.py

Rigirarlo produce sempre lo stesso contenuto (stesso RNG seed, stessa
cardinalità, stesse relazioni): il file viene ricreato da zero ad ogni run,
non aggiornato in place — è la definizione di idempotenza più semplice da
verificare e la più sicura quando i dati sono sintetici (nessuna perdita
possibile, a differenza di una migrazione contro dati reali).
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import polars as pl

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from db.seed import common, dimensions, facts, forecast, graph, network, process, scenario  # noqa: E402

DB_PATH = REPO_ROOT / "data" / "ibp.duckdb"
TEMP_DIR = REPO_ROOT / "data" / "tmp"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _connect() -> duckdb.DuckDBPyConnection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    # AC25: tutto offline. L'autoload delle extension richiede internet — lo
    # disattiviamo esplicitamente cosi' il build non dipende dalla rete.
    con = duckdb.connect(
        str(DB_PATH),
        config={
            "autoinstall_known_extensions": "false",
            "autoload_known_extensions": "false",
            "temp_directory": str(TEMP_DIR),
        },
    )
    return con


def _rebuild_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Rimuove ogni tabella preesistente e ricrea lo schema da zero: e' questo
    che rende `build_db.py` idempotente senza dover mantenere un percorso di
    migrazione incrementale per un DB generato interamente da seed sintetico."""
    existing = [r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()]
    for table in existing:
        con.execute(f'DROP TABLE IF EXISTS "{table}"')
    con.execute(SCHEMA_PATH.read_text(encoding="utf-8"))


def _load(con: duckdb.DuckDBPyConnection, table: str, df: pl.DataFrame) -> None:
    if df.height == 0:
        print(f"  [WARN] {table}: 0 righe generate (tabella creata ma vuota)")
        return
    columns = [r[0] for r in con.execute(f'DESCRIBE "{table}"').fetchall()]
    missing = set(columns) - set(df.columns)
    if missing:
        raise RuntimeError(f"{table}: colonne mancanti nel DataFrame generato: {missing}")
    col_list = ", ".join(f'"{c}"' for c in columns)
    con.register("_stage", df.to_arrow())
    con.execute(f'INSERT INTO "{table}" ({col_list}) SELECT {col_list} FROM _stage')
    con.unregister("_stage")
    print(f"  {table}: {df.height} righe")


def _stamp_base_snapshots(con: duckdb.DuckDBPyConnection) -> int:
    """Sostituisce il sentinella `PENDING_DIGEST` con la vera impronta di
    contenuto della base di ogni scenario seminato.

    Perché qui e non nel seed: `base_content_digest()` legge TSOP_DEMAND/
    TSOP_OPS, che a `scenario.build_scenarios()` time non sono ancora in DB.
    Perché importando `ibp.scenario.overlay` invece di riscrivere l'hash:
    `branch()` e `promote()` usano quella funzione, e AC16 è un confronto fra
    due digest — due implementazioni dello stesso algoritmo sono due verità
    che divergono al primo cambio di `ORDER BY`. Il seed deve produrre
    `base_snapshot_id` nel **formato canonico** `SNAP_{version_key}_{sha256}`
    (`promote._SNAPSHOT_RE`), altrimenti `_snapshot_check()` li dichiara non
    verificabili e AC16 passa a vuoto sugli unici scenari promuovibili che
    spediamo.
    """
    from ibp.scenario.overlay import base_content_digest

    pending = con.execute(
        "SELECT scenario_id, base_version_key FROM scenario "
        "WHERE base_snapshot_id = ? ORDER BY scenario_id",
        [scenario.PENDING_DIGEST],
    ).fetchall()
    digest_by_version: dict[int, str] = {}
    for scenario_id, base_version_key in pending:
        if base_version_key not in digest_by_version:
            digest_by_version[base_version_key] = base_content_digest(con, base_version_key)
        con.execute(
            "UPDATE scenario SET base_snapshot_id = ? WHERE scenario_id = ?",
            [f"SNAP_{base_version_key}_{digest_by_version[base_version_key]}", scenario_id],
        )
    print(f"  scenario.base_snapshot_id: {len(pending)} impronte calcolate "
          f"({len(digest_by_version)} basi distinte)")
    return len(pending)


def _validate(con: duckdb.DuckDBPyConnection) -> None:
    """Controlli di integrità post-load. Un fallimento qui interrompe il build
    (fail the batch): un seed "isomorfo" sbagliato è peggio di un build che si
    ferma con un messaggio chiaro."""
    checks: list[tuple[str, str, object]] = [
        ("item", "SELECT count(*) FROM item", dimensions.N_ITEMS),
        ("item planning_model", "SELECT count(*) FROM item WHERE role = 'planning_model'",
         dimensions.N_PRODUCTS),
        ("item manufacturing_key", "SELECT count(*) FROM item WHERE role = 'manufacturing_key'",
         dimensions.N_MANUFACT),
        ("DPLANT", "SELECT count(*) FROM DPLANT", dimensions.N_PLANTS),
        ("DSALES_DIVISION", "SELECT count(*) FROM DSALES_DIVISION", dimensions.N_DIVISIONS),
    ]
    for name, sql, expected in checks:
        got = con.execute(sql).fetchone()[0]
        if got != expected:
            raise RuntimeError(f"Cardinalità inattesa per {name}: atteso {expected}, ottenuto {got}")

    # Ogni item ha almeno un element_name, e nessun identificatore è orfano.
    missing_name = con.execute(
        "SELECT count(*) FROM item i WHERE NOT EXISTS ("
        "  SELECT 1 FROM item_identifier d WHERE d.item_key = i.item_key"
        "  AND d.id_type = 'element_name')"
    ).fetchone()[0]
    if missing_name:
        raise RuntimeError(f"item_identifier: {missing_name} item senza element_name")
    orphan_ident = con.execute(
        "SELECT count(*) FROM item_identifier d "
        "WHERE NOT EXISTS (SELECT 1 FROM item i WHERE i.item_key = d.item_key)"
    ).fetchone()[0]
    if orphan_ident:
        raise RuntimeError(f"item_identifier: {orphan_ident} righe orfane")

    # Il caso Steyr: deve esistere almeno un'identità chiusa nel tempo, o la
    # storia dei cicli passati resterebbe riscrivibile.
    closed_identities = con.execute(
        "SELECT count(*) FROM item_identifier WHERE valid_to IS NOT NULL"
    ).fetchone()[0]
    if closed_identities == 0:
        raise RuntimeError("item_identifier: nessuna identità chiusa (valid_to) — il caso Steyr non è coperto")

    # Il semilavorato esiste come item non vendibile, non come planning model mancante.
    semi = con.execute(
        "SELECT count(*) FROM item WHERE role = 'semi_finished' AND is_sellable = FALSE"
    ).fetchone()[0]
    if semi != dimensions.N_SEMI:
        raise RuntimeError(f"item: attesi {dimensions.N_SEMI} semilavorati non vendibili, trovati {semi}")

    # La region è un attributo: devono esistere planning model regionali, o i
    # suffissi -BA/-BR resterebbero l'unico modo per esprimerla.
    regional = con.execute(
        "SELECT count(*) FROM item WHERE role = 'planning_model' AND region <> 'GLOBAL'"
    ).fetchone()[0]
    if regional == 0:
        raise RuntimeError("item: nessun planning model con region propria (i suffissi -BA/-BR non sono sostituiti)")

    # base_snapshot_id: formato canonico e digest che combacia col contenuto
    # corrente della base. Senza questo, AC16 (promozione con base mossa ->
    # conflitto) passa a vuoto sugli scenari seminati, che sono gli unici
    # promuovibili spediti e quelli che la demo di T12 attraversa.
    import re as _re

    from ibp.scenario.overlay import base_content_digest as _digest

    _canonical = _re.compile(r"^SNAP_(-?\d+)_([0-9a-f]{64})$")
    bad_format = []
    for scenario_id, base_version_key, base_snapshot_id in con.execute(
        "SELECT scenario_id, base_version_key, base_snapshot_id FROM scenario "
        "ORDER BY scenario_id"
    ).fetchall():
        m = _canonical.match(base_snapshot_id or "")
        if m is None:
            bad_format.append((scenario_id, base_snapshot_id))
            continue
        if int(m.group(1)) != base_version_key:
            bad_format.append((scenario_id, f"version_key {m.group(1)} != {base_version_key}"))
            continue
        if m.group(2) != _digest(con, base_version_key):
            bad_format.append((scenario_id, "digest non combacia col contenuto della base"))
    if bad_format:
        raise RuntimeError(
            "scenario.base_snapshot_id non verificabile per AC16: " f"{bad_format}"
        )

    # item_link: ogni (from_item, link_type, period) deve sommare a 100 (F7).
    bad = con.execute(
        "SELECT from_item, link_type, period, sum(quota_pct) AS total FROM item_link "
        "GROUP BY from_item, link_type, period HAVING abs(sum(quota_pct) - 100.0) > 0.01"
    ).fetchall()
    if bad:
        raise RuntimeError(f"item_link: {len(bad)} (from_item, link_type, period) non sommano a 100: {bad[:5]}")

    # M:N in entrambe le direzioni (AC4).
    one_to_many = con.execute(
        "SELECT from_item FROM item_link WHERE link_type = 'splits' "
        "GROUP BY from_item, period HAVING count(DISTINCT to_item) > 1 LIMIT 1"
    ).fetchall()
    many_to_one = con.execute(
        "SELECT to_item FROM item_link WHERE link_type = 'aggregates' "
        "GROUP BY to_item, period HAVING count(DISTINCT from_item) > 1 LIMIT 1"
    ).fetchall()
    if not one_to_many:
        raise RuntimeError("item_link: nessun caso 'splits' 1 -> N trovato")
    if not many_to_one:
        raise RuntimeError("item_link: nessun caso 'aggregates' N -> 1 trovato")

    # Domanda dipendente: il legame col semilavorato porta l'offset nel dato
    # (F10), non in un file Excel a valle.
    dependent = con.execute(
        "SELECT count(*) FROM item_link WHERE link_type = 'dependent_demand' AND offset_months <> 0"
    ).fetchone()[0]
    if dependent == 0:
        raise RuntimeError("item_link: nessun legame 'dependent_demand' con offset — F10 non è nel dato")

    # La quota degli split è misurata, non mantenuta a mano (decisione 2026-09-10).
    observed = con.execute(
        "SELECT count(*) FROM item_link WHERE quota_source = 'observed_history' "
        "AND quota_window_months IS NOT NULL"
    ).fetchone()[0]
    if observed == 0:
        raise RuntimeError("item_link: nessuna quota da mix osservato (quota_source='observed_history')")

    override_rows = con.execute(
        "SELECT count(*) FROM item_link WHERE quota_source = 'manual_override'"
    ).fetchone()[0]
    if override_rows == 0:
        raise RuntimeError("item_link: nessun override manuale tracciato (quota_source='manual_override')")

    # routing: entrambi i casi (AC6/AC7).
    mandatory = con.execute("SELECT count(*) FROM routing WHERE mandatory = TRUE").fetchone()[0]
    elective = con.execute(
        "SELECT count(DISTINCT variant_key) FROM routing WHERE mandatory = FALSE"
    ).fetchone()[0]
    if mandatory == 0:
        raise RuntimeError("routing: nessun routing obbligatorio (mandatory=TRUE) trovato")
    if elective < 2:
        raise RuntimeError("routing: meno di 2 variant_key elettivi trovati (serve almeno A e B)")

    # tombstone esplicito (A7 — mai NULL come sentinella non dichiarata).
    tombstones = con.execute("SELECT count(*) FROM overlay WHERE is_deleted = TRUE").fetchone()[0]
    if tombstones == 0:
        raise RuntimeError("overlay: nessun tombstone (is_deleted=TRUE) trovato nel seed")

    # forecast a lag costante su >= 2 cicli (AC18).
    created_cycles = con.execute("SELECT count(DISTINCT created_period) FROM forecast_snapshot").fetchone()[0]
    if created_cycles < 2:
        raise RuntimeError("forecast_snapshot: meno di 2 created_period distinti (serve per l'FVA a lag costante)")

    # DVERSIONS: naming e cardinalità isomorfe al vault.
    dv_count = con.execute("SELECT count(*) FROM DVERSIONS").fetchone()[0]
    if not (400 <= dv_count <= 550):
        raise RuntimeError(f"DVERSIONS: cardinalità non isomorfa al vault (~466), ottenuto {dv_count}")
    budget_2027 = con.execute(
        "SELECT count(*) FROM DVERSIONS WHERE version_name = 'SOP_BP_2027'"
    ).fetchone()[0]
    if budget_2027 != 1:
        raise RuntimeError("DVERSIONS: SOP_BP_2027 mancante")

    # Terzisti: sono plant con capacità propria (slot e ore) e sono dichiarati
    # esterni. Se avessero capacità zero sarebbero sorgenti infinite e il piano
    # non saprebbe mai che il conto lavoro è pieno.
    subs = con.execute("SELECT count(*) FROM DPLANT WHERE plant_type = 'subcontractor'").fetchone()[0]
    if subs == 0:
        raise RuntimeError("DPLANT: nessun terzista (plant_type='subcontractor')")
    subs_no_capacity = con.execute(
        "SELECT count(*) FROM DPLANT WHERE plant_type = 'subcontractor' AND max_slots <= 0"
    ).fetchone()[0]
    if subs_no_capacity:
        raise RuntimeError(f"DPLANT: {subs_no_capacity} terzisti senza capacità")
    subs_no_resource = con.execute(
        "SELECT count(*) FROM DPLANT p WHERE p.plant_type = 'subcontractor' AND NOT EXISTS ("
        "  SELECT 1 FROM resource r WHERE r.node_key = CAST(p.plant_key AS VARCHAR))"
    ).fetchone()[0]
    if subs_no_resource:
        raise RuntimeError(f"resource: {subs_no_resource} terzisti senza pool di capacità")

    # Grana piena del supply plan: nessuna riga senza coordinate di vendita.
    # È il controllo che rende impossibile il ritorno di `Dummy`.
    ops_orphans = con.execute(
        "SELECT count(*) FROM TSOP_OPS o WHERE NOT EXISTS ("
        "  SELECT 1 FROM item i WHERE i.item_key = o.product_key AND i.role = 'planning_model')"
    ).fetchone()[0]
    if ops_orphans:
        raise RuntimeError(f"TSOP_OPS: {ops_orphans} righe senza planning item valido")
    ops_regions = con.execute("SELECT count(DISTINCT region) FROM TSOP_OPS").fetchone()[0]
    if ops_regions == 0:
        raise RuntimeError("TSOP_OPS: nessuna region valorizzata")

    # Manufacturing category deve includere i Cluster richiesti dal vault.
    required_clusters = {f"Cluster {n}" for n in (10, 11, 12, 13, 14, 15, 31, 32, 33, 38)}
    present = {r[0] for r in con.execute(
        "SELECT DISTINCT manufacturing_category FROM item WHERE role = 'manufacturing_key'"
    ).fetchall()}
    missing_clusters = required_clusters - present
    if missing_clusters:
        raise RuntimeError(f"item: manufacturing_category mancanti: {missing_clusters}")

    # AC3: Average Assembly Hours ha un consumatore reale in bill_of_resource/TSOP_OPS.
    hour_bor = con.execute("SELECT count(*) FROM bill_of_resource WHERE resource_id LIKE 'HOUR::%'").fetchone()[0]
    hour_fact = con.execute(
        "SELECT count(*) FROM TSOP_OPS t JOIN DMEASURE_OPS m ON t.measure_key = m.measure_key "
        "WHERE m.measure_code = 'ASSEMBLY_HOURS_CONSUMED'"
    ).fetchone()[0]
    if hour_bor == 0 or hour_fact == 0:
        raise RuntimeError("Average Assembly Hours: nessun consumatore reale trovato (AC3)")

    print("Validazione OK:", ", ".join(f"{n}={con.execute(s).fetchone()[0]}" for n, s, _ in checks))


def main() -> None:
    print(f"Ricostruzione DB: {DB_PATH}")
    con = _connect()
    try:
        _rebuild_schema(con)

        print("Dimensioni...")
        ctx = dimensions.build_all()
        _load(con, "DIM_DATE", ctx.dim_date)
        _load(con, "item", ctx.item)
        _load(con, "item_identifier", ctx.item_identifier)
        _load(con, "DPLANT", ctx.dplant)
        _load(con, "DSALES_DIVISION", ctx.dsales_division)
        _load(con, "DVERSIONS", ctx.dversions)
        _load(con, "DMEASURE_DEMAND", ctx.dmeasure_demand)
        _load(con, "DMEASURE_OPS", ctx.dmeasure_ops)

        print("Rete produttiva...")
        rng_network = common.new_rng("network")
        network_tables, scenario_refs = network.build_network(
            rng_network, ctx.products, ctx.manufact_keys, ctx.plants, ctx.semi_items,
        )
        for name in ("item_link", "production_eligibility", "routing",
                     "resource", "resource_capacity", "bill_of_resource"):
            _load(con, name, network_tables[name])

        print("Fatti...")
        rng_facts = common.new_rng("facts")
        tsop_demand, product_divisions = facts.build_tsop_demand(
            rng_facts, ctx.products, ctx.divisions, ctx.versions, ctx.demand_measures)
        _load(con, "TSOP_DEMAND", tsop_demand)
        rng_ops = common.new_rng("ops")
        sales_coordinates = facts.build_sales_coordinates(
            network_tables["item_link"], product_divisions,
            {p["product_key"] for p in ctx.products},
        )
        tsop_ops = facts.build_tsop_ops(rng_ops, ctx.manufact_keys, ctx.plants,
                                         ctx.versions, ctx.ops_measures, scenario_refs,
                                         sales_coordinates)
        _load(con, "TSOP_OPS", tsop_ops)
        rng_wsc = common.new_rng("wsc")
        twsc = facts.build_twsc_par_calweek(rng_wsc, ctx.manufact_keys, ctx.plants,
                                             ctx.versions, ctx.ops_measures, scenario_refs)
        _load(con, "TWSC_PAR_CALWEEK", twsc)

        print("Scenari...")
        scenario_tables = scenario.build_scenarios(ctx.versions, ctx.divisions,
                                                     ctx.demand_measures, scenario_refs)
        for name in ("scenario", "edits", "overlay"):
            _load(con, name, scenario_tables[name])
        _stamp_base_snapshots(con)

        print("Forecast e FVA...")
        rng_forecast = common.new_rng("forecast")
        forecast_tables = forecast.build_forecast(rng_forecast, ctx.products)
        for name in ("forecast_snapshot", "forecast_override", "actual_restatement"):
            _load(con, name, forecast_tables[name])

        print("Processo (P/R/A/C + i due review)...")
        rng_process = common.new_rng("process")
        process_tables, _cycle_id_by_ym = process.build_process(
            rng_process, ctx.products, ctx.plants, ctx.manufact_keys,
            ctx.demand_measures, ctx.ops_measures,
        )
        for name in ("cycle", "cycle_phase", "review_instance", "task", "raci",
                      "portfolio_item", "project", "project_resource_demand",
                      "portfolio_decision", "gap", "reconciliation_session",
                      "decision", "escalation", "rate_card", "assumption",
                      "exception_rule", "exception_instance"):
            _load(con, name, process_tables[name])

        print("Overlay a grafo...")
        edges = graph.build_edges(
            ctx.plants, network_tables["item_link"], network_tables["resource"],
            process_tables["project"].to_dicts(), process_tables["portfolio_item"].to_dicts(),
            process_tables["assumption"].to_dicts(),
        )
        _load(con, "edge", edges)

        print("Validazione...")
        _validate(con)
        print("Build completato.")
    finally:
        con.close()


if __name__ == "__main__":
    main()
