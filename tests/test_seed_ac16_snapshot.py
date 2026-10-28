"""Il seed deve spedire scenari su cui AC16 **verifica davvero qualcosa**.

Fino al 2026-09-11 `db/seed/scenario.py` scriveva `base_snapshot_id` come
`SNAP_{version_name}_{iso_ts}`: un'etichetta, non un'impronta di contenuto.
`promote._snapshot_check()` la classificava quindi "non verificabile" e
lasciava passare la promozione senza confronto — sui due scenari seminati,
che sono gli unici promuovibili spediti e quelli che la demo end-to-end di
T12 attraversa. Il test AC16 esistente (`test_scenario_ac16_conflict.py`)
non lo intercettava perché costruisce i propri scenari con `branch()`, che
l'impronta la scrive correttamente.

Questi test guardano il **dato spedito**, non il codice: sono la rete che
impedisce a una regressione del seed di rendere AC16 di nuovo cieco senza
che nessun test diventi rosso.
"""
from __future__ import annotations

import importlib

from ibp.domain.scenario import Scenario
from ibp.scenario.overlay import base_content_digest

promote_module = importlib.import_module("ibp.scenario.promote")

_SCENARIO_COLUMNS = (
    "scenario_id, name, base_version_key, base_snapshot_id, parent_scenario_id, "
    "owner, state, created_at"
)


def _seeded_scenarios(con) -> list[Scenario]:
    rows = con.execute(
        f"SELECT {_SCENARIO_COLUMNS} FROM scenario ORDER BY scenario_id"
    ).fetchall()
    return [Scenario(*row) for row in rows]


def test_seed_ships_scenarios(con):
    """Guardia sulla guardia: se il seed smettesse di spedire scenari, i due
    test sotto passerebbero a vuoto su una lista vuota."""
    assert len(_seeded_scenarios(con)) >= 2


def test_seeded_base_snapshot_is_a_content_digest(con):
    """Formato canonico `SNAP_{version_key}_{sha256}` e digest che combacia
    col contenuto corrente della base — non un'etichetta col nome della
    versione e un timestamp."""
    for scenario in _seeded_scenarios(con):
        match = promote_module._SNAPSHOT_RE.match(scenario.base_snapshot_id or "")
        assert match is not None, (
            f"{scenario.scenario_id}: base_snapshot_id={scenario.base_snapshot_id!r} "
            "non è nel formato canonico prodotto da branch() — promote() lo "
            "dichiarerebbe non verificabile e AC16 passerebbe a vuoto"
        )
        assert int(match.group(1)) == scenario.base_version_key
        assert match.group(2) == base_content_digest(con, scenario.base_version_key)


def test_seeded_scenarios_are_verifiable_and_unmoved(con):
    """`_snapshot_check()` sul dato spedito: verificabile, e base non mossa
    (il DB appena costruito non è stato toccato dopo il branch)."""
    for scenario in _seeded_scenarios(con):
        verifiable, moved = promote_module._snapshot_check(con, scenario)
        assert verifiable, f"{scenario.scenario_id}: AC16 non verificabile sul dato seminato"
        assert not moved, f"{scenario.scenario_id}: base già mossa su un DB appena costruito"


def test_moved_base_is_detected_on_a_seeded_scenario(writable_db_copy):
    """Il lato che conta: muovere la base di uno scenario **seminato** deve
    produrre `moved=True`. È esattamente ciò che prima non poteva accadere.
    Gira su `writable_db_copy`, mai su `data/ibp.duckdb`."""
    con = writable_db_copy
    scenario = _seeded_scenarios(con)[0]

    row = con.execute(
        "SELECT product_key, division_key, date_key, measure_key FROM TSOP_DEMAND "
        "WHERE version_key = ? ORDER BY product_key, division_key, date_key, measure_key "
        "LIMIT 1",
        [scenario.base_version_key],
    ).fetchone()
    assert row is not None, "la base dello scenario seminato non ha righe TSOP_DEMAND"

    con.execute(
        "UPDATE TSOP_DEMAND SET value = value + 1 WHERE version_key = ? "
        "AND product_key = ? AND division_key = ? AND date_key = ? AND measure_key = ?",
        [scenario.base_version_key, *row],
    )

    verifiable, moved = promote_module._snapshot_check(con, scenario)
    assert verifiable
    assert moved, (
        "la base è stata modificata ma _snapshot_check() non lo rileva: "
        "AC16 è cieco sugli scenari seminati"
    )
