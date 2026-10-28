"""AC16 — promozione con base mossa dal branch time: conflitto, mai
sovrascrittura. Verificato per davvero: il conflitto deve essere rilevato
*prima* di qualunque scrittura (nessuna riga DVERSIONS/TSOP_DEMAND/
TSOP_OPS parziale, nessun cambio di stato dello scenario) — un conflitto
rilevato dopo una scrittura parziale sarebbe peggio di nessun controllo."""
from __future__ import annotations

import pytest

import ibp.scenario as sc

from _scenario_support import (
    DEMAND_BASE_VERSION_KEY,
    DEMAND_PRORATION_DATE_KEY,
    DEMAND_PRORATION_MEASURE_KEY,
    DEMAND_PRORATION_PRODUCT_KEY,
    PROMOTION_YEAR,
)


def _cell():
    return sc.CellKey(
        version_key=DEMAND_BASE_VERSION_KEY, date_key=DEMAND_PRORATION_DATE_KEY,
        measure_key=DEMAND_PRORATION_MEASURE_KEY, product_key=DEMAND_PRORATION_PRODUCT_KEY,
    )


def _snapshot_counts(con):
    dversions = con.execute("SELECT count(*) FROM DVERSIONS").fetchone()[0]
    demand = con.execute("SELECT count(*) FROM TSOP_DEMAND").fetchone()[0]
    ops = con.execute("SELECT count(*) FROM TSOP_OPS").fetchone()[0]
    return dversions, demand, ops


def test_base_moved_since_branch_raises_conflict_and_writes_nothing(writable_db_copy):
    con = writable_db_copy
    scenario = sc.branch(con, name="moved-base", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    sc.mark_evaluated(con, scenario.scenario_id)

    counts_before = _snapshot_counts(con)

    # muta il base "sotto" lo scenario, dopo il branch
    con.execute(
        "UPDATE TSOP_DEMAND SET value = value + 1 WHERE version_key = ? AND product_key = ? "
        "AND date_key = ? AND measure_key = ?",
        [DEMAND_BASE_VERSION_KEY, DEMAND_PRORATION_PRODUCT_KEY, DEMAND_PRORATION_DATE_KEY, DEMAND_PRORATION_MEASURE_KEY],
    )

    with pytest.raises(sc.PromotionConflictError) as exc_info:
        sc.promote(
            con, scenario.scenario_id, cycle_year=PROMOTION_YEAR, cycle_month=1,
            side="DEMAND", status="P", user="tester",
        )
    assert exc_info.value.scenario_id == scenario.scenario_id
    assert exc_info.value.expected_snapshot != exc_info.value.actual_snapshot

    # nessuna scrittura: né una nuova DVERSIONS/TSOP_* (contando anche la
    # riga che abbiamo appena mutato noi stessi, non aggiunta), né lo
    # scenario avanzato di stato.
    dv_after, demand_after, ops_after = _snapshot_counts(con)
    dv_before, demand_before, ops_before = counts_before
    assert dv_after == dv_before, "PromotionConflictError non deve creare nessuna nuova DVERSIONS"
    assert demand_after == demand_before, "nessuna riga TSOP_DEMAND deve essere aggiunta o rimossa"
    assert ops_after == ops_before

    version_name = f"SOP_{PROMOTION_YEAR:04d}_01_DEMAND_P"
    assert con.execute(
        "SELECT 1 FROM DVERSIONS WHERE version_name = ?", [version_name]
    ).fetchone() is None

    state_row = con.execute(
        "SELECT state FROM scenario WHERE scenario_id = ?", [scenario.scenario_id]
    ).fetchone()
    assert state_row[0] == "Evaluated", "lo scenario non deve avanzare a Promoted su un conflitto"


def test_base_untouched_since_branch_promotes_cleanly(writable_db_copy):
    """Caso pulito, in contrasto diretto: nessuna mutazione del base fra
    branch e promote deve promuovere senza sollevare nulla."""
    con = writable_db_copy
    scenario = sc.branch(con, name="clean-base", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    sc.set_cell(con, scenario.scenario_id, _cell(), 500.0, user="tester")
    sc.mark_evaluated(con, scenario.scenario_id)

    result = sc.promote(
        con, scenario.scenario_id, cycle_year=PROMOTION_YEAR, cycle_month=2,
        side="DEMAND", status="P", user="tester",
    )

    assert result.version_name == f"SOP_{PROMOTION_YEAR:04d}_02_DEMAND_P"
    assert con.execute(
        "SELECT 1 FROM DVERSIONS WHERE version_name = ?", [result.version_name]
    ).fetchone() is not None


def test_conflict_is_detected_even_when_the_moved_cell_is_untouched_by_the_scenario(writable_db_copy):
    """AC16 non riguarda solo le celle che lo scenario ha toccato: la base
    intera è impronta con `base_content_digest`, quindi mutare *qualunque*
    riga del base (anche una il cui scenario non ha mai scritto) deve far
    scattare il conflitto — altrimenti la promozione potrebbe combinare
    silenziosamente dati vecchi e nuovi."""
    con = writable_db_copy
    scenario = sc.branch(con, name="untouched-cell-moved", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    sc.set_cell(con, scenario.scenario_id, _cell(), 42.0, user="tester")
    sc.mark_evaluated(con, scenario.scenario_id)

    # muta una riga completamente estranea alla cella scritta dallo scenario
    con.execute(
        "UPDATE TSOP_DEMAND SET value = value + 1 WHERE version_key = ? AND product_key = 6 "
        "AND date_key = 202609",
        [DEMAND_BASE_VERSION_KEY],
    )

    with pytest.raises(sc.PromotionConflictError):
        sc.promote(
            con, scenario.scenario_id, cycle_year=PROMOTION_YEAR, cycle_month=3,
            side="DEMAND", status="P", user="tester",
        )
