"""Fatti: TSOP_DEMAND, TSOP_OPS, TWSC_PAR_CALWEEK.

Scelta di volume (A6 — il vincolo è la latenza, non il cubo denso): non si
materializza il cubo pieno 1.661 x 62 x 24 x N-versioni. Si popolano solo le
versioni "vive" — gli ultimi cicli storici completi, il ciclo corrente aperto
e il budget dell'anno successivo — sulle combinazioni prodotto/division e
manufacturing-key/plant realmente collegate dalla rete produttiva (T1 §3).
Le altre ~450 istanze DVERSIONS esistono come dimensione (isomorfe al vault)
ma senza fatti: coerente con un cubo storico raramente riletto per intero.
"""
from __future__ import annotations

import datetime as dt
import math

import polars as pl

from . import common

# Cicli storici "chiusi" (P/R/A/C tutti presenti) prima del ciclo corrente.
HIST_CLOSED_CYCLES = common.recent_closed_cycles()
CURRENT_CYCLE = common.CURRENT_CYCLE
DEMAND_HORIZON_MONTHS = 6
BUDGET_YEAR_WITH_FACTS = 2027


def _version_lookup(versions: list[dict]) -> dict:
    return {v["version_name"]: v for v in versions}


def _assign_divisions(rng, products: list[dict], divisions: list[dict]) -> dict:
    """Ogni prodotto attivo vende attraverso un piccolo sottoinsieme di division
    (F11: canale interno come livello, non secondo piano — qui il seed si
    limita al livello esterno/region richiesto da M1)."""
    out = {}
    for p in products:
        n = rng.randint(2, 5)
        idx = rng.sample(range(len(divisions)), n)
        out[p["product_key"]] = [divisions[i] for i in idx]
    return out


def build_tsop_demand(rng, products, divisions, dversions, demand_measures):
    version_by_name = _version_lookup(dversions)
    active_products = [p for p in products if p["is_active"]]
    product_divisions = _assign_divisions(rng, active_products, divisions)

    rows = []
    demand_versions = []
    for (y, m) in [*HIST_CLOSED_CYCLES, CURRENT_CYCLE]:
        for status in ("P", "R"):
            demand_versions.append(version_by_name[f"SOP_{y:04d}_{m:02d}_DEMAND_{status}"])

    measure_ids = {k: demand_measures[k] for k in (
        "REQ_PROD", "ORDER_BOOK", "ORDER_ENTRY", "SALES_TO_REMAIN", "SALES_PLAN",
        "FORECAST_BASELINE", "FORECAST_ADJUSTED", "FORECAST_CONSENSUS",
    )}

    for version in demand_versions:
        horizon = common.month_range(
            (version["cycle_year"], version["cycle_month"]),
            common.month_add(version["cycle_year"], version["cycle_month"], DEMAND_HORIZON_MONTHS - 1),
        )
        for prod in active_products:
            base_level = float(rng.uniform(5, 400))
            for division in product_divisions[prod["product_key"]]:
                division_share = float(rng.uniform(0.1, 0.6))
                for h_idx, (hy, hm) in enumerate(horizon):
                    seasonal = 1.0 + 0.15 * math.sin(hm / 12.0 * 2 * math.pi)
                    trend = 1.0 + 0.01 * h_idx
                    qty = max(0.0, base_level * division_share * seasonal * trend
                              * float(rng.gauss(1.0, 0.08)))
                    date_key = common.date_key(hy, hm)
                    values = {
                        "REQ_PROD": qty,
                        "ORDER_BOOK": qty * float(rng.uniform(0.4, 0.9)),
                        "ORDER_ENTRY": qty * float(rng.uniform(0.3, 0.7)),
                        "SALES_TO_REMAIN": qty * float(rng.uniform(0.1, 0.5)),
                        "SALES_PLAN": qty * float(rng.uniform(0.95, 1.05)),
                        "FORECAST_BASELINE": qty * float(rng.uniform(0.85, 1.1)),
                        "FORECAST_ADJUSTED": qty * float(rng.uniform(0.9, 1.15)),
                        "FORECAST_CONSENSUS": qty * float(rng.uniform(0.92, 1.08)),
                    }
                    for code, val in values.items():
                        rows.append((
                            version["version_key"], prod["product_key"], division["division_key"],
                            division["region"], date_key, measure_ids[code], round(val, 3),
                        ))

    # Budget: SOP_BP_<BUDGET_YEAR_WITH_FACTS>, misura BUDGET_VOLUME sui 12 mesi.
    budget_version = version_by_name[f"SOP_BP_{BUDGET_YEAR_WITH_FACTS}"]
    budget_measure = demand_measures["BUDGET_VOLUME"]
    for prod in active_products:
        base_level = float(rng.uniform(5, 400))
        for division in product_divisions[prod["product_key"]]:
            division_share = float(rng.uniform(0.1, 0.6))
            for m in range(1, 13):
                seasonal = 1.0 + 0.15 * math.sin(m / 12.0 * 2 * math.pi)
                qty = max(0.0, base_level * division_share * seasonal * float(rng.gauss(1.0, 0.05)))
                rows.append((
                    budget_version["version_key"], prod["product_key"], division["division_key"],
                    division["region"], common.date_key(BUDGET_YEAR_WITH_FACTS, m),
                    budget_measure, round(qty, 3),
                ))

    df = pl.DataFrame(
        rows,
        schema=["version_key", "product_key", "division_key", "region", "date_key",
                "measure_key", "value"],
        orient="row",
    ).unique(subset=["version_key", "product_key", "division_key", "date_key", "measure_key"], keep="last")
    return df, product_divisions


