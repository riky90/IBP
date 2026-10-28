"""`confirmed_production` era, nel report originale di T3, **un secondo
root esogeno che T2 non aveva dichiarato** in `ibp/semantic/measures.py` —
un buco nel contratto dichiarato: un root che il DAG non conosce è un root
che nient'altro (T4/T7/T10) sa che debba sporcare qualcosa quando cambia.
Il critic lo ha reso un blocking finding, e T2 lo ha chiuso: ora
`MEASURE_DAG["confirmed_production"]` esiste (`depends_on=()`), e
`gap_req_conf.depends_on == ("slots_requested", "confirmed_production")`
(vedi `test_semantic_measures_dag.py`).

Questo file verifica due cose distinte:
1. Il buco è davvero chiuso: `confirmed_production` **è** un nodo del DAG
   dichiarato, raggiungibile da `measures.dirty_set()` — non solo eseguito
   privatamente dal motore.
2. Editarlo nel motore propaga correttamente fino a `gap_req_conf` e
   `value_gap`, ora attraverso il DAG dichiarato (`_node_heights()` legge
   l'altezza di `confirmed_production` da `measures.nodes()`, senza più
   un'iniezione privata — vedi `ibp/engine/engine.py::_node_heights`), non
   attraverso una scorciatoia nota solo al motore.
"""
from __future__ import annotations

import pytest

from ibp.engine import ConfirmedProductionEdit
from ibp.semantic import measures

from _engine_support import CONFIRMED_PRODUCTION_KEY_POOL, MANUFACT_KEY_WITH_RATE, PLANT_FOR_MANUFACT_WITH_RATE


def test_confirmed_production_is_now_a_declared_node_in_the_dag():
    """Inversione del test originale (round critic T3: il buco è stato
    chiuso, non solo documentato): `confirmed_production` è un nodo
    sorgente del DAG dichiarato, e `dirty_set()` lo sa raggiungere fino a
    `value_gap` senza sollevare — è il fatto che rende T4/T7/T10 in grado
    di scoprire questo root leggendo `ibp/semantic/measures.py`, non il
    codice del motore."""
    assert "confirmed_production" in measures.nodes()
    assert measures.nodes()["confirmed_production"].depends_on == ()
    assert measures.dirty_set("confirmed_production") == {
        "confirmed_production", "gap_req_conf", "value_gap",
    }


def test_gap_req_conf_declares_confirmed_production_as_a_real_dependency():
    """Non basta che il nodo esista isolato: `gap_req_conf` deve dichiararlo
    come propria dipendenza, insieme a `slots_requested` — è ciò che rende
    `dirty_set("confirmed_production")` e `dirty_set("slots_requested")`
    entrambi capaci di raggiungere `gap_req_conf`/`value_gap`."""
    assert set(measures.nodes()["gap_req_conf"].depends_on) == {
        "slots_requested", "confirmed_production",
    }


def test_editing_confirmed_production_propagates_to_gap_and_value_gap(engine):
    manufact, plant, date = MANUFACT_KEY_WITH_RATE, PLANT_FOR_MANUFACT_WITH_RATE, 202609
    key = (manufact, plant, date)

    baseline = engine.full_recalculate()
    slots_before = baseline.values["slots_requested"].get(key, 0.0)

    result = engine.recalculate([ConfirmedProductionEdit(manufact, plant, date, 42.0)])

    assert result.values["confirmed_production"][key] == 42.0
    # gap_req_conf = slots_requested - confirmed_production (slots_requested
    # non cambia per un edit su confirmed_production: solo il sottraendo cambia)
    assert result.values["gap_req_conf"][key] == pytest.approx(slots_before - 42.0)
    # manufact_key 1662 ha copertura rate_card (Cluster 10): value_gap deve esistere
    assert key in result.values["value_gap"]
    expected_rate = result.values["value_gap"][key] / result.values["gap_req_conf"][key]
    assert expected_rate > 0


def test_confirmed_production_edit_changes_gap_by_exactly_the_delta(engine):
    """Isola l'effetto dell'edit: due chiamate consecutive con valori
    diversi sulla stessa chiave devono spostare gap_req_conf esattamente
    della differenza fra i due valori confermati (slots_requested non è
    toccato da un ConfirmedProductionEdit)."""
    manufact, plant, date = CONFIRMED_PRODUCTION_KEY_POOL[3]
    key = (manufact, plant, date)

    result_a = engine.recalculate([ConfirmedProductionEdit(manufact, plant, date, 100.0)])
    gap_a = result_a.values["gap_req_conf"][key]

    result_b = engine.recalculate([ConfirmedProductionEdit(manufact, plant, date, 175.0)])
    gap_b = result_b.values["gap_req_conf"][key]

    assert gap_a - gap_b == pytest.approx(75.0)


def test_confirmed_production_edit_does_not_touch_derived_manufacturing_demand(engine):
    """`confirmed_production` entra nel sottografo direttamente su
    gap_req_conf (vedi `RecalcEngine.recalculate`, ramo
    `ConfirmedProductionEdit`): non deve mai risalire a
    derived_manufacturing_demand, che dipende solo da requested_production."""
    manufact, plant, date = MANUFACT_KEY_WITH_RATE, PLANT_FOR_MANUFACT_WITH_RATE, 202610
    baseline = engine.full_recalculate()
    dmd_before = dict(baseline.values["derived_manufacturing_demand"])

    result = engine.recalculate([ConfirmedProductionEdit(manufact, plant, date, 55555.0)])

    assert result.values["derived_manufacturing_demand"] == dmd_before
