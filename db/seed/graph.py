"""Overlay a grafo (A4): un'unica tabella `edge` sopra il mirror star schema.
Copre i tipi di nodo richiesti da M1 (plant, region, product, manufact_key,
project, resource, measure); from_type/to_type sono VARCHAR liberi cosi' M2/M3
possono aggiungere dealer/importer/installer/supplier senza migrazione.
"""
from __future__ import annotations

import datetime as dt
import json

import polars as pl

VALID_FROM_DEFAULT = dt.date(2019, 1, 1)


def build_edges(plants: list[dict], item_link: pl.DataFrame, resource: pl.DataFrame,
                 project_rows: list[dict], portfolio_item_rows: list[dict],
                 assumption_rows: list[dict]) -> pl.DataFrame:
    rows = []
    eid = 1

    # plant --BELONGS_TO--> region; l'arco porta plant_type, cosi' una query sul
    # grafo distingue il nodo interno dal terzista senza tornare a DPLANT.
    for p in plants:
        rows.append(dict(
            edge_id=eid, from_type="plant", from_key=str(p["plant_key"]), rel_type="BELONGS_TO",
            to_type="region", to_key=p["plant_region"], valid_from=VALID_FROM_DEFAULT,
            valid_to=None, attrs_json=json.dumps({"plant_type": p["plant_type"]}),
        ))
        eid += 1

    # item --<link_type>--> item, dall'ultimo periodo di ogni legame. Il tipo di
    # relazione è il rel_type dell'arco: 'produces', 'aggregates', 'splits' e
    # 'dependent_demand' diventano quattro relazioni interrogabili, non una
    # sola con un significato che dipende dal contesto.
    if item_link.height > 0:
        latest_period = item_link.group_by(["from_item", "to_item", "link_type"]).agg(
            pl.col("period").max().alias("period"))
        latest_rows = item_link.join(latest_period, on=["from_item", "to_item", "link_type", "period"],
                                      how="inner")
        for r in latest_rows.iter_rows(named=True):
            rows.append(dict(
                edge_id=eid, from_type="item", from_key=str(r["from_item"]),
                rel_type=r["link_type"].upper(), to_type="item", to_key=str(r["to_item"]),
                valid_from=r["period"], valid_to=None,
                attrs_json=json.dumps({
                    "quota_pct": float(r["quota_pct"]),
                    "quota_source": r["quota_source"],
                    "offset_months": r["offset_months"],
                }),
            ))
            eid += 1

    # project --TARGETS--> product (Portfolio Review, A9)
    item_by_id = {it["item_id"]: it for it in portfolio_item_rows}
    for proj in project_rows:
        item = item_by_id.get(proj["portfolio_item_id"])
        if item and item.get("product_key") is not None:
            rows.append(dict(
                edge_id=eid, from_type="project", from_key=str(proj["project_id"]),
                rel_type="TARGETS", to_type="item", to_key=str(item["product_key"]),
                valid_from=VALID_FROM_DEFAULT, valid_to=None, attrs_json="{}",
            ))
            eid += 1

    # assumption --INFLUENCES--> measure
    for a in assumption_rows:
        if a.get("measure_key") is not None:
            rows.append(dict(
                edge_id=eid, from_type="assumption", from_key=str(a["assumption_id"]),
                rel_type="INFLUENCES", to_type="measure", to_key=str(a["measure_key"]),
                valid_from=a["valid_from"], valid_to=a.get("valid_to"), attrs_json="{}",
            ))
            eid += 1

    # resource --CONSTRAINS--> plant
    for r in resource.iter_rows(named=True):
        if r["node_type"] in ("plant_slot_pool", "plant_hour_pool"):
            rows.append(dict(
                edge_id=eid, from_type="resource", from_key=r["resource_id"],
                rel_type="CONSTRAINS", to_type="plant", to_key=r["node_key"],
                valid_from=VALID_FROM_DEFAULT, valid_to=None,
                attrs_json=json.dumps({"uom": r["uom"], "bucket": r["bucket"]}),
            ))
            eid += 1

    # schema_overrides esplicito: valid_to è quasi sempre None nelle prime
    # righe (plant/product/project), e polars altrimenti lo tipizza Null e
    # fallisce non appena incontra una vera data (righe assumption).
    return pl.DataFrame(rows, schema_overrides={"valid_from": pl.Date, "valid_to": pl.Date})