def _production_sites(scenario_refs) -> dict:
    """manufact_key -> lista di plant dove viene prodotto (>=2 per i casi di
    routing multi-step, AC6/AC7)."""
    sites: dict[int, list[dict]] = {}
    for mk_key, plant in scenario_refs["generic_home_region"].items():
        sites[mk_key] = [plant]

    ganderkesee_cerritos = [scenario_refs["mandatory_key"]]
    return sites, ganderkesee_cerritos


def build_sales_coordinates(item_link: pl.DataFrame, product_divisions: dict,
                             product_keys: set[int]) -> dict:
    """Per ogni item di produzione, le coordinate di vendita che il supply plan
    deve portare: (product_key, division_key, region).

    È la correzione del difetto misurato: nell'export la conferma è scritta a
    manufacturing key x plant e il planning model finisce a `Dummy` su tutte e
    1.080 le righe, per poi essere ricostruito pro-rata dopo il fatto. Qui la
    coordinata si risolve *prima* di scrivere, seguendo item_link — inclusa la
    catena della domanda dipendente, dove il semilavorato eredita il planning
    model del finito che lo tira."""
    direct: dict[int, int] = {}
    dependent: dict[int, int] = {}
    for r in item_link.iter_rows(named=True):
        to_item, from_item = r["to_item"], r["from_item"]
        if r["link_type"] == "dependent_demand":
            dependent.setdefault(to_item, from_item)
        elif from_item in product_keys:
            # deterministico: a parità di legami vince il planning model più basso
            if to_item not in direct or from_item < direct[to_item]:
                direct[to_item] = from_item

    def resolve(item_key: int, depth: int = 0) -> int | None:
        if item_key in direct:
            return direct[item_key]
        if depth < 4 and item_key in dependent:
            return resolve(dependent[item_key], depth + 1)
        return None

    out = {}
    for item_key in {*direct.keys(), *dependent.keys()}:
        product_key = resolve(item_key)
        if product_key is None:
            continue
        divisions = product_divisions.get(product_key)
        if not divisions:
            continue
        division = divisions[0]
        out[item_key] = (product_key, division["division_key"], division["region"])
    return out


