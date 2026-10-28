"""Il DAG delle misure calcolate è **dichiarato**, non eseguito (T2 done_when,
D4, notes: "il DAG è dichiarato in T2 ed eseguito in T3 — non anticipare il
calcolo"). Questi test coprono la struttura del grafo
(`nodes/edges/topological_order/dirty_set`) e verificano che nessuna
funzione del layer semantico legga o calcoli un valore di misura.

Round critic T3: `confirmed_production` (letto da TSOP_OPS, il lato
Confirmed di `gap_req_conf`) mancava da `MEASURE_DAG` pur essendo già
eseguito come root dal motore — un buco nel contratto dichiarato che T4/T7/
T10 avrebbero dovuto scoprire leggendo il DAG, non il codice del motore.
Ora `confirmed_production` è un secondo nodo sorgente (`depends_on=()`) e
`gap_req_conf.depends_on == ("slots_requested", "confirmed_production")`:
il DAG non è più una catena lineare, ma un albero con due radici che
convergono su `gap_req_conf`.
"""
from __future__ import annotations

import inspect

import graphlib
import pytest

from ibp.semantic import measures

# La catena lineare originale (requested_production -> ... -> value_gap)
# resta un sottoinsieme valido del DAG — usata dove serve solo quella parte.
LINEAR_CHAIN = (
    "requested_production",
    "derived_manufacturing_demand",
    "slots_requested",
    "gap_req_conf",
    "value_gap",
)
# Tutti i nodi dichiarati, inclusa la seconda radice.
ALL_NODES = LINEAR_CHAIN + ("confirmed_production",)


def test_nodes_declares_exactly_the_six_nodes_including_confirmed_production():
    nodes = measures.nodes()
    assert set(nodes) == set(ALL_NODES)


def test_confirmed_production_is_a_second_source_node():
    nodes = measures.nodes()
    assert nodes["confirmed_production"].depends_on == ()


def test_gap_req_conf_depends_on_both_slots_requested_and_confirmed_production():
    nodes = measures.nodes()
    assert set(nodes["gap_req_conf"].depends_on) == {"slots_requested", "confirmed_production"}


def test_nodes_returns_a_defensive_copy():
    nodes = measures.nodes()
    nodes["bogus"] = "mutated"
    assert "bogus" not in measures.nodes()


def test_edges_point_from_dependency_to_dependent():
    edges = set(measures.edges())
    for upstream, downstream in zip(LINEAR_CHAIN, LINEAR_CHAIN[1:]):
        assert (upstream, downstream) in edges
    assert ("confirmed_production", "gap_req_conf") in edges
    # 4 archi della catena lineare + 1 di confirmed_production -> gap_req_conf
    assert len(edges) == len(LINEAR_CHAIN) - 1 + 1


def test_topological_order_respects_all_dependencies():
    """Non più un ordine totale unico (`requested_production` e
    `confirmed_production` sono entrambe radici, senza un ordine relativo
    dichiarato): si verifica solo che ogni dipendenza preceda il proprio
    dipendente, non un ordine esatto."""
    order = measures.topological_order()
    assert set(order) == set(ALL_NODES)
    position = {name: i for i, name in enumerate(order)}
    for name, node in measures.nodes().items():
        for dep in node.depends_on:
            assert position[dep] < position[name], (
                f"{dep} deve precedere {name} nell'ordine topologico"
            )


def test_dirty_set_from_requested_production_reaches_the_linear_chain_only():
    """`requested_production` non raggiunge `confirmed_production` (radice
    indipendente): il dirty set resta esattamente la catena lineare."""
    assert measures.dirty_set("requested_production") == set(LINEAR_CHAIN)


def test_dirty_set_from_confirmed_production_reaches_gap_and_value_gap():
    """Il caso che il critic ha reso possibile verificare: prima
    `dirty_set("confirmed_production")` sollevava `KeyError` (non era nel
    DAG); ora raggiunge esattamente sé stessa, gap_req_conf e value_gap —
    non slots_requested/derived_manufacturing_demand, che dipendono solo da
    requested_production."""
    assert measures.dirty_set("confirmed_production") == {
        "confirmed_production", "gap_req_conf", "value_gap",
    }


def test_dirty_set_from_leaf_is_only_itself():
    assert measures.dirty_set("value_gap") == {"value_gap"}


def test_dirty_set_from_middle_measure_is_exactly_reachable_downstream():
    assert measures.dirty_set("slots_requested") == {
        "slots_requested", "gap_req_conf", "value_gap",
    }


def test_dirty_set_unknown_measure_raises_key_error():
    with pytest.raises(KeyError):
        measures.dirty_set("not_a_declared_measure")


def test_declared_dag_has_no_cycle():
    # topological_order() già lo garantisce (usa graphlib.TopologicalSorter
    # internamente e solleverebbe CycleError), ma lo ridichiariamo qui in modo
    # esplicito e indipendente dall'implementazione interna.
    ts = graphlib.TopologicalSorter(
        {name: node.depends_on for name, node in measures.nodes().items()}
    )
    ts.prepare()  # solleva graphlib.CycleError se ciclico


# ---------------------------------------------------------------------------
# "Qui non si calcola nulla": le funzioni del DAG non ricevono una
# connessione DB e non possono quindi leggere TSOP_DEMAND/TSOP_OPS o
# produrre un valore — la separazione dichiarazione/esecuzione è strutturale,
# non solo documentale.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fn", [measures.nodes, measures.edges, measures.topological_order, measures.dirty_set]
)
def test_dag_functions_take_no_db_connection(fn):
    sig = inspect.signature(fn)
    assert "con" not in sig.parameters, (
        f"{fn.__name__} non dovrebbe accettare una connessione DB in T2: "
        "il DAG è dato, l'esecuzione è T3"
    )


def test_measure_dag_module_never_references_fact_tables():
    """Le tabelle di fatto (TSOP_DEMAND/TSOP_OPS) compaiono nel catalogo
    misure (list_measures, sezione 1 del modulo) ma non devono comparire
    nella sezione 2 (il DAG dichiarato) come nome di tabella interrogato:
    verificato leggendo il sorgente della sola sezione DAG."""
    import pathlib

    source = pathlib.Path(measures.__file__).read_text(encoding="utf-8")
    dag_section_start = source.index("MEASURE_DAG: dict")
    dag_section = source[dag_section_start:]
    assert ".execute(" not in dag_section
