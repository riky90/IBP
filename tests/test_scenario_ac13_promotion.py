"""AC13 — branch -> modifica sparsa -> confronto -> promozione che crea una
**nuova** istanza `DVERSIONS`, mai una mutazione di un'istanza esistente.
Il nome è portante (le misure DAX di Power BI lo ricostruiscono come
stringa): si verifica il nome esatto prodotto, non solo che una riga sia
comparsa."""
from __future__ import annotations

import pytest

import ibp.scenario as sc
from ibp.domain.errors import InvalidTransitionError

from _scenario_support import (
    DEMAND_BASE_VERSION_KEY,
    DEMAND_PRORATION_DATE_KEY,
    DEMAND_PRORATION_MEASURE_KEY,
    DEMAND_PRORATION_PRODUCT_KEY,
    OPS_BASE_VERSION_KEY,
    OPS_PRORATION_DATE_KEY,
    OPS_PRORATION_MEASURE_KEY,
    OPS_PRORATION_PLANT_KEY,
    PROMOTION_YEAR,
)


def test_promotion_creates_dversions_with_exact_conventional_name(writable_db_copy):
    con = writable_db_copy
    scenario = sc.branch(con, name="ac13-name", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    sc.mark_evaluated(con, scenario.scenario_id)

    result = sc.promote(
        con, scenario.scenario_id, cycle_year=PROMOTION_YEAR, cycle_month=4,
        side="DEMAND", status="R", user="tester",
    )

    assert result.version_name == "SOP_2099_04_DEMAND_R"
    row = con.execute(
        "SELECT version_name, cycle_year, cycle_month, side, status FROM DVERSIONS WHERE version_key = ?",
        [result.version_key],
    ).fetchone()
    assert row == ("SOP_2099_04_DEMAND_R", PROMOTION_YEAR, 4, "DEMAND", "R")


@pytest.mark.parametrize("side,status", [("DEMAND", "P"), ("DEMAND", "R"), ("SUPPLY", "A"), ("SUPPLY", "C")])
def test_promotion_name_matches_convention_for_every_side_status_combination(writable_db_copy, side, status):
    con = writable_db_copy
    base = DEMAND_BASE_VERSION_KEY if side == "DEMAND" else OPS_BASE_VERSION_KEY
    scenario = sc.branch(con, name=f"ac13-{side}-{status}", base_version_key=base, owner="tester")
    sc.mark_evaluated(con, scenario.scenario_id)

    # month scelto per non collidere fra le 4 combinazioni della stessa run
    month = {"P": 5, "R": 6, "A": 7, "C": 8}[status]
    result = sc.promote(
        con, scenario.scenario_id, cycle_year=PROMOTION_YEAR, cycle_month=month,
        side=side, status=status, user="tester",
    )
    assert result.version_name == f"SOP_{PROMOTION_YEAR:04d}_{month:02d}_{side}_{status}"


def test_promotion_never_mutates_an_existing_dversions_row(writable_db_copy):
    con = writable_db_copy
    before = con.execute(
        "SELECT version_key, version_name, cycle_year, cycle_month, side, status FROM DVERSIONS ORDER BY version_key"
    ).fetchall()

    scenario = sc.branch(con, name="no-mutation", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    sc.set_cell(
        con, scenario.scenario_id,
        sc.CellKey(
            version_key=DEMAND_BASE_VERSION_KEY, date_key=DEMAND_PRORATION_DATE_KEY,
            measure_key=DEMAND_PRORATION_MEASURE_KEY, product_key=DEMAND_PRORATION_PRODUCT_KEY,
        ),
        1234.0, user="tester",
    )
    sc.mark_evaluated(con, scenario.scenario_id)
    sc.promote(
        con, scenario.scenario_id, cycle_year=PROMOTION_YEAR, cycle_month=9,
        side="DEMAND", status="P", user="tester",
    )

    before_keys = [r[0] for r in before]
    placeholders = ", ".join("?" for _ in before_keys)
    after = con.execute(
        f"SELECT version_key, version_name, cycle_year, cycle_month, side, status FROM DVERSIONS "
        f"WHERE version_key IN ({placeholders}) ORDER BY version_key",
        before_keys,
    ).fetchall()
    # ogni riga preesistente deve comparire identica, nessuna persa né alterata
    assert after == before

    # anche il contenuto del base (TSOP_DEMAND) non deve essere toccato
    base_sum = con.execute(
        "SELECT SUM(value) FROM TSOP_DEMAND WHERE version_key = ? AND product_key = ? "
        "AND date_key = ? AND measure_key = ?",
        [DEMAND_BASE_VERSION_KEY, DEMAND_PRORATION_PRODUCT_KEY, DEMAND_PRORATION_DATE_KEY, DEMAND_PRORATION_MEASURE_KEY],
    ).fetchone()[0]
    assert base_sum == pytest.approx(123.025)  # invariato, nonostante l'edit 1234.0 nello scenario


def test_write_to_an_existing_instance_name_is_rejected(writable_db_copy):
    """Promuovere a coordinate che producono un nome già esistente in
    DVERSIONS deve essere rifiutato — mai sovrascritto."""
    con = writable_db_copy
    scenario = sc.branch(con, name="duplicate-target", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    sc.mark_evaluated(con, scenario.scenario_id)

    existing_name = con.execute(
        "SELECT version_name, cycle_year, cycle_month, side, status FROM DVERSIONS WHERE version_key = ?",
        [DEMAND_BASE_VERSION_KEY],
    ).fetchone()
    version_name, cycle_year, cycle_month, side, status = existing_name

    with pytest.raises(sc.DuplicateVersionError) as exc_info:
        sc.promote(
            con, scenario.scenario_id, cycle_year=cycle_year, cycle_month=cycle_month,
            side=side, status=status, user="tester",
        )
    assert exc_info.value.version_name == version_name

    unchanged_count = con.execute(
        "SELECT count(*) FROM DVERSIONS WHERE version_name = ?", [version_name]
    ).fetchone()[0]
    assert unchanged_count == 1  # non duplicata, non sovrascritta


def test_scenario_ends_in_promoted_state(writable_db_copy):
    con = writable_db_copy
    scenario = sc.branch(con, name="end-state", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    sc.mark_evaluated(con, scenario.scenario_id)
    result = sc.promote(
        con, scenario.scenario_id, cycle_year=PROMOTION_YEAR, cycle_month=10,
        side="DEMAND", status="P", user="tester",
    )
    assert result.scenario.state == "Promoted"
    persisted_state = con.execute(
        "SELECT state FROM scenario WHERE scenario_id = ?", [scenario.scenario_id]
    ).fetchone()[0]
    assert persisted_state == "Promoted"


def test_promoting_a_draft_scenario_is_rejected_not_silently_evaluated(writable_db_copy):
    """`Draft -> Promoted` non è una transizione dichiarata
    (`SCENARIO_TRANSITIONS`, T2): promuovere uno scenario mai valutato deve
    sollevare, non promuoverlo comunque."""
    con = writable_db_copy
    scenario = sc.branch(con, name="never-evaluated", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    assert scenario.state == "Draft"

    with pytest.raises(InvalidTransitionError):
        sc.promote(
            con, scenario.scenario_id, cycle_year=PROMOTION_YEAR, cycle_month=11,
            side="DEMAND", status="P", user="tester",
        )


def test_promoting_an_already_promoted_scenario_is_rejected(writable_db_copy):
    con = writable_db_copy
    scenario = sc.branch(con, name="double-promote", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    sc.mark_evaluated(con, scenario.scenario_id)
    sc.promote(
        con, scenario.scenario_id, cycle_year=PROMOTION_YEAR, cycle_month=12,
        side="DEMAND", status="P", user="tester",
    )
    with pytest.raises(InvalidTransitionError):
        sc.promote(
            con, scenario.scenario_id, cycle_year=PROMOTION_YEAR + 1, cycle_month=1,
            side="DEMAND", status="P", user="tester",
        )


def test_ops_side_promotion_materialises_tsop_ops_rows(writable_db_copy):
    con = writable_db_copy
    cell = sc.CellKey(
        version_key=OPS_BASE_VERSION_KEY, date_key=OPS_PRORATION_DATE_KEY,
        measure_key=OPS_PRORATION_MEASURE_KEY, plant_key=OPS_PRORATION_PLANT_KEY,
    )
    scenario = sc.branch(con, name="ops-promotion", base_version_key=OPS_BASE_VERSION_KEY, owner="tester")
    sc.set_cell(con, scenario.scenario_id, cell, 1000.0, user="tester")
    sc.mark_evaluated(con, scenario.scenario_id)

    result = sc.promote(
        con, scenario.scenario_id, cycle_year=PROMOTION_YEAR + 2, cycle_month=1,
        side="SUPPLY", status="A", user="tester",
    )

    total = con.execute(
        "SELECT SUM(value) FROM TSOP_OPS WHERE version_key = ? AND plant_key = ? "
        "AND date_key = ? AND measure_key = ?",
        [result.version_key, OPS_PRORATION_PLANT_KEY, OPS_PRORATION_DATE_KEY, OPS_PRORATION_MEASURE_KEY],
    ).fetchone()[0]
    assert total == pytest.approx(1000.0)