def build_tsop_ops(rng, manufact_keys, plants, dversions, ops_measures, scenario_refs,
                    sales_coordinates: dict) -> pl.DataFrame:
    version_by_name = _version_lookup(dversions)
    plant_by_code = {p["plant_code"]: p for p in plants}
    manufact_by_key = {m["manufact_key"]: m for m in [*manufact_keys, *scenario_refs["semi_items"]]}

    sites, _ = _production_sites(scenario_refs)
    mandatory_key = scenario_refs["mandatory_key"]["manufact_key"]
    elective_key = scenario_refs["elective_key"]["manufact_key"]
    sites[mandatory_key] = [plant_by_code["DE-GANDERKESEE"], plant_by_code["US-CERRITOS"]]
    sites[elective_key] = [plant_by_code["AT-NORTHFIELD"], plant_by_code["CA-NIAGARA"]]
    for semi in scenario_refs["semi_items"]:
        sites[semi["item_key"]] = [plant_by_code[semi["home_plant_code"]]]
    for sub, mk in zip(scenario_refs["subcontractors"], scenario_refs["subcontracted_keys"]):
        sites.setdefault(mk["manufact_key"], []).append(sub)

    ops_versions = []
    for (y, m) in HIST_CLOSED_CYCLES:
        for status in ("A", "C"):
            ops_versions.append(version_by_name[f"SOP_{y:04d}_{m:02d}_SUPPLY_{status}"])

    mid = {k: ops_measures[k] for k in (
        "PROD_UNITS", "AVG_MAX_CAPACITY", "CAPACITY_UTIL", "WEEKS_PRODUCTION",
        "SLOTS_REQUESTED", "SLOTS_AVAILABLE", "SLOTS_CURRENT_MONTH", "SLOTS_PREVIOUS_MONTH",
        "INVENTORY", "FMS", "PLANT_RELIABILITY", "ORDER_BACKLOG", "FROZEN_ZONE",
        "ASSEMBLY_HOURS_CONSUMED", "ASSEMBLY_HOURS_CAPACITY",
    )}

    rows = []
    for version in ops_versions:
        horizon = common.month_range(
            (version["cycle_year"], version["cycle_month"]),
            common.month_add(version["cycle_year"], version["cycle_month"], DEMAND_HORIZON_MONTHS - 1),
        )
        for mk_key, mk_plants in sites.items():
            mk = manufact_by_key[mk_key]
            coord = sales_coordinates.get(mk_key)
            if coord is None:
                # Nessuna coordinata di vendita risolvibile: la riga non si
                # scrive. È la regola che sostituisce `Dummy` — meglio un buco
                # dichiarato che una conferma da riallocare a posteriori.
                continue
            product_key, division_key, region = coord
            for plant in mk_plants:
                base_units = float(rng.uniform(1, 25))
                for (hy, hm) in horizon:
                    date_key = common.date_key(hy, hm)
                    units_per_day = max(0.1, base_units * float(rng.gauss(1.0, 0.1)))
                    max_capacity = units_per_day * float(rng.uniform(1.1, 1.4))
                    util = min(1.0, units_per_day / max_capacity)
                    weeks_production = float(rng.uniform(0.5, plant["slot_granularity_factor"] * 1.5))
                    granularity = plant["slot_granularity_factor"]
                    current_share = min(1.0, weeks_production / granularity)
                    previous_share = max(0.0, (weeks_production - granularity) / granularity)
                    slots = units_per_day * mk["slot_equivalence_factor"] * float(rng.uniform(0.02, 0.06))

                    values = {
                        "PROD_UNITS": units_per_day,
                        "AVG_MAX_CAPACITY": max_capacity,
                        "CAPACITY_UTIL": util,
                        "WEEKS_PRODUCTION": weeks_production,
                        "SLOTS_REQUESTED": slots,
                        "SLOTS_AVAILABLE": float(plant["max_slots"]),
                        "SLOTS_CURRENT_MONTH": slots * current_share,
                        "SLOTS_PREVIOUS_MONTH": slots * previous_share,
                        "INVENTORY": units_per_day * float(rng.uniform(2, 12)),
                        "FMS": units_per_day * float(rng.uniform(0, 3)),
                        "PLANT_RELIABILITY": float(rng.uniform(0.80, 0.99)),
                        "ORDER_BACKLOG": units_per_day * float(rng.uniform(1, 6)),
                        "FROZEN_ZONE": float(rng.uniform(1, 3)),
                    }
                    if plant["layout_type"] == "assembly_island":
                        consumed = units_per_day * mk["average_assembly_hours"]
                        values["ASSEMBLY_HOURS_CONSUMED"] = consumed
                        values["ASSEMBLY_HOURS_CAPACITY"] = consumed * float(rng.uniform(1.1, 1.5))

                    for code, val in values.items():
                        rows.append((
                            version["version_key"], mk_key, plant["plant_key"],
                            product_key, division_key, region,
                            date_key, mid[code], round(float(val), 4),
                        ))

    key_cols = ["version_key", "manufact_key", "plant_key", "product_key",
                "division_key", "date_key", "measure_key"]
    return pl.DataFrame(
        rows,
        schema=["version_key", "manufact_key", "plant_key", "product_key",
                "division_key", "region", "date_key", "measure_key", "value"],
        orient="row",
    ).unique(subset=key_cols, keep="last")


def build_twsc_par_calweek(rng, manufact_keys, plants, dversions, ops_measures, scenario_refs) -> pl.DataFrame:
    """Parametro settimanale (Weeks Production) alla base dello spread a due
    mesi — sostituisce l'Excel che oggi scrive sul DB (AC9)."""
    version_by_name = _version_lookup(dversions)
    plant_by_code = {p["plant_code"]: p for p in plants}
    manufact_by_key = {m["manufact_key"]: m for m in manufact_keys}
    weeks_measure = ops_measures["WEEKS_PRODUCTION"]

    sites, _ = _production_sites(scenario_refs)
    mandatory_key = scenario_refs["mandatory_key"]["manufact_key"]
    elective_key = scenario_refs["elective_key"]["manufact_key"]
    sites[mandatory_key] = [plant_by_code["DE-GANDERKESEE"], plant_by_code["US-CERRITOS"]]
    sites[elective_key] = [plant_by_code["AT-NORTHFIELD"], plant_by_code["CA-NIAGARA"]]

    version = version_by_name[f"SOP_{CURRENT_CYCLE[0]:04d}_{CURRENT_CYCLE[1]:02d}_SUPPLY_A"]
    cal_start = dt.date(CURRENT_CYCLE[0], CURRENT_CYCLE[1], 1)
    calweek_count = 9  # ~2 mesi di settimane di calendario
    calweeks = [cal_start + dt.timedelta(weeks=w) for w in range(calweek_count)]

    rows = []
    for mk_key, mk_plants in sites.items():
        mk = manufact_by_key[mk_key]
        for plant in mk_plants:
            for cw in calweeks:
                weeks_val = float(rng.uniform(0.5, plant["slot_granularity_factor"] * 1.4))
                rows.append((
                    version["version_key"], mk_key, plant["plant_key"], cw, weeks_measure,
                    round(weeks_val, 3),
                ))
    return pl.DataFrame(
        rows,
        schema=["version_key", "manufact_key", "plant_key", "calweek_date", "measure_key", "value"],
        orient="row",
    ).unique(subset=["version_key", "manufact_key", "plant_key", "calweek_date", "measure_key"], keep="last")
