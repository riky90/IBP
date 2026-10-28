"""AC10 — il test cardine: `recalculate()` (propagazione dirty sul
sottografo) deve produrre lo stesso risultato di `full_recalculate()`
sullo stesso stato sorgente, su sequenze di edit.

L'affermazione dell'implementatore ("holds by construction, both call the
same compute function") è vera per la *formula* usata per ogni cella, ma
non dice nulla sul fatto che il **dirty set sia completo**: se
`_downstream()` dimenticasse un arco, `recalculate()` lascerebbe una cella
a valle non ricalcolata mentre `full_recalculate()` la calcolerebbe
comunque — è esattamente il tipo di bug che un confronto di formula non
scopre e un confronto di *risultato* sì. Questo file confronta i risultati,
non le formule.

Ogni test usa `engine` (clone economico di un `RecalcEngine` già caldo,
vedi conftest.py) e verifica via
`_engine_support.assert_matches_full_recalculate` — confronto **esatto**
(`==`), non con tolleranza. Round critic T3: prima serviva `math.isclose`
perché `_compute_dmd_cell` sommava iterando su `set` non ordinati (rumore
nell'ultimo bit fra `recalculate()` e `full_recalculate()`, 8 batch su 120
nelle prove originali); il motore ora somma su `sorted(...)`, un ordine
totale esplicito, e il confronto esatto passa su tutti i casi qui sotto —
incluse le 8 sequenze casuali da 15 batch. Se un caso futuro tornasse a
richiedere tolleranza, sarebbe un fatto sul motore da riportare (vedi
`_engine_support.values_close`, ancora configurabile), non da nascondere
allentando questo file."""
from __future__ import annotations

import random

import pytest

from ibp.engine import ConfirmedProductionEdit, RequestedProductionEdit

from _engine_support import (
    AGGREGATING_PRODUCTS_INTO_1662,
    CONFIRMED_PRODUCTION_KEY_POOL,
    REQUESTED_PRODUCTION_KEY_POOL,
    assert_matches_full_recalculate,
)


def test_single_requested_production_edit_matches_full_recalculate(engine):
    product, division, date = REQUESTED_PRODUCTION_KEY_POOL[0]
    result = engine.recalculate([RequestedProductionEdit(product, division, date, 12345.0)])
    assert_matches_full_recalculate(engine, result)


def test_single_confirmed_production_edit_matches_full_recalculate(engine):
    manufact, plant, date = CONFIRMED_PRODUCTION_KEY_POOL[0]
    result = engine.recalculate([ConfirmedProductionEdit(manufact, plant, date, 777.0)])
    assert_matches_full_recalculate(engine, result)


def test_repeated_edits_to_the_same_cell_in_one_batch_uses_the_last_value(engine):
    """Più edit sulla stessa cella nello stesso batch: l'ultimo vince (`new_value`
    è 'set', non un delta — vedi RequestedProductionEdit). Un motore che
    applicasse i delta in ordine sbagliato o sommasse gli edit invece di
    sostituire divergerebbe da full_recalculate()."""
    product, division, date = REQUESTED_PRODUCTION_KEY_POOL[1]
    result = engine.recalculate([
        RequestedProductionEdit(product, division, date, 100.0),
        RequestedProductionEdit(product, division, date, 500.0),
        RequestedProductionEdit(product, division, date, 42.0),
    ])
    assert result.values["requested_production"][(product, division, date)] == 42.0
    assert_matches_full_recalculate(engine, result)


def test_edits_that_cancel_out_within_one_batch(engine):
    """Due edit sulla stessa cella nello stesso batch che tornano al valore
    di partenza: il risultato finale deve comunque combaciare con
    full_recalculate() (che vede solo il valore finale, non la storia del
    batch)."""
    product, division, date = REQUESTED_PRODUCTION_KEY_POOL[2]
    baseline = engine.full_recalculate()  # stato pubblico corrente, non un attributo privato
    original = baseline.values["requested_production"].get((product, division, date), 0.0)
    result = engine.recalculate([
        RequestedProductionEdit(product, division, date, original + 1000.0),
        RequestedProductionEdit(product, division, date, original),
    ])
    assert result.values["requested_production"][(product, division, date)] == original
    assert_matches_full_recalculate(engine, result)


def test_batch_with_edits_at_different_dag_depths(engine):
    """Un `RequestedProductionEdit` (radice, height 0, deve attraversare
    derived_manufacturing_demand -> slots_requested -> gap_req_conf ->
    value_gap) e un `ConfirmedProductionEdit` (radice esogena che entra
    direttamente in gap_req_conf, height diverso) nello stesso batch: il
    min-heap deve processare entrambi i sottografi correttamente senza che
    l'uno interferisca sull'ordine dell'altro."""
    product, division, date = REQUESTED_PRODUCTION_KEY_POOL[3]
    manufact, plant, cdate = CONFIRMED_PRODUCTION_KEY_POOL[0]
    result = engine.recalculate([
        RequestedProductionEdit(product, division, date, 321.0),
        ConfirmedProductionEdit(manufact, plant, cdate, 88.0),
    ])
    assert_matches_full_recalculate(engine, result)


