"""Rete produttiva (A2, il cuore di M1): item_link, production_eligibility,
routing, bill_of_resource, resource, resource_capacity.

Contiene esplicitamente i casi richiesti dal piano:
  - item_link M:N in entrambe le direzioni (F7): uno split 60/40 con override
    manuale tracciato, e l'aggregazione "Timber & Recycling" (più planning
    model sulla stessa manufacturing key).
  - domanda dipendente del semilavorato (F10) come riga di item_link con
    offset_months=2 — il calcolo che oggi è un file Excel che scrive sul DB.
  - routing obbligatorio (Ganderkesee -> Cerritos, tipo ILK/ILT), routing
    elettivo (Northfield/Niagara, caso NAM) con variant_key, e un passo su
    terzista, che consuma capacità come gli altri.
"""
from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

import polars as pl

from . import common

DATA_DIR = Path(__file__).parent / "data"
_PLANT_MASTER = json.loads((DATA_DIR / "plant_master.json").read_text(encoding="utf-8"))
HOUR_POOL_MONTHLY_HOURS = _PLANT_MASTER["hour_pool_monthly_hours"]
SUB_HOUR_POOL_MONTHLY_HOURS = _PLANT_MASTER["subcontractor_hour_pool_monthly_hours"]

MAPPING_WINDOW_MONTHS_BACK = 5  # finestra time-phased del baseline mapping

# Lo split fra manufacturing key non è una percentuale mantenuta a mano: è il
# mix osservato a consuntivo sull'orderbook degli ultimi N mesi, ricalcolato ad
# ogni ciclo. Oltre l'orizzonte dell'orderbook — dove oggi il piano allocava
# tutto al plant di default della region, falsando il carico di medio termine —
# resta l'unica base ancorata ai fatti.
OBSERVED_MIX_WINDOW_MONTHS = 12

# Domanda dipendente: il semilavorato è richiesto due mesi prima del finito
# (lead time + transito). Un solo parametro, non una matrice per lane (F10).
DEPENDENT_DEMAND_OFFSET_MONTHS = 2


def _plants_by_code(plants: list[dict]) -> dict:
    return {p["plant_code"]: p for p in plants}


def _plants_by_region(plants: list[dict]) -> dict:
    out = defaultdict(list)
    for p in plants:
        out[p["plant_region"]].append(p)
    return out


