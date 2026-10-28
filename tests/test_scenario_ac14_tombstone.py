"""AC14 — tombstone: una cella cancellata in uno scenario non deve mai
ricomparire dal base, e la rappresentazione deve essere `is_deleted=TRUE`
esplicito, mai un `value=NULL` usato come sentinella implicita (che sarebbe
indistinguibile da "nessuno ha mai scritto qui"). Ogni test lavora su una
copia scrivibile del DB reale (`writable_db_copy`), mai sul file reale."""
from __future__ import annotations

import ibp.scenario as sc

from _scenario_support import (
    DEMAND_BASE_VERSION_KEY,
    DEMAND_PRORATION_BASE_SUM,
    DEMAND_PRORATION_DATE_KEY,
    DEMAND_PRORATION_MEASURE_KEY,
    DEMAND_PRORATION_PRODUCT_KEY,
)


def _cell(**overrides):
    defaults = dict(
        version_key=DEMAND_BASE_VERSION_KEY,
        date_key=DEMAND_PRORATION_DATE_KEY,
        measure_key=DEMAND_PRORATION_MEASURE_KEY,
        product_key=DEMAND_PRORATION_PRODUCT_KEY,
    )
    defaults.update(overrides)
    return sc.CellKey(**defaults)


def test_delete_then_read_does_not_resurrect_the_base_value(writable_db_copy):
    con = writable_db_copy
    scenario = sc.branch(con, name="tombstone", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    cell = _cell()

    before = sc.resolve_cell(con, scenario.scenario_id, cell)
    assert before.source == "base"
    assert before.value == DEMAND_PRORATION_BASE_SUM

    sc.delete_cell(con, scenario.scenario_id, cell, user="tester")
    after = sc.resolve_cell(con, scenario.scenario_id, cell)

    assert after.is_deleted is True
    assert after.value is None
    assert after.source == "overlay"
    # il base stesso resta intatto — solo lo scenario "vede" il tombstone
    base_still_there = sc.resolve_cell(con, DEMAND_BASE_VERSION_KEY, cell)
    assert base_still_there.value == DEMAND_PRORATION_BASE_SUM


def test_delete_is_stored_as_explicit_flag_not_a_bare_null(writable_db_copy):
    """Verifica diretta sulla riga `overlay`: `is_deleted=TRUE`, non un
    `value=NULL` che il chiamante dovrebbe interpretare da solo."""
    con = writable_db_copy
    scenario = sc.branch(con, name="tombstone-raw", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    cell = _cell()
    sc.delete_cell(con, scenario.scenario_id, cell, user="tester")

    row = con.execute(
        "SELECT value, is_deleted FROM overlay WHERE scenario_id = ? AND product_key = ? "
        "AND date_key = ? AND measure_key = ?",
        [scenario.scenario_id, DEMAND_PRORATION_PRODUCT_KEY, DEMAND_PRORATION_DATE_KEY, DEMAND_PRORATION_MEASURE_KEY],
    ).fetchone()
    assert row is not None, "delete_cell() deve scrivere una riga overlay anche per una cella mai scritta prima"
    value, is_deleted = row
    assert is_deleted is True
    assert value is None


def test_delete_then_re_set_resurrects_via_a_real_write_not_the_tombstone(writable_db_copy):
    """Cancellare e poi riscrivere la stessa cella deve tornare al valore
    nuovo — il tombstone precedente non deve "vincere" su una scrittura
    successiva più recente."""
    con = writable_db_copy
    scenario = sc.branch(con, name="delete-then-set", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    cell = _cell()

    sc.delete_cell(con, scenario.scenario_id, cell, user="tester")
    sc.set_cell(con, scenario.scenario_id, cell, 777.0, user="tester")
    result = sc.resolve_cell(con, scenario.scenario_id, cell)

    assert result.is_deleted is False
    assert result.value == 777.0
    assert result.source == "overlay"


def test_delete_in_parent_scenario_is_inherited_by_nested_child(writable_db_copy):
    """AC14 + AC15: un figlio che non ha mai scritto quella cella deve
    vedere il tombstone del genitore, non il base."""
    con = writable_db_copy
    parent = sc.branch(con, name="parent", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    cell = _cell()
    sc.delete_cell(con, parent.scenario_id, cell, user="tester")

    child = sc.branch(
        con, name="child", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester",
        parent_scenario_id=parent.scenario_id,
    )
    child_view = sc.resolve_cell(con, child.scenario_id, cell)

    assert child_view.is_deleted is True
    assert child_view.value is None
    assert child_view.source == "overlay"


def test_child_can_resurrect_a_cell_its_parent_deleted(writable_db_copy):
    """Un figlio può sovrascrivere il tombstone del genitore con un valore
    proprio — l'overlay più vicino alla foglia vince (stessa regola di
    AC15, non solo di AC14)."""
    con = writable_db_copy
    parent = sc.branch(con, name="parent2", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    cell = _cell()
    sc.delete_cell(con, parent.scenario_id, cell, user="tester")

    child = sc.branch(
        con, name="child2", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester",
        parent_scenario_id=parent.scenario_id,
    )
    sc.set_cell(con, child.scenario_id, cell, 55.5, user="tester")
    child_view = sc.resolve_cell(con, child.scenario_id, cell)
    parent_view = sc.resolve_cell(con, parent.scenario_id, cell)

    assert child_view.is_deleted is False
    assert child_view.value == 55.5
    # il genitore, non riscritto, resta cancellato per sé stesso
    assert parent_view.is_deleted is True


def test_delete_a_cell_with_no_prior_overlay_row_still_tombstones_correctly(writable_db_copy):
    """`delete_cell` su una cella mai toccata da questo scenario prima
    (nessuna riga overlay preesistente da aggiornare) deve comunque produrre
    un tombstone corretto, non un errore né un no-op silenzioso."""
    con = writable_db_copy
    scenario = sc.branch(con, name="fresh-delete", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    cell = _cell()

    row_before = con.execute(
        "SELECT overlay_id FROM overlay WHERE scenario_id = ?", [scenario.scenario_id]
    ).fetchall()
    assert row_before == []  # non-vacuo: davvero nessuna riga overlay ancora

    sc.delete_cell(con, scenario.scenario_id, cell, user="tester")
    result = sc.resolve_cell(con, scenario.scenario_id, cell)
    assert result.is_deleted is True
    assert result.value is None
