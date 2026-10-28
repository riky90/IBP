"""T2 done_when #1: ogni transizione valida dichiarata deve riuscire, ogni
transizione illegale deve sollevare l'eccezione specifica (mai una
`Exception` generica, mai un fallimento silenzioso). Copre tutte le macchine
a stati dichiarate in `ibp.domain` più il caso STAT_03 (AC4/AC20).
"""
from __future__ import annotations

import datetime as dt

import pytest

from ibp.domain import (
    CYCLE_PHASE_STAT_MACHINE,
    GAP_STATUS,
    PORTFOLIO_ITEM_LIFECYCLE,
    PROJECT_STATE,
    REVIEW_STATUS,
    SCENARIO_STATE,
    CyclePhase,
    Gap,
    InvalidTransitionError,
    PhaseClosedError,
    PortfolioItem,
    Project,
    ReviewInstance,
    Scenario,
    UnknownStateError,
    build_phase_sequence_machine,
)
from ibp.domain.cycle import PhaseDef

# ---------------------------------------------------------------------------
# Ogni transizione dichiarata deve riuscire (positivo), esaustivo per ogni
# macchina, più una transizione illegale rappresentativa (negativo).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "machine",
    [
        PORTFOLIO_ITEM_LIFECYCLE,
        PROJECT_STATE,
        GAP_STATUS,
        SCENARIO_STATE,
        REVIEW_STATUS,
        CYCLE_PHASE_STAT_MACHINE,
    ],
    ids=lambda m: m.name,
)
def test_every_declared_transition_succeeds(machine):
    for from_state, targets in machine.transitions.items():
        for to_state in targets:
            # validate() non deve sollevare per una transizione dichiarata.
            machine.validate(from_state, to_state)


def test_portfolio_item_illegal_transition_raises_specific_error():
    item = PortfolioItem(item_id=1, product_key=None, name="X", lifecycle_state="Concept")
    with pytest.raises(InvalidTransitionError) as exc_info:
        item.transition_to("Mature")  # salta stadi, non dichiarata
    assert exc_info.value.machine == "portfolio_item.lifecycle_state"
    assert exc_info.value.from_state == "Concept"
    assert exc_info.value.to_state == "Mature"


def test_portfolio_item_valid_transition_succeeds():
    item = PortfolioItem(item_id=1, product_key=None, name="X", lifecycle_state="Concept")
    moved = item.transition_to("Development")
    assert moved.lifecycle_state == "Development"
    assert item.lifecycle_state == "Concept"  # immutabile: l'originale non cambia


def test_portfolio_item_retired_is_terminal():
    item = PortfolioItem(item_id=1, product_key=None, name="X", lifecycle_state="Retired")
    with pytest.raises(InvalidTransitionError):
        item.transition_to("Concept")


def test_project_illegal_backward_transition_raises():
    project = Project(project_id=1, portfolio_item_id=1, name="P", state="Approved")
    with pytest.raises(InvalidTransitionError):
        project.transition_to("Proposed")


def test_project_close_from_any_nonterminal_state_succeeds():
    for state in ("Proposed", "Assessed", "Resourced", "Approved", "InExecution"):
        project = Project(project_id=1, portfolio_item_id=1, name="P", state=state)
        assert project.transition_to("Closed").state == "Closed"


def test_gap_direct_escalation_from_open_succeeds():
    gap = Gap(
        gap_id=1, cycle_id=1, scope="s", dimension_slice_json="{}", measure_key=None,
        plan_value=1.0, target_value=2.0, delta_units=1.0, delta_value=1.0,
        owner="o", category="c", status="Open",
    )
    assert gap.transition_to("Escalated").status == "Escalated"


def test_gap_illegal_transition_from_closed_raises():
    gap = Gap(
        gap_id=1, cycle_id=1, scope="s", dimension_slice_json="{}", measure_key=None,
        plan_value=1.0, target_value=2.0, delta_units=1.0, delta_value=1.0,
        owner="o", category="c", status="Closed",
    )
    with pytest.raises(InvalidTransitionError):
        gap.transition_to("Open")


def test_scenario_evaluated_back_to_draft_is_allowed():
    scenario = Scenario(
        scenario_id="s1", name="n", base_version_key=1, base_snapshot_id="snap",
        parent_scenario_id=None, owner="o", state="Evaluated", created_at=dt.datetime.now(),
    )
    assert scenario.transition_to("Draft").state == "Draft"


