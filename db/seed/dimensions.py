"""Dimensioni: il master unico `item` (+ `item_identifier`), DPLANT,
DSALES_DIVISION, DVERSIONS, DMEASURE_DEMAND, DMEASURE_OPS, DIM_DATE.

Cardinalità target isomorfe al vault (vedi docs/01-plan-m1.md):
~1.661 planning model, ~1.346 manufacturing key, 52 DPLANT, 62 DSALES_DIVISION,
~466 DVERSIONS.

`item` è un solo master con un `role`: planning model, manufacturing key e
semilavorato sono lo stesso tipo di entità con ruoli diversi. Le chiavi vivono
in un unico keyspace, quindi `product_key` e `manufact_key` dei fatti sono
entrambi `item.item_key` — è ciò che rende esprimibile un legame fra due item
qualsiasi (`item_link`) invece di una tabella di mapping fra due dimensioni.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path

import polars as pl

from . import common

DATA_DIR = Path(__file__).parent / "data"

N_PRODUCTS = 1661
N_MANUFACT = 1346
N_PLANTS = 52
N_DIVISIONS = 62

# I tre semilavorati veri dell'export: Basic Assemblies CL2&3 / CL4 / CL5,
# tutti a Northfield, tutti senza planning model *per costruzione* — il
# pre-assemblaggio non si vende. Qui sono item con role='semi_finished' e
# is_sellable=false: non un planning model mancante, un item non vendibile.
SEMI_FINISHED = [
    ("Basic Assemblies CL2 & 3", "AT-NORTHFIELD"),
    ("Basic Assemblies CL4", "AT-NORTHFIELD"),
    ("Basic Assemblies CL5", "AT-NORTHFIELD"),
]
N_SEMI = len(SEMI_FINISHED)
N_ITEMS = N_PRODUCTS + N_MANUFACT + N_SEMI

# Quota di planning model con una region propria invece di 'GLOBAL'. Sull'export
# sono 32 su 685 (~4,7%) i modelli che portano (NAM)/(LATAM) nel *nome*: qui la
# stessa quota diventa un attributo, ed è la ragione per cui i suffissi -BA/-BR
# sui manufacturing key non servono più.
REGIONAL_MODEL_SHARE = 0.047
REGIONAL_MODEL_REGIONS = ["NAM", "LATAM"]

# Caption drift: sull'export il caption coincide con l'element name solo sul 76%
# delle righe supply. Il 24% restante non è un legame mancante, è un secondo
# identificatore dello stesso item — e qui è esattamente questo.
CAPTION_DRIFT_SHARE = 0.24

# Il caso Steyr: un attributo di identità cambiato in place riscrive la storia
# dei cicli passati. Qui il cambio è una riga chiusa con valid_to più una nuova
# riga aperta, quindi il passato resta leggibile com'era.
N_RESTATED_IDENTITIES = 9
IDENTITY_EPOCH = dt.date(2019, 1, 1)
IDENTITY_RESTATED_AT = dt.date(2025, 7, 1)

PRODUCT_DIVISIONS = [
    "Loader Cranes", "Truck Mounted Forklifts", "Tail Lifts", "Marine Cranes",
    "Timber & Recycling", "Railway Systems", "Access Platforms", "Truck Bodies",
    "Hooklifts", "Cable Winches", "Special Vehicles", "Structural Access",
    "Container Handling", "Aftermarket & Services",
]
assert len(PRODUCT_DIVISIONS) == 14

# Catalogo globale delle Manufacturing Category: deve includere i Cluster
# 10-15, 31-33, 38 citati dal vault, più qualche categoria non-cluster.
MANUFACTURING_CATEGORIES = (
    [f"Cluster {n}" for n in [10, 11, 12, 13, 14, 15, 31, 32, 33, 38]]
    + ["Standard Assembly", "Special Build", "Semi-Finished", "Kit & Options"]
)

# AC2: capacita' di plant (layout, max slot, granularita') e' master data letta
# da db/seed/data/plant_master.json — zero literal di capacita' in questo file.
PLANT_MASTER = json.loads((DATA_DIR / "plant_master.json").read_text(encoding="utf-8"))
LAYOUT_CAPACITY = PLANT_MASTER["layout_capacity"]
SUBCONTRACTOR_CAPACITY = PLANT_MASTER["subcontractor_capacity"]
GRANULARITY_VARIANTS = PLANT_MASTER["granularity_variants"]
NAMED_PLANTS = PLANT_MASTER["named_plants"]
PLANT_REGION_TOTALS = PLANT_MASTER["region_totals"]
assert sum(PLANT_REGION_TOTALS.values()) == N_PLANTS

DIVISION_REGION_TOTALS = {"EMEA": 28, "NAM": 12, "APAC": 10, "LATAM": 7, "CIS": 5}
assert sum(DIVISION_REGION_TOTALS.values()) == N_DIVISIONS


@dataclass
class SeedContext:
    """Bundle di DataFrame + lookup python-side riusati dagli altri generatori."""

    dim_date: pl.DataFrame
    item: pl.DataFrame
    item_identifier: pl.DataFrame
    dplant: pl.DataFrame
    dsales_division: pl.DataFrame
    dversions: pl.DataFrame
    dmeasure_demand: pl.DataFrame
    dmeasure_ops: pl.DataFrame

    products: list[dict] = field(default_factory=list)
    manufact_keys: list[dict] = field(default_factory=list)
    semi_items: list[dict] = field(default_factory=list)
    plants: list[dict] = field(default_factory=list)
    divisions: list[dict] = field(default_factory=list)
    versions: list[dict] = field(default_factory=list)
    demand_measures: dict = field(default_factory=dict)
    ops_measures: dict = field(default_factory=dict)


def build_dim_date() -> pl.DataFrame:
    rows = []
    for y, m in common.month_range(common.DIM_DATE_START, common.DIM_DATE_END):
        rows.append(dict(
            date_key=common.date_key(y, m),
            date=dt.date(y, m, 1),
            year=y, month=m,
            month_name=common.MONTH_NAMES[m - 1],
            quarter=(m - 1) // 3 + 1,
            year_month=f"{y:04d}-{m:02d}",
        ))
    return pl.DataFrame(rows)


def _build_hierarchy(total_leaves: int, top_names: list[str], rng,
                      mid_bounds=(2, 4), sub_bounds=(2, 4), code_prefix="P"):
    """Genera Top -> Mid -> Sub -> N foglie, con N che somma esattamente
    `total_leaves`. Ritorna lista di dict {top, mid, sub, leaf_no}."""
    top_weights = [rng.uniform(0.5, 1.5) for _ in top_names]
    top_leaf_counts = common.apportion(total_leaves, top_weights)

    out = []
    leaf_seq = 0
    for top, top_count in zip(top_names, top_leaf_counts):
        if top_count == 0:
            continue
        n_mid = rng.randint(mid_bounds[0], mid_bounds[1])
        mid_names = [f"{top} - Line {i + 1}" for i in range(n_mid)]
        mid_weights = [rng.uniform(0.5, 1.5) for _ in range(n_mid)]
        mid_leaf_counts = common.apportion(top_count, mid_weights)

        for mid, mid_count in zip(mid_names, mid_leaf_counts):
            if mid_count == 0:
                continue
            n_sub = rng.randint(sub_bounds[0], sub_bounds[1])
            sub_names = [f"{mid} / Class {chr(65 + i)}" for i in range(n_sub)]
            sub_weights = [rng.uniform(0.5, 1.5) for _ in range(n_sub)]
            sub_leaf_counts = common.apportion(mid_count, sub_weights)

            for sub, sub_count in zip(sub_names, sub_leaf_counts):
                for _ in range(sub_count):
                    leaf_seq += 1
                    out.append(dict(top=top, mid=mid, sub=sub, leaf_no=leaf_seq))
    return out


def build_planning_models(rng) -> list[dict]:
    """Item con role='planning_model'. `product_key` è l'item_key: il nome della
    chiave resta quello dei fatti (DSALES_Product), il keyspace è unico."""
    leaves = _build_hierarchy(N_PRODUCTS, PRODUCT_DIVISIONS, rng)
    rows = []
    for i, leaf in enumerate(leaves, start=1):
        div_code = "PD" + str(PRODUCT_DIVISIONS.index(leaf["top"]) + 1).zfill(2)
        # La region è un attributo, non un pezzo di nome: niente "(NAM)" nel
        # model e quindi niente suffisso -BA/-BR sulla chiave di produzione.
        region = (rng.choice(REGIONAL_MODEL_REGIONS)
                  if rng.random() < REGIONAL_MODEL_SHARE else "GLOBAL")
        rows.append(dict(
            item_key=i,
            product_key=i,
            role="planning_model",
            is_sellable=True,
            region=region,
            product_code=f"SP-{i:05d}",
            model=f"{div_code}-{leaf['leaf_no']:04d}",
            product_category=leaf["sub"],
            product_line=leaf["mid"],
            product_division=leaf["top"],
            product_division_code=div_code,
            is_active=bool(rng.random() < 0.35),
        ))
    return rows


def build_manufacturing_keys(rng) -> list[dict]:
    # Product Line del manufacturing è una tassonomia gemella (non identica)
    # a quella commerciale: stessa idea di raggruppamento, chiavi indipendenti.
    manufact_lines = [f"MFG Line {i + 1}" for i in range(18)]
    leaves = _build_hierarchy(N_MANUFACT, manufact_lines, rng, mid_bounds=(1, 3), sub_bounds=(1, 2))

    # Rimappa mid/sub sui nomi di dominio richiesti: mid=Manufacturing Category
    # (dal catalogo con i Cluster), sub=Manufacturing Family.
    cat_cycle = list(MANUFACTURING_CATEGORIES)
    rows = []
    cat_idx = 0
    family_counters: dict[tuple, int] = {}
    for i, leaf in enumerate(leaves, start=1):
        # assegna una manufacturing category dal catalogo globale in round-robin
        # pesato, cosi' tutte le entry (inclusi i Cluster) compaiono nel dato.
        category = cat_cycle[cat_idx % len(cat_cycle)]
        cat_idx += 1
        key = (leaf["top"], category)
        family_counters.setdefault(key, 0)
        family_counters[key] += 1
        family = f"{category} Family {((family_counters[key] - 1) // 6) + 1}"

        # AC2: il "x2" hard-coded oggi diventa il caso particolare factor=2.0 nel
        # dato; altri fattori (es. 1.75 per una gru pesante) mostrano che non e'
        # un caso speciale unico ma un attributo continuo dell'item.
        factor = rng.choices(
            [1.0, 1.2, 1.5, 1.75, 2.0],
            weights=[0.7, 0.1, 0.08, 0.07, 0.05],
            k=1,
        )[0]
        item_key = N_PRODUCTS + i
        rows.append(dict(
            item_key=item_key,
            manufact_key=item_key,
            role="manufacturing_key",
            is_sellable=False,
            region="GLOBAL",
            manufact_code=f"MK-{i:05d}",
            model=f"MK-{leaf['leaf_no']:04d}",
            manufacturing_family=family,
            manufacturing_category=category,
            product_line=leaf["top"],
            average_assembly_hours=round(float(rng.uniform(0.5, 42.0)), 2),
            slot_equivalence_factor=round(float(factor), 3),
            is_active=bool(rng.random() < 0.35),
        ))
    return rows


def build_semi_finished(rng) -> list[dict]:
    """I tre Basic Assemblies di Northfield. Non hanno planning model per
    costruzione (non si vendono) e la loro domanda è dipendente: arriva dal
    finito con un offset, via item_link. Oggi quel calcolo è un file Excel."""
    rows = []
    for i, (name, plant_code) in enumerate(SEMI_FINISHED, start=1):
        item_key = N_PRODUCTS + N_MANUFACT + i
        rows.append(dict(
            item_key=item_key,
            manufact_key=item_key,
            role="semi_finished",
            is_sellable=False,
            region="EMEA",
            manufact_code=f"BA-{i:03d}",
            model=name,
            home_plant_code=plant_code,
            manufacturing_family="Basic Assemblies",
            manufacturing_category="Semi-Finished",
            product_line="Pre-Assembly",
            average_assembly_hours=round(float(rng.uniform(6.0, 18.0)), 2),
            slot_equivalence_factor=1.0,
            is_active=True,
        ))
    return rows


def build_item_master(products: list[dict], manufact_keys: list[dict],
                       semi_items: list[dict]) -> pl.DataFrame:
    """Le tre liste in un solo master. Le colonne dell'altro lato restano NULL:
    una colonna nulla è dichiarata e interrogabile, una convenzione sul nome no."""
    rows = []
    for p in products:
        rows.append(dict(
            item_key=p["item_key"], role=p["role"], model=p["model"],
            region=p["region"], is_sellable=p["is_sellable"],
            product_division=p["product_division"],
            product_division_code=p["product_division_code"],
            product_line=p["product_line"], product_category=p["product_category"],
            manufacturing_line=None, manufacturing_category=None,
            manufacturing_family=None,
            average_assembly_hours=0.0, slot_equivalence_factor=1.0,
            is_active=p["is_active"],
        ))
    for m in [*manufact_keys, *semi_items]:
        rows.append(dict(
            item_key=m["item_key"], role=m["role"], model=m["model"],
            region=m["region"], is_sellable=m["is_sellable"],
            product_division=None, product_division_code=None,
            product_line=None, product_category=None,
            manufacturing_line=m["product_line"],
            manufacturing_category=m["manufacturing_category"],
            manufacturing_family=m["manufacturing_family"],
            average_assembly_hours=m["average_assembly_hours"],
            slot_equivalence_factor=m["slot_equivalence_factor"],
            is_active=m["is_active"],
        ))
    # schema esplicito: le prime righe hanno le colonne manifatturiere a NULL e
    # polars le tipizzerebbe Null, fallendo alla prima riga valorizzata.
    nullable_text = ("product_division", "product_division_code", "product_line",
                      "product_category", "manufacturing_line", "manufacturing_category",
                      "manufacturing_family")
    return pl.DataFrame(rows, schema_overrides={c: pl.String for c in nullable_text})


def build_item_identifier(rng, products: list[dict], manufact_keys: list[dict],
                           semi_items: list[dict]) -> pl.DataFrame:
    """Un element_name per ogni item; un caption divergente sul 24% delle chiavi
    di produzione (caption drift misurato); un material number SAP dove il
    caption è già stato riscritto; e nove identità rifatte con valid_to, che è
    il caso Steyr reso non distruttivo."""
    rows = []
    iid = 1

    def add(item_key: str, id_type: str, value: str, valid_from: dt.date,
            valid_to: dt.date | None = None):
        nonlocal iid
        rows.append(dict(identifier_id=iid, item_key=item_key, id_type=id_type,
                          value=value, valid_from=valid_from, valid_to=valid_to))
        iid += 1

    for p in products:
        add(p["item_key"], "element_name", p["product_code"], IDENTITY_EPOCH)

    drift_pool = []
    for m in [*manufact_keys, *semi_items]:
        add(m["item_key"], "element_name", m["manufact_code"], IDENTITY_EPOCH)
        if m["role"] == "manufacturing_key" and rng.random() < CAPTION_DRIFT_SHARE:
            drift_pool.append(m)

    for m in drift_pool:
        # Il caption è stato riscritto con il material number quando la distinta
        # è nata: due identificatori dello stesso item, non due item.
        material = f"MAT-{rng.randint(100000, 999999)}"
        add(m["item_key"], "caption", material, IDENTITY_EPOCH)
        add(m["item_key"], "sap_material", material, IDENTITY_EPOCH)

    # Caso Steyr: la versione del modello passa da A a B. La riga vecchia si
    # chiude, non si sovrascrive — i cicli passati continuano a riportare A.
    restated = rng.sample(products, N_RESTATED_IDENTITIES)
    for p in restated:
        add(p["item_key"], "legacy", f"{p['product_code']}-A", IDENTITY_EPOCH,
            IDENTITY_RESTATED_AT)
        add(p["item_key"], "caption", f"{p['product_code']}-B", IDENTITY_RESTATED_AT)

    return pl.DataFrame(rows, schema_overrides={"valid_from": pl.Date, "valid_to": pl.Date})


def _capacity_for(layout_type: str) -> dict:
    return LAYOUT_CAPACITY[layout_type]


def build_dplant(rng) -> tuple[pl.DataFrame, list[dict]]:
    rows = []
    key = 1
    remaining_by_region = dict(PLANT_REGION_TOTALS)
    default_layout = PLANT_MASTER.get("default_layout_type", "assembly_island")

    for p in NAMED_PLANTS:
        remaining_by_region[p["plant_region"]] -= 1
        plant_type = p.get("plant_type", "internal")
        # Il terzista ha una capacità propria, più piccola: è la ragione per cui
        # sta nella stessa tabella. Se fosse una sorgente infinita non
        # servirebbe modellarlo, e il piano non saprebbe mai che il conto lavoro
        # è saturo.
        cap = SUBCONTRACTOR_CAPACITY if plant_type == "subcontractor" else _capacity_for(p["layout_type"])
        rows.append(dict(
            plant_key=key,
            plant_code=p["plant_code"],
            plant_name=p["plant_name"],
            plant_activity=p["plant_activity"],
            plant_region=p["plant_region"],
            plant_type=plant_type,
            layout_type=p["layout_type"],
            max_slots=cap["max_slots"],
            slot_granularity_factor=cap["slot_granularity_factor"],
        ))
        key += 1

    generic_cap = _capacity_for(default_layout)
    for region, count in remaining_by_region.items():
        for j in range(count):
            gran = float(rng.choice(GRANULARITY_VARIANTS))
            rows.append(dict(
                plant_key=key,
                plant_code=f"{region}-{j + 1:02d}",
                plant_name=f"Plant {region} {j + 1:02d}",
                plant_activity="Manufacturing",
                plant_region=region,
                plant_type="internal",
                layout_type=default_layout,
                max_slots=generic_cap["max_slots"],
                slot_granularity_factor=gran,
            ))
            key += 1
    assert len(rows) == N_PLANTS
    return pl.DataFrame(rows), rows


def build_dsales_division(rng) -> tuple[pl.DataFrame, list[dict]]:
    rows = []
    key = 1
    for region, count in DIVISION_REGION_TOTALS.items():
        for j in range(count):
            rows.append(dict(
                division_key=key,
                division_code=f"SD-{region}-{j + 1:02d}",
                division_name=f"Sales Division {region} {j + 1:02d}",
                region=region,
            ))
            key += 1
    assert len(rows) == N_DIVISIONS
    return pl.DataFrame(rows), rows


def build_dversions() -> tuple[pl.DataFrame, list[dict]]:
    rows = []
    key = 1
    cycles = common.month_range(common.CYCLE_START, common.CYCLE_END)
    for y, m in cycles:
        budget_ref = f"SOP_BP_{y}"
        for side, status in (("DEMAND", "P"), ("DEMAND", "R"), ("SUPPLY", "A"), ("SUPPLY", "C")):
            name = f"SOP_{y:04d}_{m:02d}_{side}_{status}"
            rows.append(dict(
                version_key=key, version_name=name, cycle_year=y, cycle_month=m,
                side=side, status=status, is_budget=False, is_frozen=False,
                first_planning_year=y, first_planning_month=m,
                valid_budget_version=budget_ref,
            ))
            key += 1
    for y in common.BUDGET_YEARS:
        name = f"SOP_BP_{y}"
        rows.append(dict(
            version_key=key, version_name=name, cycle_year=y, cycle_month=1,
            side=None, status=None, is_budget=True, is_frozen=True,
            first_planning_year=y, first_planning_month=1,
            valid_budget_version=name,
        ))
        key += 1
    return pl.DataFrame(rows), rows


def build_dmeasure_demand() -> tuple[pl.DataFrame, dict]:
    defs = [
        ("REQ_PROD", "Requested Production", "units", "sum"),
        ("ORDER_BOOK", "Order Book", "units", "sum"),
        ("ORDER_ENTRY", "Order Entry", "units", "sum"),
        ("ORDER_COVERAGE", "Order Coverage", "months", "ratio"),
        ("SALES_TO_REMAIN", "Sales to Remain", "units", "sum"),
        ("FORECAST_NAIVE", "Forecast Naive", "units", "sum"),
        ("FORECAST_BASELINE", "Forecast Baseline (Statistical)", "units", "sum"),
        ("FORECAST_ADJUSTED", "Forecast Planner Adjusted", "units", "sum"),
        ("FORECAST_CONSENSUS", "Forecast Consensus", "units", "sum"),
        ("SALES_PLAN", "Sales Plan", "units", "sum"),
        ("BUDGET_VOLUME", "Budget Volume", "units", "sum"),
    ]
    rows = [dict(measure_key=i + 1, measure_code=c, measure_name=n, uom=u, agg_method=a)
            for i, (c, n, u, a) in enumerate(defs)]
    lookup = {r["measure_code"]: r["measure_key"] for r in rows}
    return pl.DataFrame(rows), lookup


def build_dmeasure_ops() -> tuple[pl.DataFrame, dict]:
    defs = [
        ("PROD_UNITS", "Production Units/Day", "units/day", "sum"),
        ("AVG_MAX_CAPACITY", "Average Maximum Capacity per Day", "units/day", "avg"),
        ("CAPACITY_UTIL", "Capacity Utilization", "ratio", "ratio"),
        ("WEEKS_PRODUCTION", "Weeks Production", "weeks", "avg"),
        ("SLOTS_REQUESTED", "Slots Requested", "slots", "sum"),
        ("SLOTS_AVAILABLE", "Slots Available", "slots", "max"),
        ("SLOTS_CURRENT_MONTH", "Slots Current Month", "slots", "sum"),
        ("SLOTS_PREVIOUS_MONTH", "Slots Previous Month", "slots", "sum"),
        ("INVENTORY", "Inventory", "units", "sum"),
        ("FMS", "Field Modification Stock (FMS)", "units", "sum"),
        ("PLANT_RELIABILITY", "Plant Reliability", "ratio", "ratio"),
        ("ORDER_BACKLOG", "Load & Open (L&O)", "units", "sum"),
        ("FROZEN_ZONE", "Frozen Zone", "months", "avg"),
        ("ASSEMBLY_HOURS_CONSUMED", "Assembly Hours Consumed", "hours", "sum"),
        ("ASSEMBLY_HOURS_CAPACITY", "Assembly Hours Capacity", "hours", "sum"),
    ]
    rows = [dict(measure_key=i + 1, measure_code=c, measure_name=n, uom=u, agg_method=a)
            for i, (c, n, u, a) in enumerate(defs)]
    lookup = {r["measure_code"]: r["measure_key"] for r in rows}
    return pl.DataFrame(rows), lookup


def build_all() -> SeedContext:
    rng_product = common.new_rng("dsales_product")
    rng_manufact = common.new_rng("dmanufact_key")
    rng_semi = common.new_rng("semi_finished")
    rng_identity = common.new_rng("item_identifier")
    rng_plant = common.new_rng("dplant")
    rng_division = common.new_rng("dsales_division")

    dim_date = build_dim_date()
    products = build_planning_models(rng_product)
    manufact_keys = build_manufacturing_keys(rng_manufact)
    semi_items = build_semi_finished(rng_semi)
    item = build_item_master(products, manufact_keys, semi_items)
    item_identifier = build_item_identifier(rng_identity, products, manufact_keys, semi_items)
    dplant, plants = build_dplant(rng_plant)
    dsales_division, divisions = build_dsales_division(rng_division)
    dversions, versions = build_dversions()
    dmeasure_demand, demand_measures = build_dmeasure_demand()
    dmeasure_ops, ops_measures = build_dmeasure_ops()

    return SeedContext(
        dim_date=dim_date,
        item=item,
        item_identifier=item_identifier,
        dplant=dplant,
        dsales_division=dsales_division,
        dversions=dversions,
        dmeasure_demand=dmeasure_demand,
        dmeasure_ops=dmeasure_ops,
        products=products,
        manufact_keys=manufact_keys,
        semi_items=semi_items,
        plants=plants,
        divisions=divisions,
        versions=versions,
        demand_measures=demand_measures,
        ops_measures=ops_measures,
    )
