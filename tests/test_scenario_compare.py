"""`compare(ref_a, ref_b)` deve funzionare indifferentemente su tutte e tre
le combinazioni (versione/versione, scenario/scenario, versione/scenario),
e il caso "scenario contro il proprio base" deve riportare **solo** le
celle davvero sovrascritte — non un sottoinsieme arbitrario di celle mai
toccate, che è esattamente il tipo di rumore che renderebbe un confronto
scenari inutilizzabile in pratica (troppi "cambiamenti" da rivedere per
trovare quelli veri)."""
from __future__ import annotations

import ibp.scenario as sc

from _scenario_support import (
    DEMAND_BASE_VERSION_KEY,
    DEMAND_PRORATION_DATE_KEY,
    DEMAND_PRORATION_MEASURE_KEY,
    DEMAND_PRORATION_PRODUCT_KEY,
)

_OVERRIDE_VALUE = 999999.0


def _cell():
    return sc.CellKey(
        version_key=DEMAND_BASE_VERSION_KEY, date_key=DEMAND_PRORATION_DATE_KEY,
        measure_key=DEMAND_PRORATION_MEASURE_KEY, product_key=DEMAND_PRORATION_PRODUCT_KEY,
    )


def test_compare_version_against_itself_is_all_zero(writable_db_copy):
    con = writable_db_copy
    rows = sc.compare(con, DEMAND_BASE_VERSION_KEY, DEMAND_BASE_VERSION_KEY)
    assert rows  # non-vacuo
    assert all(r.delta == 0.0 and r.value_a == r.value_b for r in rows)


def test_compare_scenario_against_scenario(writable_db_copy):
    con = writable_db_copy
    a = sc.branch(con, name="cmp-A", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    b = sc.branch(con, name="cmp-B", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    cell = _cell()
    sc.set_cell(con, a.scenario_id, cell, 100.0, user="tester")
    sc.set_cell(con, b.scenario_id, cell, 400.0, user="tester")

    rows = sc.compare(con, a.scenario_id, b.scenario_id)
    matching = [
        r for r in rows
        if r.product_key == DEMAND_PRORATION_PRODUCT_KEY and r.date_key == DEMAND_PRORATION_DATE_KEY
        and r.measure_key == DEMAND_PRORATION_MEASURE_KEY
    ]
    assert len(matching) == 1
    row = matching[0]
    assert row.value_a == 100.0
    assert row.value_b == 400.0
    assert row.delta == 300.0


def test_compare_version_against_scenario_shows_the_override(writable_db_copy):
    con = writable_db_copy
    scenario = sc.branch(con, name="cmp-mixed", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    cell = _cell()
    sc.set_cell(con, scenario.scenario_id, cell, _OVERRIDE_VALUE, user="tester")

    rows = sc.compare(con, DEMAND_BASE_VERSION_KEY, scenario.scenario_id)
    matching = [
        r for r in rows
        if r.product_key == DEMAND_PRORATION_PRODUCT_KEY and r.date_key == DEMAND_PRORATION_DATE_KEY
        and r.measure_key == DEMAND_PRORATION_MEASURE_KEY
    ]
    assert len(matching) == 1
    assert matching[0].value_b == _OVERRIDE_VALUE
    assert matching[0].delta == _OVERRIDE_VALUE - matching[0].value_a


def test_compare_scenario_against_its_own_base_returns_only_truly_overridden_cells(writable_db_copy):
    """Il caso esplicitamente richiesto: uno scenario con **una sola**
    cella sovrascritta, confrontato col proprio base, deve riportare
    **esattamente** quella cella con delta diverso da zero — nessun'altra.

    TROVATO SCRIVENDO QUESTO TEST (non un'aspettativa sbagliata): la
    versione base usata ha 100224+ righe `TSOP_DEMAND`; `compare()` chiama
    `materialize_ref()` due volte (una per lato), ciascuna delle quali fa
    un proprio `SUM(value) GROUP BY ...` via DuckDB. Verificato isolatamente
    (`ibp.scenario.overlay.materialize_version` chiamato due volte di fila
    sullo stesso `version_key`, DB invariato): le due chiamate producono
    migliaia di valori che differiscono nell'ultimo bit (~1e-13), quasi
    certamente per via della somma parallela di DuckDB che non garantisce lo
    stesso ordine di riduzione fra due esecuzioni dello stesso piano. Il
    risultato è che `compare()` riporta migliaia di celle come "cambiate"
    (`delta != 0.0`) che nessuno ha mai toccato — la stessa cosa che questo
    AC vieta esplicitamente ("solo le celle davvero sovrascritte")."""
    con = writable_db_copy
    scenario = sc.branch(con, name="cmp-self-base", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    cell = _cell()
    sc.set_cell(con, scenario.scenario_id, cell, _OVERRIDE_VALUE, user="tester")

    rows = sc.compare(con, DEMAND_BASE_VERSION_KEY, scenario.scenario_id)
    changed = [r for r in rows if r.delta != 0.0]
    changed_keys = {(r.product_key, r.plant_key, r.date_key, r.measure_key) for r in changed}
    expected_key = (DEMAND_PRORATION_PRODUCT_KEY, None, DEMAND_PRORATION_DATE_KEY, DEMAND_PRORATION_MEASURE_KEY)

    assert changed_keys == {expected_key}, (
        f"compare() ha riportato {len(changed)} celle come cambiate contro 1 sola cella "
        f"realmente sovrascritta; le altre {len(changed) - 1} sono con ogni evidenza rumore "
        "di somma in virgola mobile (vedi docstring del test)"
    )