def test_scenario_promoted_is_terminal():
    scenario = Scenario(
        scenario_id="s1", name="n", base_version_key=1, base_snapshot_id="snap",
        parent_scenario_id=None, owner="o", state="Promoted", created_at=dt.datetime.now(),
    )
    with pytest.raises(InvalidTransitionError):
        scenario.transition_to("Draft")


def test_review_instance_skip_to_closed_from_scheduled_allowed():
    review = ReviewInstance(
        review_id=1, cycle_id=1, review_type="Demand", day_start=1, day_end=5,
        status="Scheduled", gate=None,
    )
    assert review.transition_to("Closed").status == "Closed"


def test_review_instance_illegal_backward_transition_raises():
    review = ReviewInstance(
        review_id=1, cycle_id=1, review_type="Demand", day_start=1, day_end=5,
        status="Closed", gate=None,
    )
    with pytest.raises(InvalidTransitionError):
        review.transition_to("InProgress")


def test_unknown_state_raises_unknown_state_error_not_invalid_transition():
    item = PortfolioItem(item_id=1, product_key=None, name="X", lifecycle_state="Concept")
    with pytest.raises(UnknownStateError) as exc_info:
        item.transition_to("NotARealState")
    assert exc_info.value.state == "NotARealState"


def test_unknown_starting_state_raises_unknown_state_error():
    with pytest.raises(UnknownStateError):
        PORTFOLIO_ITEM_LIFECYCLE.validate("Bogus", "Concept")


# ---------------------------------------------------------------------------
# STAT_01 -> STAT_02 -> STAT_03, e il rifiuto di scrittura su STAT_03 (AC4/AC20)
# ---------------------------------------------------------------------------


def _phase(stat_state: str, name: str = "Demand") -> CyclePhase:
    return CyclePhase(
        phase_id=1, cycle_id=1, phase_no=1, name=name,
        day_start=1, day_end=5, stat_state=stat_state, gate=None,
    )


def test_stat_progression_01_to_02_to_03():
    phase = _phase("STAT_01")
    phase = phase.advance_stat()
    assert phase.stat_state == "STAT_02"
    phase = phase.advance_stat()
    assert phase.stat_state == "STAT_03"


def test_stat_cannot_skip_01_directly_to_03():
    with pytest.raises(InvalidTransitionError):
        CYCLE_PHASE_STAT_MACHINE.validate("STAT_01", "STAT_03")


def test_stat_03_write_is_rejected_with_phase_closed_error():
    phase = _phase("STAT_03", name="IntegratedReconciliation")
    with pytest.raises(PhaseClosedError) as exc_info:
        phase.assert_writable()
    assert exc_info.value.phase_name == "IntegratedReconciliation"
    assert exc_info.value.stat_state == "STAT_03"


def test_stat_01_and_02_writes_are_allowed():
    for stat_state in ("STAT_01", "STAT_02"):
        phase = _phase(stat_state)
        phase.assert_writable()  # non deve sollevare


def test_stat_03_advance_also_raises_phase_closed_not_invalid_transition():
    phase = _phase("STAT_03")
    with pytest.raises(PhaseClosedError):
        phase.advance_stat()


# ---------------------------------------------------------------------------
# build_phase_sequence_machine: la sequenza di fase è dato, non costante Python
# ---------------------------------------------------------------------------


def test_phase_sequence_machine_built_from_arbitrary_phase_defs():
    phases = [
        PhaseDef(phase_id=1, cycle_id=99, phase_no=1, name="Portfolio", day_start=1, day_end=5, stat_state="STAT_01", gate=None),
        PhaseDef(phase_id=2, cycle_id=99, phase_no=2, name="Demand", day_start=6, day_end=10, stat_state="STAT_01", gate=None),
        PhaseDef(phase_id=3, cycle_id=99, phase_no=3, name="Gate", day_start=11, day_end=12, stat_state="STAT_03", gate="Exec"),
    ]
    machine = build_phase_sequence_machine(phases)
    machine.validate("Portfolio", "Demand")
    machine.validate("Demand", "Gate")
    with pytest.raises(InvalidTransitionError):
        machine.validate("Portfolio", "Gate")  # salta Demand
    assert machine.allowed_from("Gate") == ()  # ultima fase è terminale
