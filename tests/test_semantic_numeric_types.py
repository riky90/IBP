"""Round 2 (critic FAIL su round 1, ora corretto in `ibp/semantic/dimensions.py`):
DuckDB ritorna `decimal.Decimal` per le colonne `DECIMAL(6,3)`
(`DPLANT.slot_granularity_factor`, `item.slot_equivalence_factor`,
`item.average_assembly_hours`). Se il costruttore di riga non le converte,
`2.5 * registry.item_factors(...).slot_equivalence_factor` solleva
`TypeError` non appena un chiamante (T3, `slots_requested`) le moltiplica
contro una misura `DOUBLE` del cubo — esattamente il caso misurato dal
critic. Il contratto di tipo ("mai `Decimal` nel semantic layer") è
verificato qui come test, non per ispezione del codice, e su un campione di
righe (una sola riga potrebbe essere integrale per caso e non farlo emergere)."""
from __future__ import annotations

import decimal

CUBE_MEASURE_SAMPLE = 2.5  # un fattore DOUBLE plausibile, non un intero


def test_plant_capacity_slot_granularity_factor_is_float_across_all_plants(registry):
    plants = registry.plants()
    assert len(plants) >= 10  # campione ampio, non una singola riga fortunata
    for plant in plants:
        assert isinstance(plant.slot_granularity_factor, float), (
            f"{plant.plant_code}: slot_granularity_factor è {type(plant.slot_granularity_factor)}, atteso float"
        )
        assert not isinstance(plant.slot_granularity_factor, decimal.Decimal)


def test_plant_capacity_slot_granularity_factor_multiplies_against_a_double(registry):
    for plant in registry.plants():
        product = CUBE_MEASURE_SAMPLE * plant.slot_granularity_factor  # non deve sollevare TypeError
        assert isinstance(product, float)


def test_item_factors_slot_equivalence_and_hours_are_float_across_sample(registry, con):
    item_keys = [
        r[0] for r in con.execute(
            "SELECT item_key FROM item WHERE role = 'manufacturing_key' ORDER BY item_key LIMIT 25"
        ).fetchall()
    ]
    assert len(item_keys) == 25  # campione ampio
    for item_key in item_keys:
        factors = registry.item_factors(item_key)
        assert isinstance(factors.slot_equivalence_factor, float), (
            f"item {item_key}: slot_equivalence_factor è {type(factors.slot_equivalence_factor)}"
        )
        assert isinstance(factors.average_assembly_hours, float), (
            f"item {item_key}: average_assembly_hours è {type(factors.average_assembly_hours)}"
        )
        assert not isinstance(factors.slot_equivalence_factor, decimal.Decimal)
        assert not isinstance(factors.average_assembly_hours, decimal.Decimal)


def test_item_factors_slot_equivalence_factor_multiplies_against_a_double(registry, con):
    """Il caso esatto che ha rotto in revisione: T3's `slots_requested` è
    `derived_manufacturing_demand * slot_equivalence_factor`, e
    `derived_manufacturing_demand` è una misura `DOUBLE` del cubo."""
    item_keys = [
        r[0] for r in con.execute(
            "SELECT item_key FROM item WHERE role = 'manufacturing_key' ORDER BY item_key LIMIT 25"
        ).fetchall()
    ]
    for item_key in item_keys:
        factors = registry.item_factors(item_key)
        slots_requested = CUBE_MEASURE_SAMPLE * factors.slot_equivalence_factor
        assert isinstance(slots_requested, float)


def test_list_item_factors_never_returns_decimal(registry):
    for factors in registry.list_item_factors():
        assert isinstance(factors.slot_equivalence_factor, float)
        assert isinstance(factors.average_assembly_hours, float)
