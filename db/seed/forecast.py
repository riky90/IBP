"""Forecast e FVA (A8): forecast_snapshot a lag costante, forecast_override,
actual_restatement. Il seed copre >=2 cicli di creazione con lag multipli,
cosi' che T5 possa ricostruire lo stairstep Naive -> Baseline -> Rettificata
-> Consenso senza dover rigenerare la storia (impossibile a posteriori, A8)."""
from __future__ import annotations

import datetime as dt

import math
import polars as pl

from . import common

N_SERIES = 6
N_CREATED_CYCLES_BACK = 2   # >= 2 cicli richiesti dal piano
MAX_LAG_MONTHS = 5
PROCESS_STEPS = ("naive", "statistical", "planner_adjusted", "consensus")


def build_forecast(rng, products: list[dict]):
    active_products = [p for p in products if p["is_active"]][:N_SERIES]
    series_ids = [f"SERIES::{p['product_key']}" for p in active_products]

    created_cycles = common.recent_closed_cycles(N_CREATED_CYCLES_BACK)

    snapshot_rows = []
    override_rows = []
    restatement_rows = []
    snap_id = 1
    override_id = 1
    restatement_id = 1

    for series_id in series_ids:
        level = float(rng.uniform(20, 250))
        for (cy, cm) in created_cycles:
            created_period = dt.date(cy, cm, 1)
            for lag in range(0, MAX_LAG_MONTHS + 1):
                ty, tm = common.month_add(cy, cm, lag)
                target_period = dt.date(ty, tm, 1)
                seasonal = 1.0 + 0.1 * math.sin(tm / 12.0 * 2 * math.pi)

                naive_val = level * seasonal
                statistical_val = naive_val * float(rng.gauss(1.0, 0.06))
                # FVA negativo allo step planner e' comune e onesto (A8): non si
                # forza sempre un miglioramento rispetto alla baseline.
                planner_val = statistical_val * float(rng.gauss(1.0, 0.09))
                consensus_val = (statistical_val + planner_val) / 2.0 * float(rng.gauss(1.0, 0.02))

                for step, val, model in (
                    ("naive", naive_val, "seasonal_naive"),
                    ("statistical", statistical_val, "AutoETS"),
                    ("planner_adjusted", planner_val, None),
                    ("consensus", consensus_val, None),
                ):
                    snapshot_rows.append(dict(
                        snapshot_id=snap_id, series_id=series_id, target_period=target_period,
                        created_period=created_period, lag=lag, process_step=step,
                        value=round(float(val), 3), model_name=model,
                    ))
                    snap_id += 1

                if rng.random() < 0.3:
                    override_rows.append(dict(
                        override_id=override_id, series_id=series_id, target_period=target_period,
                        created_period=created_period, user="demand.planner@ibp.local",
                        reason_code=str(rng.choice(["promo", "event", "data_correction", "market_intel"])),
                        delta=round(float(planner_val - statistical_val), 3),
                    ))
                    override_id += 1

            # actual + eventuale restatement per i mesi ormai passati (lag<=1
            # dal ciclo di creazione più vecchio -> gia' consuntivati).
            actual_period_y, actual_period_m = cy, cm
            actual_value = level * (1.0 + 0.1 * math.sin(actual_period_m / 12.0 * 2 * math.pi)) * float(rng.gauss(1.0, 0.05))
            restated_at = dt.datetime(actual_period_y, actual_period_m, 20, 7, 0)
            restatement_rows.append(dict(
                restatement_id=restatement_id, series_id=series_id,
                period=dt.date(actual_period_y, actual_period_m, 1),
                value=round(float(actual_value), 3), restated_at=restated_at,
            ))
            restatement_id += 1
            if rng.random() < 0.4:
                later_value = actual_value * float(rng.gauss(1.0, 0.03))
                restatement_rows.append(dict(
                    restatement_id=restatement_id, series_id=series_id,
                    period=dt.date(actual_period_y, actual_period_m, 1),
                    value=round(float(later_value), 3),
                    restated_at=restated_at + dt.timedelta(days=45),
                ))
                restatement_id += 1

    return dict(
        forecast_snapshot=pl.DataFrame(snapshot_rows),
        forecast_override=pl.DataFrame(override_rows),
        actual_restatement=pl.DataFrame(restatement_rows),
    )
