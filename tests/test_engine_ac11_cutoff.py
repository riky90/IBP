"""AC11 — l'early cutoff è misurato, non solo promesso: `CutoffStats` deve
muoversi nella direzione giusta a seconda che l'edit sia un no-op (stesso
valore) o un cambio reale, e l'invariante `visited == computed + cutoff +
absent` deve reggere in ogni chiamata (`recalculate()` e
`full_recalculate()`), non solo asserendo che i quattro contatori esistano.

Round critic T3: `CutoffStats` aveva solo tre termini
(`visited/computed/cutoff`) e `full_recalculate()` faceva confluire in
`cutoff` sia le celle davvero ricalcolate-e-invariate sia le celle
`value_gap` senza copertura `rate_card` (sparsità di master data, mai
esistite, non "ricalcolate e trovate uguali"). Un pannello che leggesse
`cutoff` come "risparmio da propagazione incrementale" avrebbe contato
sparsità come se fosse ottimizzazione. Ora un quarto contatore, `absent`,
tiene le due cose separate: `cutoff` è sempre e solo "c'era già un valore,
il ricalcolo dà lo stesso valore"; `absent` è sempre e solo "non c'era nulla
prima e non c'è nulla dopo"."""
from __future__ import annotations

from ibp.engine import ConfirmedProductionEdit, RequestedProductionEdit

from _engine_support import CONFIRMED_PRODUCTION_KEY_POOL, REQUESTED_PRODUCTION_KEY_POOL


def _assert_cutoff_invariant(stats) -> None:
    assert stats.visited == stats.computed + stats.cutoff + stats.absent, (
        f"invariante AC11 violata: visited={stats.visited} != "
        f"computed={stats.computed} + cutoff={stats.cutoff} + absent={stats.absent}"
    )


def test_noop_requested_production_edit_computes_nothing_downstream(engine):
    """Un edit con lo stesso valore già presente non deve sporcare nessuna
    cella a valle: computed == 0 per l'intera chiamata (la sola cella
    esaminata — requested_production stessa non passa dal contatore, solo
    i nodi calcolati a valle — è quella derived_manufacturing_demand, che
    trova nessun cambio e si ferma lì)."""
    product, division, date = REQUESTED_PRODUCTION_KEY_POOL[4]
    baseline = engine.full_recalculate()
    current_value = baseline.values["requested_production"][(product, division, date)]

    result = engine.recalculate([RequestedProductionEdit(product, division, date, current_value)])

    assert result.stats.computed == 0, f"no-op ha comunque calcolato {result.stats.computed} celle"
    assert result.stats.visited > 0, "un edit deve comunque visitare almeno la prima cella a valle"
    assert result.stats.absent == 0, (
        "il no-op deve ricadere su cutoff (c'era già un valore, invariato), non su absent "
        "(che significherebbe che la cella non aveva mai avuto un valore)"
    )
    assert result.stats.cutoff == result.stats.visited
    _assert_cutoff_invariant(result.stats)


def test_noop_confirmed_production_edit_computes_nothing(engine):
    manufact, plant, date = CONFIRMED_PRODUCTION_KEY_POOL[1]
    baseline = engine.full_recalculate()
    current_value = baseline.values["confirmed_production"].get((manufact, plant, date), 0.0)

    result = engine.recalculate([ConfirmedProductionEdit(manufact, plant, date, current_value)])

    assert result.stats.computed == 0
    assert result.stats.absent == 0
    _assert_cutoff_invariant(result.stats)


def test_real_requested_production_edit_computes_downstream_cells(engine):
    """Un edit che cambia davvero il valore deve produrre computed > 0: il
    contrario del no-op sopra, sullo stesso tipo di edit."""
    product, division, date = REQUESTED_PRODUCTION_KEY_POOL[5]
    baseline = engine.full_recalculate()
    current_value = baseline.values["requested_production"][(product, division, date)]
    new_value = current_value + 10_000.0  # abbastanza grande da non confondersi col rumore in virgola mobile

    result = engine.recalculate([RequestedProductionEdit(product, division, date, new_value)])

    assert result.stats.computed > 0, "un edit reale deve calcolare almeno una cella a valle"
    assert result.stats.visited >= result.stats.computed
    _assert_cutoff_invariant(result.stats)


def test_real_confirmed_production_edit_computes_gap_and_value_gap(engine):
    manufact, plant, date = CONFIRMED_PRODUCTION_KEY_POOL[2]
    baseline = engine.full_recalculate()
    current_value = baseline.values["confirmed_production"].get((manufact, plant, date), 0.0)

    result = engine.recalculate([ConfirmedProductionEdit(manufact, plant, date, current_value + 10_000.0)])

    assert result.stats.computed > 0
    _assert_cutoff_invariant(result.stats)


