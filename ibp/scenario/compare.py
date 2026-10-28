"""`compare(ref_a, ref_b)`: accetta indifferentemente `version_key` (int) e
`scenario_id` (str) su entrambi i lati — versione contro versione, scenario
contro scenario, o l'uno contro l'altro, con lo stesso percorso di codice
(`overlay.materialize_ref` fa già il dispatch per tipo)."""
from __future__ import annotations

from .models import CompareRow
from .overlay import materialize_ref


def compare(con, ref_a: int | str, ref_b: int | str) -> list[CompareRow]:
    """Delta per slice fra `ref_a` e `ref_b`. Una slice presente in un solo
    lato vale `0.0` sull'altro (stessa semantica additiva del cubo: nessuna
    riga per quella cella significa nessun contributo, non "sconosciuto").
    Ordinata per leggibilità (`date_key`, `measure_key`, `product_key`,
    `plant_key`), non è un contratto di ordinamento stabile oltre quello."""
    slices_a = materialize_ref(con, ref_a)
    slices_b = materialize_ref(con, ref_b)
    keys = set(slices_a) | set(slices_b)

    rows = []
    for product_key, plant_key, date_key, measure_key in keys:
        value_a = slices_a.get((product_key, plant_key, date_key, measure_key), 0.0)
        value_b = slices_b.get((product_key, plant_key, date_key, measure_key), 0.0)
        rows.append(
            CompareRow(
                product_key=product_key, plant_key=plant_key, date_key=date_key,
                measure_key=measure_key, value_a=value_a, value_b=value_b,
                delta=value_b - value_a,
            )
        )
    rows.sort(
        key=lambda r: (
            r.date_key, r.measure_key,
            r.product_key if r.product_key is not None else -1,
            r.plant_key if r.plant_key is not None else -1,
        )
    )
    return rows
