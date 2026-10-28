"""AC15 — la cache key include lo stack intero: A non serve mai aggregati
di B. Questo è, per esplicita nota del coordinatore, il tipo di difetto più
invisibile del sistema — un numero sbagliato che sembra plausibile. I test
qui verificano sia la lettura diretta (resolve_cell/materialize) sia la
chiave di cache stessa (ScenarioStack.cache_key()), incluso il caso
negativo esplicito: una cache ingenua chiavata solo su base_version_key
servirebbe l'aggregato sbagliato — questo file lo costruisce e dimostra che
`cache_key()` non colliderebbe."""
from __future__ import annotations

import ibp.scenario as sc

from _scenario_support import DEMAND_BASE_VERSION_KEY, DEMAND_PRORATION_DATE_KEY, DEMAND_PRORATION_MEASURE_KEY, DEMAND_PRORATION_PRODUCT_KEY


def _cell(product_key=DEMAND_PRORATION_PRODUCT_KEY, date_key=DEMAND_PRORATION_DATE_KEY):
    return sc.CellKey(
        version_key=DEMAND_BASE_VERSION_KEY, date_key=date_key,
        measure_key=DEMAND_PRORATION_MEASURE_KEY, product_key=product_key,
    )


def test_value_written_in_scenario_a_is_never_visible_from_sibling_b(writable_db_copy):
    con = writable_db_copy
    a = sc.branch(con, name="A", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    b = sc.branch(con, name="B", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    cell = _cell()

    base_value = sc.resolve_cell(con, DEMAND_BASE_VERSION_KEY, cell).value
    sc.set_cell(con, a.scenario_id, cell, 999999.0, user="tester")

    view_a = sc.resolve_cell(con, a.scenario_id, cell)
    view_b = sc.resolve_cell(con, b.scenario_id, cell)

    assert view_a.value == 999999.0
    assert view_b.value == base_value  # B non vede l'edit di A
    assert view_b.source == "base"


def test_three_level_nested_chain_resolves_with_correct_precedence(writable_db_copy):
    """Nonno scrive X, padre scrive Y (ed eredita X), figlio scrive Z (ed
    eredita X e Y): la foglia deve vedere tutti e tre, ciascuno dal layer
    giusto, nell'ordine radice -> foglia."""
    con = writable_db_copy
    # tre celle indipendenti (product_key diversi, stesso date/measure) per
    # distinguere le tre scritture lungo la catena
    cell_x = sc.CellKey(version_key=DEMAND_BASE_VERSION_KEY, date_key=DEMAND_PRORATION_DATE_KEY, measure_key=1, product_key=9)
    cell_y = sc.CellKey(version_key=DEMAND_BASE_VERSION_KEY, date_key=DEMAND_PRORATION_DATE_KEY, measure_key=1, product_key=11)
    cell_z = sc.CellKey(version_key=DEMAND_BASE_VERSION_KEY, date_key=DEMAND_PRORATION_DATE_KEY, measure_key=1, product_key=14)

    grandparent = sc.branch(con, name="gp", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    sc.set_cell(con, grandparent.scenario_id, cell_x, 111.0, user="tester")

    parent = sc.branch(
        con, name="p", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester",
        parent_scenario_id=grandparent.scenario_id,
    )
    sc.set_cell(con, parent.scenario_id, cell_y, 222.0, user="tester")

    child = sc.branch(
        con, name="c", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester",
        parent_scenario_id=parent.scenario_id,
    )
    sc.set_cell(con, child.scenario_id, cell_z, 333.0, user="tester")

    assert sc.resolve_cell(con, child.scenario_id, cell_x).value == 111.0  # ereditato dal nonno
    assert sc.resolve_cell(con, child.scenario_id, cell_y).value == 222.0  # ereditato dal padre
    assert sc.resolve_cell(con, child.scenario_id, cell_z).value == 333.0  # proprio del figlio

    # il padre, letto da sé, non vede l'edit del figlio
    assert sc.resolve_cell(con, parent.scenario_id, cell_z).source == "base"


def test_child_overrides_parent_value_for_the_same_cell(writable_db_copy):
    con = writable_db_copy
    cell = _cell()
    parent = sc.branch(con, name="p2", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    sc.set_cell(con, parent.scenario_id, cell, 100.0, user="tester")
    child = sc.branch(
        con, name="c2", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester",
        parent_scenario_id=parent.scenario_id,
    )
    sc.set_cell(con, child.scenario_id, cell, 200.0, user="tester")

    assert sc.resolve_cell(con, child.scenario_id, cell).value == 200.0
    assert sc.resolve_cell(con, parent.scenario_id, cell).value == 100.0  # il padre resta al proprio


def test_cache_key_differs_for_two_siblings_on_the_same_base(writable_db_copy):
    con = writable_db_copy
    a = sc.branch(con, name="sib-A", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    b = sc.branch(con, name="sib-B", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")

    key_a = sc.stack_of(con, a.scenario_id).cache_key()
    key_b = sc.stack_of(con, b.scenario_id).cache_key()

    assert key_a != key_b
    # la parte "ingenua" (solo base_version_key) collide per costruzione:
    # è esattamente il caso che cache_key() deve evitare includendo la chain.
    assert key_a[0] == key_b[0] == DEMAND_BASE_VERSION_KEY


def test_cache_key_differs_for_parent_versus_its_own_child(writable_db_copy):
    con = writable_db_copy
    parent = sc.branch(con, name="pp", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    child = sc.branch(
        con, name="cc", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester",
        parent_scenario_id=parent.scenario_id,
    )

    key_parent = sc.stack_of(con, parent.scenario_id).cache_key()
    key_child = sc.stack_of(con, child.scenario_id).cache_key()

    assert key_parent != key_child
    assert key_child[1][:len(key_parent[1])] == key_parent[1]  # il figlio estende la catena del padre
    assert len(key_child[1]) == len(key_parent[1]) + 1


def test_naive_cache_keyed_only_on_base_version_would_leak_a_into_b(writable_db_copy):
    """Costruisce esplicitamente il caso negativo che il coordinatore ha
    chiesto: una cache ingenua indicizzata solo su `base_version_key`
    servirebbe l'aggregato di A a B (stesso base). La vera `cache_key()`
    (che include la chain) non deve permettere la stessa collisione."""
    con = writable_db_copy
    a = sc.branch(con, name="naive-A", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    b = sc.branch(con, name="naive-B", base_version_key=DEMAND_BASE_VERSION_KEY, owner="tester")
    cell = _cell()
    sc.set_cell(con, a.scenario_id, cell, 424242.0, user="tester")

    # Una cache "ingenua" come quella che AC15 esiste per vietare:
    naive_cache: dict[int, float] = {}
    naive_cache[sc.stack_of(con, a.scenario_id).base_version_key] = sc.resolve_cell(
        con, a.scenario_id, cell
    ).value
    # B, cercando nella stessa cache ingenua con la propria base_version_key,
    # troverebbe (erroneamente) il valore di A:
    naive_lookup_for_b = naive_cache.get(sc.stack_of(con, b.scenario_id).base_version_key)
    assert naive_lookup_for_b == 424242.0, "dimostra la collisione che una cache ingenua produrrebbe"

    # La vera cache_key() (AC15) non permette questa collisione:
    real_cache: dict[tuple, float] = {}
    real_cache[sc.stack_of(con, a.scenario_id).cache_key()] = sc.resolve_cell(con, a.scenario_id, cell).value
    real_lookup_for_b = real_cache.get(sc.stack_of(con, b.scenario_id).cache_key())
    assert real_lookup_for_b is None, "cache_key() deve rendere impossibile la stessa collisione"
