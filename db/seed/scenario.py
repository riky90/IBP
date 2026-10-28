"""Scenari (A7): scenario, edits (append-only), overlay (cache con tombstone
esplicito). Il seed dimostra la forma dei dati che T4 orchestrerà: non
implementa merge/promozione (fuori scope di T1).

`base_snapshot_id` — nota portante. Fino al 2026-09-11 questo modulo scriveva
`SNAP_{version_name}_{iso_ts}`: un'etichetta, non un'impronta di contenuto.
Conseguenza reale, non teorica: `promote()` (T4, `_snapshot_check`) non trovava
nulla da confrontare e classificava i due scenari seminati come "non
verificabili", quindi **AC16 sugli unici scenari promuovibili spediti non
verificava niente** — ed è esattamente il percorso che la demo di T12 attraversa.

Il digest non è calcolabile qui: `base_content_digest()` legge TSOP_DEMAND/
TSOP_OPS dal DB, che al momento in cui questa funzione gira non sono ancora
caricate. Per questo il seed emette il sentinella `PENDING_DIGEST` e
`db/build_db.py` lo sostituisce subito dopo il load (`_stamp_base_snapshots`),
usando **la stessa funzione** che `branch()` e `promote()` usano — una sola
implementazione dell'algoritmo, non due che possono divergere. `_validate()`
fallisce il build se un sentinella sopravvive.
"""
from __future__ import annotations

import datetime as dt
import json

import polars as pl

from . import common

# Sostituito da `db/build_db.py::_stamp_base_snapshots` dopo il load dei fatti
# (il digest legge TSOP_DEMAND/TSOP_OPS, qui non ancora in DB). Un valore
# residuo a fine build è un errore, non un default: `_validate()` lo rifiuta.
PENDING_DIGEST = "PENDING_DIGEST"


def build_scenarios(dversions: list[dict], divisions: list[dict], demand_measures: dict,
                     scenario_refs: dict):
    version_by_name = {v["version_name"]: v for v in dversions}
    base_version = version_by_name[
        f"SOP_{common.CURRENT_CYCLE_YEAR:04d}_{common.CURRENT_CYCLE_MONTH:02d}_DEMAND_R"
    ]
    product = scenario_refs["split_product"]
    division_a = divisions[0]
    req_prod = demand_measures["REQ_PROD"]

    d1 = common.date_key(common.CURRENT_CYCLE_YEAR, common.CURRENT_CYCLE_MONTH)
    y2, m2 = common.month_add(common.CURRENT_CYCLE_YEAR, common.CURRENT_CYCLE_MONTH, 1)
    d2 = common.date_key(y2, m2)
    y3, m3 = common.month_add(common.CURRENT_CYCLE_YEAR, common.CURRENT_CYCLE_MONTH, 2)
    d3 = common.date_key(y3, m3)

    def cell_key(date_key):
        return json.dumps({
            "version_key": base_version["version_key"], "product_key": product["product_key"],
            "division_key": division_a["division_key"], "date_key": date_key,
            "measure_key": req_prod,
        })

    created = dt.datetime(common.CURRENT_CYCLE_YEAR, common.CURRENT_CYCLE_MONTH, 12, 10, 0)
    scenario_rows = [
        dict(scenario_id="SCN-0001", name="What-if: NAM configuration mix shift",
             base_version_key=base_version["version_key"],
             base_snapshot_id=PENDING_DIGEST,
             parent_scenario_id=None, owner="demand.planner@ibp.local",
             state="Evaluated", created_at=created),
        dict(scenario_id="SCN-0002", name="What-if: NAM mix shift - deep dive",
             base_version_key=base_version["version_key"],
             base_snapshot_id=PENDING_DIGEST,
             parent_scenario_id="SCN-0001", owner="demand.planner@ibp.local",
             state="Draft", created_at=created + dt.timedelta(hours=3)),
    ]

    edits_rows = [
        dict(edit_id=1, scenario_id="SCN-0001", ts=created, user="demand.planner@ibp.local",
             cell_key_json=cell_key(d1), measure_key=req_prod, old_value=120.0, new_value=150.0, op="set"),
        dict(edit_id=2, scenario_id="SCN-0001", ts=created + dt.timedelta(minutes=20),
             user="demand.planner@ibp.local", cell_key_json=cell_key(d1), measure_key=req_prod,
             old_value=150.0, new_value=165.0, op="increment"),
        dict(edit_id=3, scenario_id="SCN-0001", ts=created + dt.timedelta(minutes=45),
             user="demand.planner@ibp.local", cell_key_json=cell_key(d2), measure_key=req_prod,
             old_value=95.0, new_value=None, op="delete"),
        dict(edit_id=4, scenario_id="SCN-0002", ts=created + dt.timedelta(hours=3, minutes=5),
             user="supply.planner@ibp.local", cell_key_json=cell_key(d3), measure_key=req_prod,
             old_value=80.0, new_value=92.0, op="set"),
    ]

    overlay_rows = [
        dict(overlay_id=1, scenario_id="SCN-0001", version_key=base_version["version_key"],
             product_key=product["product_key"], plant_key=None, date_key=d1,
             measure_key=req_prod, value=165.0, is_deleted=False),
        dict(overlay_id=2, scenario_id="SCN-0001", version_key=base_version["version_key"],
             product_key=product["product_key"], plant_key=None, date_key=d2,
             measure_key=req_prod, value=None, is_deleted=True),
        dict(overlay_id=3, scenario_id="SCN-0002", version_key=base_version["version_key"],
             product_key=product["product_key"], plant_key=None, date_key=d3,
             measure_key=req_prod, value=92.0, is_deleted=False),
    ]

    return dict(
        scenario=pl.DataFrame(scenario_rows),
        edits=pl.DataFrame(edits_rows),
        overlay=pl.DataFrame(overlay_rows),
    )
