"""La parte di T4 che lo schema non impone — decisa dall'implementatore: una
slice di `overlay` (`product_key|plant_key` + `date_key` + `measure_key`)
più larga della grana piena di `TSOP_DEMAND`/`TSOP_OPS` (senza
`division_key`/`region`/`manufact_key`) viene, a `promote()`, **proratata
sul mix osservato in base** sulle righe che quella slice copre — o
distribuita in parti uguali se il mix di base è tutto zero — e una slice
overlay senza nessuna riga base corrispondente è rifiutata esplicitamente
(`UnmaterializableCellError`), mai materializzata a caso."""
from __future__ import annotations

import pytest

import ibp.scenario as sc

from _scenario_support import (
    DEMAND_BASE_VERSION_KEY,
    DEMAND_PRORATION_BASE_ROWS,
    DEMAND_PRORATION_BASE_SUM,
    DEMAND_PRORATION_DATE_KEY,
    DEMAND_PRORATION_MEASURE_KEY,
    DEMAND_PRORATION_PRODUCT_KEY,
    OPS_BASE_VERSION_KEY,
    OPS_PRORATION_BASE_ROWS,
    OPS_PRORATION_BASE_SUM,
    OPS_PRORATION_DATE_KEY,
    OPS_PRORATION_MEASURE_KEY,
    OPS_PRORATION_PLANT_KEY,
    PROMOTION_YEAR,
)