def build_network(rng, products: list[dict], manufact_keys: list[dict], plants: list[dict],
                   semi_items: list[dict]):
    active_products = [p for p in products if p["is_active"]]
    active_manufact = [m for m in manufact_keys if m["is_active"]]
    by_code = _plants_by_code(plants)
    by_region = _plants_by_region(plants)

    window = common.month_range(
        common.month_add(common.CURRENT_CYCLE_YEAR, common.CURRENT_CYCLE_MONTH, -MAPPING_WINDOW_MONTHS_BACK),
        (common.CURRENT_CYCLE_YEAR, common.CURRENT_CYCLE_MONTH),
    )

    # -- selezioni per i casi obbligatori del piano -------------------------
    split_product = active_products[0]
    timber_manufact = active_manufact[0]
    timber_products = active_products[1:4]
    mandatory_key = active_manufact[10]
    elective_key = active_manufact[11]
    split_mk_a = active_manufact[1]
    split_mk_b = active_manufact[2]

    reserved_product_keys = {split_product["product_key"], *[p["product_key"] for p in timber_products]}
    reserved_manufact_keys = {timber_manufact["manufact_key"], mandatory_key["manufact_key"], elective_key["manufact_key"]}

    link_rows = []
    lid = 1

    def add_link(from_item, to_item, link_type, period, quota_pct, quota_source,
                 quota_window_months=None, offset_months=0,
                 override_by=None, override_at=None):
        nonlocal lid
        link_rows.append(dict(
            link_id=lid, from_item=from_item, to_item=to_item, link_type=link_type,
            period=period, quota_pct=quota_pct, quota_source=quota_source,
            quota_window_months=quota_window_months, offset_months=offset_months,
            override_by=override_by, override_at=override_at,
            valid_from=period, valid_to=None,
        ))
        lid += 1

    # Caso 'splits' — 1 planning model -> N manufacturing key. La quota è il mix
    # osservato a consuntivo, non una percentuale scritta a mano: quota_source
    # lo dichiara, quota_window_months dice su quanto passato è misurata.
    for (y, m) in window[:-1]:
        period = dt.date(y, m, 1)
        for mk, pct in ((split_mk_a, 60.0), (split_mk_b, 40.0)):
            add_link(split_product["product_key"], mk["manufact_key"], "splits",
                     period, pct, "observed_history", OBSERVED_MIX_WINDOW_MONTHS)

    # L'override manuale resta possibile e resta distinguibile dal valore di
    # regola: il planner che scavalca il mix osservato lascia una firma.
    last_y, last_m = window[-1]
    last_period = dt.date(last_y, last_m, 1)
    override_ts = dt.datetime(last_y, last_m, 15, 9, 25)
    for mk, pct in ((split_mk_a, 55.0), (split_mk_b, 45.0)):
        add_link(split_product["product_key"], mk["manufact_key"], "splits",
                 last_period, pct, "manual_override",
                 override_by="demand.planner@ibp.local", override_at=override_ts)

    # Caso 'aggregates' — N planning model -> 1 manufacturing key (i YCRANE_*).
    for prod in timber_products:
        for (y, m) in window:
            add_link(prod["product_key"], timber_manufact["manufact_key"],
                     "aggregates", dt.date(y, m, 1), 100.0, "rule")

    # Caso 'produces' — 1:1 diretto, il grosso del parco (462 su 685 misurati).
    baseline_products = [p for p in active_products if p["product_key"] not in reserved_product_keys]
    baseline_pool = [m for m in active_manufact if m["manufact_key"] not in reserved_manufact_keys]
    for i, prod in enumerate(baseline_products):
        mk = baseline_pool[i % len(baseline_pool)]
        for (y, m) in window:
            add_link(prod["product_key"], mk["manufact_key"], "produces",
                     dt.date(y, m, 1), 100.0, "rule")

    # Caso 'dependent_demand' — il finito tira il semilavorato con due mesi di
    # anticipo. È il pattern -BA/-BR: oggi due nomi di chiave senza relazione e
    # un Excel che fa la sottrazione; qui una riga con un offset.
    finished_for_semi = baseline_pool[:len(semi_items)]
    for semi, finished in zip(semi_items, finished_for_semi):
        for (y, m) in window:
            add_link(finished["manufact_key"], semi["item_key"], "dependent_demand",
                     dt.date(y, m, 1), 100.0, "rule",
                     offset_months=DEPENDENT_DEMAND_OFFSET_MONTHS)

    item_link = pl.DataFrame(link_rows, schema_overrides={
        "period": pl.Date, "valid_from": pl.Date, "valid_to": pl.Date,
        "quota_window_months": pl.Int32, "override_at": pl.Datetime,
    })

    # -- production_eligibility (F8) -----------------------------------------
    eligibility_rows = []
    eid = 1
    valid_from = dt.date(2019, 1, 1)

    ganderkesee, cerritos = by_code["DE-GANDERKESEE"], by_code["US-CERRITOS"]
    northfield, niagara = by_code["AT-NORTHFIELD"], by_code["CA-NIAGARA"]

    for plant, region_scope, prio in (
        (ganderkesee, "EMEA", 1), (cerritos, "NAM", 1),
    ):
        eligibility_rows.append(dict(
            eligibility_id=eid, manufacturing_key=mandatory_key["manufact_key"],
            plant=plant["plant_key"], region_scope=region_scope, priority=prio,
            valid_from=valid_from, valid_to=None,
        ))
        eid += 1

    for plant, prio in ((northfield, 1), (niagara, 2)):
        eligibility_rows.append(dict(
            eligibility_id=eid, manufacturing_key=elective_key["manufact_key"],
            plant=plant["plant_key"], region_scope="NAM", priority=prio,
            valid_from=valid_from, valid_to=None,
        ))
        eid += 1

    # I tre semilavorati si producono solo a Northfield, ed è tutto ciò che serve
    # dire: il vincolo è nel dato, non nel fatto che nessuno li ordini altrove.
    for semi in semi_items:
        home = by_code[semi["home_plant_code"]]
        eligibility_rows.append(dict(
            eligibility_id=eid, manufacturing_key=semi["item_key"],
            plant=home["plant_key"], region_scope="GLOBAL", priority=1,
            valid_from=valid_from, valid_to=None,
        ))
        eid += 1

    # Il terzista è eleggibile come qualsiasi altro plant, con priorità più
    # bassa: si usa quando l'interno non basta. La differenza sta in plant_type,
    # non nel fatto di essere fuori dal modello.
    subcontractors = [p for p in plants if p["plant_type"] == "subcontractor"]
    subcontracted_keys = []
    for i, sub in enumerate(subcontractors):
        mk = active_manufact[20 + i]
        subcontracted_keys.append(mk)
        eligibility_rows.append(dict(
            eligibility_id=eid, manufacturing_key=mk["manufact_key"],
            plant=sub["plant_key"], region_scope=sub["plant_region"], priority=2,
            valid_from=valid_from, valid_to=None,
        ))
        eid += 1

    special_pair_keys = {mandatory_key["manufact_key"], elective_key["manufact_key"]}

    generic_home_region: dict[int, dict] = {}
    for mk in active_manufact:
        if mk["manufact_key"] in special_pair_keys:
            continue
        region = rng.choice(common.REGIONS)
        candidates = by_region[region]
        plant = rng.choice(candidates)
        generic_home_region[mk["manufact_key"]] = plant
        eligibility_rows.append(dict(
            eligibility_id=eid, manufacturing_key=mk["manufact_key"],
            plant=plant["plant_key"], region_scope=region, priority=1,
            valid_from=valid_from, valid_to=None,
        ))
        eid += 1
        if rng.random() < 0.2:
            other_region = rng.choice([r for r in common.REGIONS if r != region])
            other_candidates = by_region[other_region]
            other_plant = rng.choice(other_candidates)
            eligibility_rows.append(dict(
                eligibility_id=eid, manufacturing_key=mk["manufact_key"],
                plant=other_plant["plant_key"], region_scope=other_region, priority=2,
                valid_from=valid_from, valid_to=None,
            ))
            eid += 1

    production_eligibility = pl.DataFrame(eligibility_rows)

    # -- routing (F9/F10) ------------------------------------------------------
    routing_rows = [
        dict(routing_id=1, manufacturing_key=mandatory_key["manufact_key"], variant_key=None,
             step_no=1, plant=ganderkesee["plant_key"], operation_type="semi_finish",
             lead_offset_months=2, mandatory=True),
        dict(routing_id=2, manufacturing_key=mandatory_key["manufact_key"], variant_key=None,
             step_no=2, plant=cerritos["plant_key"], operation_type="finish",
             lead_offset_months=0, mandatory=True),
        dict(routing_id=3, manufacturing_key=elective_key["manufact_key"], variant_key="A",
             step_no=1, plant=northfield["plant_key"], operation_type="pre_assembly",
             lead_offset_months=1, mandatory=False),
        dict(routing_id=4, manufacturing_key=elective_key["manufact_key"], variant_key="A",
             step_no=2, plant=niagara["plant_key"], operation_type="finish",
             lead_offset_months=0, mandatory=False),
        dict(routing_id=5, manufacturing_key=elective_key["manufact_key"], variant_key="B",
             step_no=1, plant=northfield["plant_key"], operation_type="full_build",
             lead_offset_months=0, mandatory=False),
    ]

    # Passo su terzista: due step, il secondo fuori. Consuma capacità come gli
    # altri, e il piano se ne accorge quando il terzista è pieno.
    rid = len(routing_rows) + 1
    for sub, mk in zip(subcontractors, subcontracted_keys):
        home = generic_home_region.get(mk["manufact_key"])
        if home is None or home["plant_key"] == sub["plant_key"]:
            continue
        routing_rows.append(dict(
            routing_id=rid, manufacturing_key=mk["manufact_key"], variant_key="SUB",
            step_no=1, plant=home["plant_key"], operation_type="pre_assembly",
            lead_offset_months=1, mandatory=False,
        ))
        rid += 1
        routing_rows.append(dict(
            routing_id=rid, manufacturing_key=mk["manufact_key"], variant_key="SUB",
            step_no=2, plant=sub["plant_key"], operation_type="contract_finish",
            lead_offset_months=0, mandatory=False,
        ))
        rid += 1

    # Il semilavorato ha un routing proprio a Northfield: è un item pianificato,
    # non una riga di Excel derivata dal finito.
    for semi in semi_items:
        home = by_code[semi["home_plant_code"]]
        routing_rows.append(dict(
            routing_id=rid, manufacturing_key=semi["item_key"], variant_key=None,
            step_no=1, plant=home["plant_key"], operation_type="pre_assembly",
            lead_offset_months=0, mandatory=True,
        ))
        rid += 1

    routing = pl.DataFrame(routing_rows)

    # -- resource + resource_capacity ------------------------------------------
    resource_rows = []
    for p in plants:
        resource_rows.append(dict(
            resource_id=f"SLOT::{p['plant_code']}", node_type="plant_slot_pool",
            node_key=str(p["plant_key"]), uom="slot", bucket="month",
            capacity_source="DPLANT.max_slots",
        ))
        if p["layout_type"] == "assembly_island":
            sub = p["plant_type"] == "subcontractor"
            resource_rows.append(dict(
                resource_id=f"HOUR::{p['plant_code']}", node_type="plant_hour_pool",
                node_key=str(p["plant_key"]), uom="hour", bucket="month",
                capacity_source=("plant_master.subcontractor_hour_pool_monthly_hours"
                                  if sub else "plant_master.hour_pool_monthly_hours"),
            ))
    resource = pl.DataFrame(resource_rows)

    capacity_window = common.month_range(
        common.month_add(common.CURRENT_CYCLE_YEAR, common.CURRENT_CYCLE_MONTH, -common.CAPACITY_WINDOW_MONTHS_BACK),
        common.month_add(common.CURRENT_CYCLE_YEAR, common.CURRENT_CYCLE_MONTH, common.CAPACITY_WINDOW_MONTHS_FWD),
    )
    plant_by_key = {p["plant_key"]: p for p in plants}
    capacity_rows = []
    for r in resource_rows:
        plant = plant_by_key[int(r["node_key"])]
        for (y, m) in capacity_window:
            period = dt.date(y, m, 1)
            if r["node_type"] == "plant_slot_pool":
                qty = float(plant["max_slots"])
            elif plant["plant_type"] == "subcontractor":
                qty = float(SUB_HOUR_POOL_MONTHLY_HOURS)
            else:
                qty = float(HOUR_POOL_MONTHLY_HOURS)
            capacity_rows.append(dict(
                resource_id=r["resource_id"], period=period, available_qty=qty,
                calendar_id="STD", utilisation_target=0.85,
            ))
    resource_capacity = pl.DataFrame(capacity_rows)

    # -- bill_of_resource --------------------------------------------------------
    bor_rows = []
    bid = 1

    def add_bor(mk_key, variant_key, plant_code, qty_per_unit, offset_periods, spread=None):
        nonlocal bid
        bor_rows.append(dict(
            bor_id=bid, manufacturing_key=mk_key, variant_key=variant_key,
            resource_id=f"SLOT::{plant_code}", qty_per_unit=qty_per_unit,
            offset_periods=offset_periods,
            spread_profile_json=json.dumps(spread or {}),
        ))
        bid += 1

    add_bor(mandatory_key["manufact_key"], None, "DE-GANDERKESEE",
            mandatory_key["slot_equivalence_factor"], -2, {"current": 0.6, "previous": 0.4})
    add_bor(mandatory_key["manufact_key"], None, "US-CERRITOS",
            mandatory_key["slot_equivalence_factor"], 0)
    add_bor(elective_key["manufact_key"], "A", "AT-NORTHFIELD",
            elective_key["slot_equivalence_factor"], -1)
    add_bor(elective_key["manufact_key"], "A", "CA-NIAGARA",
            elective_key["slot_equivalence_factor"], 0)
    add_bor(elective_key["manufact_key"], "B", "AT-NORTHFIELD",
            elective_key["slot_equivalence_factor"], 0)

    for mk in active_manufact:
        if mk["manufact_key"] in special_pair_keys:
            continue
        plant = generic_home_region[mk["manufact_key"]]
        add_bor(mk["manufact_key"], None, plant["plant_code"], mk["slot_equivalence_factor"], 0)
        if plant["layout_type"] == "assembly_island":
            bor_rows.append(dict(
                bor_id=bid, manufacturing_key=mk["manufact_key"], variant_key=None,
                resource_id=f"HOUR::{plant['plant_code']}", qty_per_unit=mk["average_assembly_hours"],
                offset_periods=0, spread_profile_json="{}",
            ))
            bid += 1

    # Terzista: assorbe slot e ore come un plant interno. Se non li assorbisse,
    # il conto lavoro sarebbe una capacità infinita e il piano non lo saprebbe.
    for sub, mk in zip(subcontractors, subcontracted_keys):
        add_bor(mk["manufact_key"], "SUB", sub["plant_code"],
                mk["slot_equivalence_factor"], 0)
        bor_rows.append(dict(
            bor_id=bid, manufacturing_key=mk["manufact_key"], variant_key="SUB",
            resource_id=f"HOUR::{sub['plant_code']}",
            qty_per_unit=mk["average_assembly_hours"], offset_periods=0,
            spread_profile_json="{}",
        ))
        bid += 1

    # Semilavorato: consuma capacità a Northfield con l'offset di due mesi, che è
    # lo stesso parametro dichiarato su item_link — un solo valore, due usi.
    for semi in semi_items:
        add_bor(semi["item_key"], None, semi["home_plant_code"],
                semi["slot_equivalence_factor"], -DEPENDENT_DEMAND_OFFSET_MONTHS)

    bill_of_resource = pl.DataFrame(bor_rows)

    scenario_refs = dict(
        mandatory_key=mandatory_key, elective_key=elective_key,
        split_product=split_product, split_mk_a=split_mk_a, split_mk_b=split_mk_b,
        timber_manufact=timber_manufact, timber_products=timber_products,
        generic_home_region=generic_home_region,
        subcontractors=subcontractors, subcontracted_keys=subcontracted_keys,
        semi_items=semi_items,
    )
    return dict(
        item_link=item_link,
        production_eligibility=production_eligibility,
        routing=routing,
        resource=resource,
        resource_capacity=resource_capacity,
        bill_of_resource=bill_of_resource,
    ), scenario_refs
