"""AC12 — min/max/ratio si ricalcolano sul gruppo, mai per delta. Test
diretti su `ibp/engine/aggregate.py` (`combine`/`combine_ratio`/
`is_delta_safe`): sono le funzioni pure che incarnano la trappola che A5
nomina esplicitamente — un delta-update di un max è sbagliato esattamente
nel momento in cui il valore che cambia (in calo) *era* il max precedente,
perché il nuovo max "sembra" ancora valido finché non lo si confronta col
ricalcolo pieno sull'intero gruppo."""
from __future__ import annotations

import pytest

from ibp.engine.aggregate import combine, combine_ratio, is_delta_safe


def test_lowering_the_current_max_yields_the_second_highest_value():
    """Il caso che rompe un delta-update ingenuo: il gruppo [10, 30, 20] ha
    max=30. Si abbassa l'elemento che *era* il max a 5: un delta-update che
    si limitasse a "il nuovo max è min(vecchio_max, nuovo_valore)" o che
    non ricontrollasse affatto il gruppo darebbe un risultato sbagliato
    (30, o un valore stantio). Il ricalcolo sul gruppo intero deve dare 20,
    il secondo valore più alto — non 5 (il valore appena abbassato) e non 30
    (il vecchio max, ormai non più nel gruppo)."""
    original_group = [10.0, 30.0, 20.0]
    assert combine("max", original_group) == 30.0

    group_after_lowering_the_max = [10.0, 5.0, 20.0]  # il 30 è diventato 5
    new_max = combine("max", group_after_lowering_the_max)

    assert new_max == 20.0
    assert new_max != 5.0  # non il valore appena abbassato
    assert new_max != 30.0  # non il vecchio max, stantio


def test_raising_the_current_min_yields_the_second_lowest_value():
    """Speculare per il minimo: gruppo [10, 30, 20], min=10. Si alza
    l'elemento che *era* il min a 50: il nuovo minimo deve essere 20 (il
    secondo più basso), non 10 (stantio) e non 50 (il valore appena alzato,
    che ora è il massimo del gruppo)."""
    original_group = [10.0, 30.0, 20.0]
    assert combine("min", original_group) == 10.0

    group_after_raising_the_min = [50.0, 30.0, 20.0]  # il 10 è diventato 50
    new_min = combine("min", group_after_raising_the_min)

    assert new_min == 20.0
    assert new_min != 10.0
    assert new_min != 50.0


def test_ratio_recomputed_when_denominator_of_one_pair_changes():
    """`combine_ratio` è somma dei numeratori su somma dei denominatori
    dell'intero gruppo (es. CAPACITY_UTIL): cambiare il denominatore di una
    sola coppia deve rifare il rapporto sull'intero gruppo, non aggiustare
    per delta il rapporto precedente (che sarebbe sbagliato non appena il
    rapporto non è lineare nel denominatore, ed è sempre così)."""
    original_pairs = [(40.0, 100.0), (30.0, 100.0)]  # numeratore, denominatore
    original_ratio = combine_ratio(original_pairs)
    assert original_ratio == pytest.approx(70.0 / 200.0)

    # il denominatore della prima coppia raddoppia (es. capacità del plant aumentata)
    pairs_after_denominator_change = [(40.0, 200.0), (30.0, 100.0)]
    new_ratio = combine_ratio(pairs_after_denominator_change)

    assert new_ratio == pytest.approx(70.0 / 300.0)
    assert new_ratio != pytest.approx(original_ratio)
    # un "delta" ingenuo che aggiustasse solo il denominatore aggregato
    # sommando il delta (100) al denominatore totale precedente (200) darebbe
    # lo stesso risultato per caso *solo* in questo caso lineare-in-somma; il
    # punto del test è che combine_ratio arriva a 300 ricalcolando la somma,
    # non applicando un'operazione diversa da "ricalcola tutto".
    assert sum(d for _, d in pairs_after_denominator_change) == 300.0


def test_combine_ratio_zero_denominator_is_explicit_zero_not_an_exception():
    assert combine_ratio([(10.0, 0.0), (5.0, 0.0)]) == 0.0


def test_combine_empty_group_raises_value_error_not_a_fabricated_zero():
    with pytest.raises(ValueError):
        combine("max", [])
    with pytest.raises(ValueError):
        combine("min", [])
    with pytest.raises(ValueError):
        combine("sum", [])


def test_combine_ratio_empty_group_raises_value_error():
    with pytest.raises(ValueError):
        combine_ratio([])


def test_combine_unknown_agg_method_raises_value_error():
    with pytest.raises(ValueError):
        combine("median", [1.0, 2.0])


def test_is_delta_safe_declares_only_sum_and_count():
    """A5: solo sum/count sono delta-safe *in linea di principio* — min/max/
    avg/ratio richiedono sempre il gruppo intero."""
    assert is_delta_safe("sum") is True
    assert is_delta_safe("count") is True
    assert is_delta_safe("min") is False
    assert is_delta_safe("max") is False
    assert is_delta_safe("avg") is False
    assert is_delta_safe("ratio") is False


def test_combine_sum_and_avg_basic_sanity():
    assert combine("sum", [1.0, 2.0, 3.0]) == 6.0
    assert combine("avg", [1.0, 2.0, 3.0]) == pytest.approx(2.0)
    assert combine("count", [1.0, 2.0, 3.0]) == 3.0