def test_full_recalculate_absent_counts_cells_without_rate_coverage(engine):
    """`full_recalculate()` non confronta mai col valore precedente (azzera
    `self._values` a ogni chiamata, vedi `ibp/engine/engine.py`): il suo
    `cutoff` è **sempre** 0 — non c'è propagazione da tagliare in un
    ricalcolo che parte da zero. Una cella `gap_req_conf` senza `rate_card`
    applicabile non produce mai un valore `value_gap`
    (`_compute_value_gap_cell` ritorna `None`): non è "ricalcolata e trovata
    invariata" (non c'era nulla da confrontare), è "non c'è mai stato nulla
    da calcolare" — `absent`, non `cutoff` (round critic T3, vedi
    `cells.py::CutoffStats`).

    Con una `rate_card` sparsa per progettazione (4/14 categorie, vedi
    test_engine_sparse_rate_card.py) questo non è un caso limite: il
    conteggio di `absent` deve combaciare esattamente con il numero di
    celle `gap_req_conf` prive di una `value_gap` corrispondente — derivato
    dal DB qui, non un numero fisso nel test (il seed potrebbe cambiare la
    copertura di rate_card in una revisione futura)."""
    result = engine.full_recalculate()

    gap_keys_without_value_gap = set(result.values["gap_req_conf"]) - set(result.values["value_gap"])
    assert gap_keys_without_value_gap, (
        "fixture non più valida: nessuna cella gap_req_conf priva di rate_card su questo DB, "
        "il test non starebbe verificando nulla"
    )
    assert result.stats.cutoff == 0, (
        "full_recalculate() non ha stato precedente con cui confrontare: cutoff deve restare 0"
    )
    assert result.stats.absent == len(gap_keys_without_value_gap), (
        f"absent={result.stats.absent} dovrebbe combaciare esattamente con le "
        f"{len(gap_keys_without_value_gap)} celle gap_req_conf senza rate_card"
    )
    _assert_cutoff_invariant(result.stats)


def test_recalculate_distinguishes_cutoff_from_absent_on_the_same_target(engine):
    """Il caso che il quarto contatore esiste per distinguere: la stessa
    cella (product 6, senza copertura rate_card via 1663/1665) sottoposta a
    due chiamate consecutive di `recalculate()`.

    1. Un edit reale (valore diverso) fa propagare fino a `gap_req_conf`
       (che ottiene un valore vero) e tenta `value_gap` (che resta
       `None`, mai avendo avuto un valore) — quel tentativo conta come
       `absent`, non `cutoff`: non c'era nulla da "non cambiare".
    2. La stessa identica chiamata ripetuta è ora un vero no-op su
       `gap_req_conf`, che stavolta **aveva già** un valore reale
       (impostato al passo 1): deve ricadere su `cutoff`, non su `absent` —
       ed è per questo che serve un contatore a parte da quello sopra."""
    product, division, date = 6, 1, 202609  # -> 1663/1665, nessuna copertura rate_card
    baseline = engine.full_recalculate()
    current_value = baseline.values["requested_production"][(product, division, date)]
    new_value = current_value + 5_000.0

    first = engine.recalculate([RequestedProductionEdit(product, division, date, new_value)])
    assert first.stats.computed > 0
    assert first.stats.absent > 0, (
        "il primo edit reale deve comunque produrre almeno un tentativo value_gap "
        "assente (nessuna copertura rate_card per 1663/1665)"
    )
    assert (1663, 50, date) not in first.values["value_gap"]

    second = engine.recalculate([RequestedProductionEdit(product, division, date, new_value)])
    assert second.stats.computed == 0, "la ripetizione identica non deve ricalcolare nulla di nuovo"
    assert second.stats.cutoff > 0, "gap_req_conf aveva già un valore reale: deve contare come cutoff"
    assert second.stats.absent == 0, (
        "nessuna cella priva di valore viene rivisitata qui: la propagazione si ferma "
        "a gap_req_conf (cutoff) prima di raggiungere di nuovo value_gap"
    )
    _assert_cutoff_invariant(first.stats)
    _assert_cutoff_invariant(second.stats)


def test_cutoff_invariant_holds_even_when_value_gap_never_materialises(engine):
    """Caso più fine del no-op semplice: product 6 alimenta (via 'splits',
    item_link) il manufacturing_key 1663, che non ha copertura `rate_card`
    (round 3 dell'implementatore: sparsità dichiarata). Un edit reale a monte
    fa comunque propagare/calcolare derived_manufacturing_demand ->
    slots_requested -> gap_req_conf, ma value_gap resta assente per
    l'intera catena — l'invariante visited == computed + cutoff deve
    reggere comunque, senza che la cella "mai creata" la rompa."""
    product, division, date = 6, 1, 202609  # product 6 -> splits su 1663/1665, nessuna copertura rate_card
    baseline = engine.full_recalculate()
    current_value = baseline.values["requested_production"][(product, division, date)]

    result = engine.recalculate([RequestedProductionEdit(product, division, date, current_value + 5_000.0)])

    assert (1663, 50, date) not in result.values["value_gap"], (
        "senza rate_card la cella value_gap deve restare assente anche dopo un edit reale a monte"
    )
    assert result.stats.computed > 0  # derived_manufacturing_demand/slots_requested/gap_req_conf sono cambiati
    _assert_cutoff_invariant(result.stats)
