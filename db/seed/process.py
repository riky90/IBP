"""Processo P/R/A/C e i due review mancanti (A9): cycle, cycle_phase,
review_instance, task, raci, portfolio_item, project, project_resource_demand,
portfolio_decision, gap, reconciliation_session, decision, escalation,
rate_card, assumption, exception_rule, exception_instance.

Le fasi (day_start/day_end, stat_state, gate) sono lette da
db/seed/data/process_phases.json — Portfolio, Demand, Global Demand
Validation, Supply, Integrated Reconciliation, Gate finale (vedi
docs/01-plan-m1.md A9); nessun range di giorni e' hardcoded qui.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import polars as pl

from . import common

DATA_DIR = Path(__file__).parent / "data"
_PROCESS_PHASES = json.loads((DATA_DIR / "process_phases.json").read_text(encoding="utf-8"))

# Fasi lette da master data (day range, stat_state, gate): non literal qui,
# coerente con lo stesso principio applicato a DPLANT (AC2).
PHASE_DEFS = [
    (p["name"], p["day_start"], p["day_end"], p["stat_state"], p["gate"])
    for p in _PROCESS_PHASES["phases"]
]
REVIEW_TYPE_BY_PHASE = _PROCESS_PHASES["review_type_by_phase"]

TODAY = dt.date(common.CURRENT_CYCLE_YEAR, common.CURRENT_CYCLE_MONTH, common.CURRENT_CYCLE_DAY)


def _review_status(is_current: bool, day_start: int, day_end: int) -> str:
    if not is_current:
        return "Closed"
    today_day = TODAY.day
    if today_day > day_end:
        return "Closed"
    if today_day >= day_start:
        return "InProgress"
    return "Scheduled"


def build_process(rng, products: list[dict], plants: list[dict],
                   manufact_keys: list[dict], demand_measures: dict, ops_measures: dict):
    cycles_ym = [*common.recent_closed_cycles(), common.CURRENT_CYCLE]
    current_ym = common.CURRENT_CYCLE

    cycle_rows, phase_rows, review_rows, task_rows, raci_rows = [], [], [], [], []
    cycle_id_by_ym = {}
    cycle_id = 1
    phase_id = 1
    review_id = 1
    task_id = 1
    raci_id = 1

    for (y, m) in cycles_ym:
        is_current = (y, m) == current_ym
        opened_at = dt.datetime(y, m, 1, 7, 0)
        closed_at = None if is_current else dt.datetime(y, m, 16, 18, 0)
        current_phase = "Demand"
        if is_current:
            for name, ds, de, _, _ in PHASE_DEFS:
                if ds <= TODAY.day <= de:
                    current_phase = name
        else:
            current_phase = "Gate"

        cycle_rows.append(dict(
            cycle_id=cycle_id, cycle_year=y, cycle_month=m, name=f"Cycle {y:04d}-{m:02d}",
            opened_at=opened_at, closed_at=closed_at, current_phase=current_phase,
        ))
        cycle_id_by_ym[(y, m)] = cycle_id

        for name, ds, de, stat_state, gate in PHASE_DEFS:
            phase_rows.append(dict(
                phase_id=phase_id, cycle_id=cycle_id, phase_no=len(phase_rows) % len(PHASE_DEFS) + 1,
                name=name, day_start=ds, day_end=de, stat_state=stat_state, gate=gate,
            ))
            phase_id += 1

            status = _review_status(is_current, ds, de)
            review_rows.append(dict(
                review_id=review_id, cycle_id=cycle_id, review_type=REVIEW_TYPE_BY_PHASE[name],
                day_start=ds, day_end=de, status=status, gate=gate,
            ))

            for t_name, owner in _tasks_for_review(name):
                task_rows.append(dict(
                    task_id=task_id, review_id=review_id, name=t_name, owner=owner,
                    due_day=de, status="Done" if status == "Closed" else "Pending",
                ))
                for role, party in _raci_for_review(name):
                    raci_rows.append(dict(raci_id=raci_id, task_id=task_id, role=role, party=party))
                    raci_id += 1
                task_id += 1
            review_id += 1
        cycle_id += 1

    # -- Portfolio Review: portfolio_item, project, project_resource_demand,
    #    portfolio_decision ------------------------------------------------
    npi_candidates = [p for p in products if not p["is_active"]][:4]
    lifecycle_cycle = ["Concept", "Development", "Launch", "Mature"]
    portfolio_item_rows, project_rows, prd_rows, decision_rows = [], [], [], []
    demand_plants = plants[:2]

    for i, prod in enumerate(npi_candidates):
        item_id = i + 1
        portfolio_item_rows.append(dict(
            item_id=item_id, product_key=prod["product_key"], name=f"NPI {prod['model']}",
            lifecycle_state=lifecycle_cycle[i % len(lifecycle_cycle)],
        ))
        project_id = i + 1
        target_launch = dt.date(current_ym[0], current_ym[1], 1) + dt.timedelta(days=90 * (i + 1))
        project_rows.append(dict(
            project_id=project_id, portfolio_item_id=item_id, name=f"Project {prod['model']}",
            state=["Proposed", "Assessed", "Resourced", "Approved"][i % 4],
            target_launch_date=target_launch,
        ))
        for j, plant in enumerate(demand_plants):
            period_y, period_m = common.month_add(current_ym[0], current_ym[1], 2 + j)
            prd_rows.append(dict(
                demand_id=len(prd_rows) + 1, project_id=project_id, plant=plant["plant_key"],
                period=dt.date(period_y, period_m, 1),
                slot_qty=float(rng.uniform(1, 4)), hours_qty=float(rng.uniform(10, 60)),
            ))
        decision_rows.append(dict(
            decision_id=i + 1, project_id=project_id, cycle_id=cycle_id_by_ym[current_ym],
            decision_type=["Introduce", "Reposition", "Defer", "Introduce"][i % 4],
            effective_date=target_launch, decided_by="portfolio.board@ibp.local",
        ))

    portfolio_item = pl.DataFrame(portfolio_item_rows)
    project = pl.DataFrame(project_rows)
    project_resource_demand = pl.DataFrame(prd_rows)
    portfolio_decision = pl.DataFrame(decision_rows)

    # -- Integrated Reconciliation: gap, reconciliation_session, decision,
    #    escalation ----------------------------------------------------------
    recon_cycle_id = cycle_id_by_ym[common.recent_closed_cycles()[-1]]
    gap_categories = ["Volume", "Mix", "Capacity", "Financial"]
    gap_rows = []
    for i in range(6):
        plan_value = float(rng.uniform(600, 5000))
        target_value = plan_value * float(rng.gauss(1.0, 0.15))
        delta_units = plan_value - target_value
        gap_rows.append(dict(
            gap_id=i + 1, cycle_id=recon_cycle_id, scope="plant" if i % 2 == 0 else "product_division",
            dimension_slice_json=json.dumps({"index": i}),
            measure_key=demand_measures["REQ_PROD"] if i % 2 else ops_measures["SLOTS_REQUESTED"],
            plan_value=round(plan_value, 2), target_value=round(target_value, 2),
            delta_units=round(delta_units, 2), delta_value=round(delta_units * 1250.0, 2),
            owner="supply.planner@ibp.local", category=gap_categories[i % len(gap_categories)],
            status=["Open", "Proposed", "Escalated", "Closed", "Open", "Escalated"][i],
        ))
    gap = pl.DataFrame(gap_rows)

    escalated_ids = [g["gap_id"] for g in gap_rows if g["status"] == "Escalated"]
    session_rows = [dict(
        session_id=1, cycle_id=recon_cycle_id,
        held_at=dt.datetime(*common.recent_closed_cycles()[-1], 15, 14, 0),
        agenda_json=json.dumps({"gap_ids": escalated_ids}), status="Closed",
    )]
    reconciliation_session = pl.DataFrame(session_rows)

    decision_ir_rows = [dict(
        decision_id=i + 1, session_id=1, gap_id=gid,
        description=f"Decisione su gap #{gid}", decided_by="ir.chair@ibp.local",
        decided_at=dt.datetime(*common.recent_closed_cycles()[-1], 15, 16, 0),
    ) for i, gid in enumerate(escalated_ids)]
    decision = pl.DataFrame(decision_ir_rows)

    escalation_rows = [dict(
        escalation_id=i + 1, gap_id=gid, session_id=1,
        level=["intermediate", "maximum"][i % 2], escalated_to="sop.director@ibp.local",
        escalated_at=dt.datetime(*common.recent_closed_cycles()[-1], 15, 12, 0), status="Open",
    ) for i, gid in enumerate(escalated_ids)]
    escalation = pl.DataFrame(escalation_rows)

    # -- rate_card --------------------------------------------------------------
    rate_card_rows = []
    for i, category in enumerate(["Cluster 10", "Cluster 31", "Standard Assembly", "Special Build"]):
        rate_card_rows.append(dict(
            rate_card_id=i + 1, manufacturing_category=category, product_division=None,
            period=dt.date(current_ym[0], 1, 1),
            avg_revenue_per_unit=round(float(rng.uniform(3000, 60000)), 2),
            avg_margin_pct=round(float(rng.uniform(0.12, 0.35)), 3),
            owner="finance.bp@ibp.local",
        ))
    rate_card = pl.DataFrame(rate_card_rows)

    # -- assumption ---------------------------------------------------------------
    assumption_rows = [
        dict(assumption_id=1, cycle_id=cycle_id_by_ym[current_ym],
             name="No supply disruption", description="Nessuna interruzione nota sui componenti critici nell'orizzonte di piano.",
             owner="supply.planner@ibp.local", measure_key=None,
             valid_from=dt.date(current_ym[0], current_ym[1], 1), valid_to=None),
        dict(assumption_id=2, cycle_id=cycle_id_by_ym[current_ym],
             name="Stable FX EUR/USD", description="Tasso di cambio EUR/USD stabile nell'orizzonte di budget.",
             owner="finance.bp@ibp.local", measure_key=demand_measures["BUDGET_VOLUME"],
             valid_from=dt.date(current_ym[0], 1, 1), valid_to=dt.date(current_ym[0], 12, 31)),
    ]
    assumption = pl.DataFrame(assumption_rows)

    # -- exception_rule / exception_instance (F3) --------------------------------
    exception_rule_rows = [
        dict(rule_id=1, name="Minor w/w variance", measure_key=demand_measures["REQ_PROD"],
             threshold_pct=20.0, comparison="w/w", severity_level="minor",
             is_provisional=True, source="Gartner literature default (F3) — nessuna soglia documentata dal vault"),
        dict(rule_id=2, name="Intermediate w/w variance", measure_key=demand_measures["REQ_PROD"],
             threshold_pct=35.0, comparison="w/w", severity_level="intermediate",
             is_provisional=True, source="Gartner literature default (F3) — nessuna soglia documentata dal vault"),
        dict(rule_id=3, name="Maximum w/w variance", measure_key=demand_measures["REQ_PROD"],
             threshold_pct=50.0, comparison="w/w", severity_level="maximum",
             is_provisional=True, source="Gartner literature default (F3) — nessuna soglia documentata dal vault"),
    ]
    exception_rule = pl.DataFrame(exception_rule_rows)

    exception_instance_rows = []
    for i in range(4):
        rule = exception_rule_rows[i % len(exception_rule_rows)]
        observed = rule["threshold_pct"] * float(rng.uniform(1.05, 1.6))
        exception_instance_rows.append(dict(
            instance_id=i + 1, rule_id=rule["rule_id"], cycle_id=recon_cycle_id,
            dimension_slice_json=json.dumps({"product_key": products[i]["product_key"]}),
            observed_value=round(observed, 2), threshold_value=rule["threshold_pct"],
            severity_level=rule["severity_level"],
            status=["Open", "Acknowledged", "Open", "Resolved"][i],
            raised_at=dt.datetime(*common.recent_closed_cycles()[-1], 9, 0),
        ))
    exception_instance = pl.DataFrame(exception_instance_rows)

    return {
        "cycle": pl.DataFrame(cycle_rows),
        "cycle_phase": pl.DataFrame(phase_rows),
        "review_instance": pl.DataFrame(review_rows),
        "task": pl.DataFrame(task_rows),
        "raci": pl.DataFrame(raci_rows),
        "portfolio_item": portfolio_item,
        "project": project,
        "project_resource_demand": project_resource_demand,
        "portfolio_decision": portfolio_decision,
        "gap": gap,
        "reconciliation_session": reconciliation_session,
        "decision": decision,
        "escalation": escalation,
        "rate_card": rate_card,
        "assumption": assumption,
        "exception_rule": exception_rule,
        "exception_instance": exception_instance,
    }, cycle_id_by_ym


def _tasks_for_review(review_name: str) -> list[tuple[str, str]]:
    common_tasks = {
        "Portfolio": [("Assess NPI resource demand", "portfolio.manager@ibp.local"),
                      ("Approve/defer projects", "portfolio.board@ibp.local")],
        "Demand": [("Build statistical baseline", "demand.analyst@ibp.local"),
                   ("Planner override review", "demand.planner@ibp.local")],
        "GlobalDemandValidation": [("Validate demand vs budget", "sop.director@ibp.local")],
        "Supply": [("Run allocation proposal", "supply.planner@ibp.local"),
                   ("Constrain to capacity", "supply.manager@ibp.local")],
        "IntegratedReconciliation": [("Build gap agenda", "ir.chair@ibp.local"),
                                      ("Decide & escalate", "ir.chair@ibp.local")],
        "Gate": [("Sign-off MBR", "sop.director@ibp.local")],
    }
    return common_tasks.get(review_name, [])


def _raci_for_review(review_name: str) -> list[tuple[str, str]]:
    return [
        ("R", "process.owner@ibp.local"),
        ("A", "sop.director@ibp.local"),
        ("C", "finance.bp@ibp.local"),
        ("I", "executive.team@ibp.local"),
    ]