def test_diamond_two_products_aggregating_into_the_same_manufacturing_key(engine):
    """AC10/A5 punto 2 — il glitch del diamante: i planning model 9 e 11
    'aggregates' sullo stesso manufacturing_key 1662 (item_link, F7).
    Editarli entrambi, per lo stesso date_key, nello stesso batch, deve
    produrre la stessa derived_manufacturing_demand[1662, date] che
    full_recalculate() calcolerebbe sommando entrambi i contributi — non il
    doppio (se la cella venisse ricalcolata due volte accumulando) né la
    metà (se una delle due scritture venisse persa)."""
    product_a, product_b = AGGREGATING_PRODUCTS_INTO_1662
    date = 202609
    result = engine.recalculate([
        RequestedProductionEdit(product_a, 9, date, 200.0),
        RequestedProductionEdit(product_b, 2, date, 300.0),
    ])
    assert_matches_full_recalculate(engine, result)
    # non-vacuo: la cella del diamante deve davvero comparire nel risultato
    assert (1662, date) in result.values["derived_manufacturing_demand"]


def test_batch_touching_both_exogenous_roots_on_overlapping_downstream_cells(engine):
    """Un `RequestedProductionEdit` che (via item_link/eligibility) produce
    `slots_requested`/`gap_req_conf` per (1662, 37, 202609), **e** un
    `ConfirmedProductionEdit` diretto sulla stessa chiave (1662, 37, 202609)
    nello stesso batch: due punti di ingresso diversi che convergono sulla
    stessa cella gap_req_conf nello stesso giro di propagazione — il
    dedup su `pending` deve gestirlo senza doppio conteggio né perdita."""
    product_a, product_b = AGGREGATING_PRODUCTS_INTO_1662
    date = 202609
    result = engine.recalculate([
        RequestedProductionEdit(product_a, 9, date, 150.0),
        ConfirmedProductionEdit(1662, 37, date, 999.0),
    ])
    assert_matches_full_recalculate(engine, result)
    assert result.values["gap_req_conf"][(1662, 37, date)] == pytest.approx(
        result.values["slots_requested"].get((1662, 37, date), 0.0) - 999.0
    )


# ---------------------------------------------------------------------------
# Property-style: sequenze casuali di batch di edit, confrontate ad ogni
# passo con full_recalculate() sullo stesso stato. Il generatore copre
# deliberatamente gli stessi pattern dei test nominati sopra, ma in
# combinazioni non previste in anticipo.
# ---------------------------------------------------------------------------


def _random_rp_edit(rng: random.Random) -> RequestedProductionEdit:
    product, division, date = rng.choice(REQUESTED_PRODUCTION_KEY_POOL)
    return RequestedProductionEdit(product, division, date, rng.uniform(-500.0, 5000.0))


def _random_confirmed_edit(rng: random.Random) -> ConfirmedProductionEdit:
    manufact, plant, date = rng.choice(CONFIRMED_PRODUCTION_KEY_POOL)
    return ConfirmedProductionEdit(manufact, plant, date, rng.uniform(-500.0, 5000.0))


def _random_batch(rng: random.Random) -> list:
    """Un batch fra 1 e 5 edit, che mischia i due tipi con probabilità
    variabile — incluse ripetizioni della stessa chiave nello stesso batch
    (repeated edits) per costruzione, dato che il pool di chiavi è piccolo
    rispetto alla dimensione massima del batch."""
    size = rng.randint(1, 5)
    batch = []
    for _ in range(size):
        if rng.random() < 0.7:
            batch.append(_random_rp_edit(rng))
        else:
            batch.append(_random_confirmed_edit(rng))
    return batch


@pytest.mark.parametrize("seed", range(8))
def test_random_edit_sequences_match_full_recalculate(engine, seed):
    """8 sequenze indipendenti (seed diversi) di 15 batch casuali ciascuna
    (120 batch totali, ~350-450 edit singoli): ogni batch è confrontato con
    full_recalculate() sullo stato risultante prima di procedere al
    successivo, così un mismatch è isolato al batch esatto che lo ha
    causato invece di annegare in una sequenza lunga."""
    rng = random.Random(seed)
    for batch_no in range(15):
        batch = _random_batch(rng)
        result = engine.recalculate(batch)
        full = engine.full_recalculate()
        from _engine_support import values_close, diff_values

        assert values_close(result.values, full.values), (
            f"seed={seed} batch#{batch_no}={batch!r}: "
            f"diverge da full_recalculate(): {diff_values(result.values, full.values)[:10]}"
        )