def test_demand_override_prorates_on_observed_base_mix_and_sums_to_target(writable_db_copy):
    con = writable_db_copy
    cell = sc.CellKey(
        version_key=DEMAND_BASE_VERSION_KEY, date_key=DEMAND_PRORATION_DATE_KEY,
        measure_key=DEMAND_PRORATION_MEASURE_KEY, product_key=DEMAND_PRORATION_PRODUCT_KEY,
    )
    scenario = sc.branch(con, name="prorate-demand", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    target = 246.05  # esattamente il doppio della somma base (123.025 * 2)
    sc.set_cell(con, scenario.scenario_id, cell, target, user="tester")
    sc.mark_evaluated(con, scenario.scenario_id)

    result = sc.promote(
        con, scenario.scenario_id, cycle_year=PROMOTION_YEAR, cycle_month=1,
        side="DEMAND", status="C", user="tester",
    )

    rows = con.execute(
        "SELECT division_key, region, value FROM TSOP_DEMAND WHERE version_key = ? "
        "AND product_key = ? AND date_key = ? AND measure_key = ? ORDER BY division_key",
        [result.version_key, DEMAND_PRORATION_PRODUCT_KEY, DEMAND_PRORATION_DATE_KEY, DEMAND_PRORATION_MEASURE_KEY],
    ).fetchall()
    assert len(rows) == len(DEMAND_PRORATION_BASE_ROWS)  # stesse righe (division/region) del base, non fuse

    by_division = {r[0]: r[2] for r in rows}
    for division_key, region, base_value in DEMAND_PRORATION_BASE_ROWS:
        expected_share = base_value / DEMAND_PRORATION_BASE_SUM
        assert by_division[division_key] == pytest.approx(target * expected_share)

    assert sum(r[2] for r in rows) == pytest.approx(target)  # somma torna esattamente all'override


def test_ops_override_prorates_on_observed_base_mix_and_sums_to_target(writable_db_copy):
    con = writable_db_copy
    cell = sc.CellKey(
        version_key=OPS_BASE_VERSION_KEY, date_key=OPS_PRORATION_DATE_KEY,
        measure_key=OPS_PRORATION_MEASURE_KEY, plant_key=OPS_PRORATION_PLANT_KEY,
    )
    scenario = sc.branch(con, name="prorate-ops", base_version_key=OPS_BASE_VERSION_KEY, owner="tester")
    target = 1500.0
    sc.set_cell(con, scenario.scenario_id, cell, target, user="tester")
    sc.mark_evaluated(con, scenario.scenario_id)

    result = sc.promote(
        con, scenario.scenario_id, cycle_year=PROMOTION_YEAR, cycle_month=2,
        side="SUPPLY", status="A", user="tester",
    )

    rows = con.execute(
        "SELECT manufact_key, product_key, division_key, value FROM TSOP_OPS WHERE version_key = ? "
        "AND plant_key = ? AND date_key = ? AND measure_key = ? ORDER BY manufact_key",
        [result.version_key, OPS_PRORATION_PLANT_KEY, OPS_PRORATION_DATE_KEY, OPS_PRORATION_MEASURE_KEY],
    ).fetchall()
    assert len(rows) == len(OPS_PRORATION_BASE_ROWS)

    by_manufact = {r[0]: r[3] for r in rows}
    for manufact_key, product_key, division_key, region, base_value in OPS_PRORATION_BASE_ROWS:
        expected_share = base_value / OPS_PRORATION_BASE_SUM
        assert by_manufact[manufact_key] == pytest.approx(target * expected_share)

    assert sum(r[3] for r in rows) == pytest.approx(target)


def test_zero_base_mix_prorates_equally_not_undefined(writable_db_copy):
    """Se tutte le righe base della slice sono 0.0 (nessun mix osservabile),
    il riparto deve essere equo fra le righe — non una divisione per zero
    e non tutto concentrato su una sola riga per un bug di segno."""
    con = writable_db_copy
    con.execute(
        "UPDATE TSOP_DEMAND SET value = 0.0 WHERE version_key = ? AND product_key = ? "
        "AND date_key = ? AND measure_key = ?",
        [DEMAND_BASE_VERSION_KEY, DEMAND_PRORATION_PRODUCT_KEY, DEMAND_PRORATION_DATE_KEY, DEMAND_PRORATION_MEASURE_KEY],
    )
    cell = sc.CellKey(
        version_key=DEMAND_BASE_VERSION_KEY, date_key=DEMAND_PRORATION_DATE_KEY,
        measure_key=DEMAND_PRORATION_MEASURE_KEY, product_key=DEMAND_PRORATION_PRODUCT_KEY,
    )
    scenario = sc.branch(con, name="prorate-zero-mix", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    sc.set_cell(con, scenario.scenario_id, cell, 100.0, user="tester")
    sc.mark_evaluated(con, scenario.scenario_id)

    result = sc.promote(
        con, scenario.scenario_id, cycle_year=PROMOTION_YEAR, cycle_month=3,
        side="DEMAND", status="A", user="tester",
    )

    rows = con.execute(
        "SELECT value FROM TSOP_DEMAND WHERE version_key = ? AND product_key = ? "
        "AND date_key = ? AND measure_key = ?",
        [result.version_key, DEMAND_PRORATION_PRODUCT_KEY, DEMAND_PRORATION_DATE_KEY, DEMAND_PRORATION_MEASURE_KEY],
    ).fetchall()
    assert len(rows) == 2
    for (value,) in rows:
        assert value == pytest.approx(50.0)  # 100.0 / 2, ripartizione equa


def test_overlay_cell_with_zero_matching_base_rows_raises_unmaterializable(writable_db_copy):
    con = writable_db_copy
    fictitious_cell = sc.CellKey(
        version_key=DEMAND_BASE_VERSION_KEY, date_key=209912,  # nessuna riga TSOP_DEMAND a questa data
        measure_key=DEMAND_PRORATION_MEASURE_KEY, product_key=DEMAND_PRORATION_PRODUCT_KEY,
    )
    # non-vacuità: verifica che davvero non ci sia nessuna riga base per questa slice
    assert con.execute(
        "SELECT count(*) FROM TSOP_DEMAND WHERE version_key = ? AND product_key = ? AND date_key = 209912",
        [DEMAND_BASE_VERSION_KEY, DEMAND_PRORATION_PRODUCT_KEY],
    ).fetchone()[0] == 0

    scenario = sc.branch(con, name="unmaterializable", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    sc.set_cell(con, scenario.scenario_id, fictitious_cell, 42.0, user="tester")
    sc.mark_evaluated(con, scenario.scenario_id)

    dv_count_before = con.execute("SELECT count(*) FROM DVERSIONS").fetchone()[0]

    with pytest.raises(sc.UnmaterializableCellError) as exc_info:
        sc.promote(
            con, scenario.scenario_id, cycle_year=PROMOTION_YEAR, cycle_month=4,
            side="DEMAND", status="P", user="tester",
        )
    assert exc_info.value.cell_key == (DEMAND_PRORATION_PRODUCT_KEY, None, 209912, DEMAND_PRORATION_MEASURE_KEY)

    dv_count_after = con.execute("SELECT count(*) FROM DVERSIONS").fetchone()[0]
    assert dv_count_after == dv_count_before, "nessuna nuova DVERSIONS deve comparire su un rifiuto"
