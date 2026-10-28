"""`rate_card` copre solo 4 delle 14 `manufacturing_category` nel seed (per
progettazione, non per difetto — vedi `README.md`/`db/build_db.py`). Una
cella `gap_req_conf` la cui `manufacturing_category` non ha una tariffa
applicabile non deve produrre una cella `value_gap` uguale a `0.0`: `0.0`
si leggerebbe come "nessun value gap" (un fatto positivo, il piano è a
target), mentre l'assenza di dato è "non sappiamo" — sono affermazioni
opposte, e confonderle è precisamente il tipo di bug silenzioso che
un'asserzione su `absent is None`/`key not in dict` scopre e un confronto
con `== 0.0` nasconderebbe."""
from __future__ import annotations

from ibp.engine import RequestedProductionEdit

from _engine_support import (
    MANUFACT_KEY_WITH_RATE,
    MANUFACT_KEY_WITHOUT_RATE,
    PLANT_FOR_MANUFACT_WITH_RATE,
    PLANT_FOR_MANUFACT_WITHOUT_RATE,
)


def test_manufacturing_category_without_rate_card_coverage_is_verified_against_the_real_db(con):
    """Non-vacuità: prima di fidarsi di MANUFACT_KEY_WITHOUT_RATE, verifica
    contro il DB reale che la sua manufacturing_category non compaia in
    rate_card, e che quella di MANUFACT_KEY_WITH_RATE invece sì."""
    category_without = con.execute(
        "SELECT manufacturing_category FROM item WHERE item_key = ?", [MANUFACT_KEY_WITHOUT_RATE]
    ).fetchone()[0]
    category_with = con.execute(
        "SELECT manufacturing_category FROM item WHERE item_key = ?", [MANUFACT_KEY_WITH_RATE]
    ).fetchone()[0]
    covered = {
        r[0] for r in con.execute("SELECT DISTINCT manufacturing_category FROM rate_card").fetchall()
    }
    assert category_without not in covered
    assert category_with in covered


def test_gap_cell_without_rate_coverage_has_no_value_gap_entry(engine):
    """Cluster della fixture nota (item 1663, via item 6 'splits') non ha
    copertura rate_card: la cella deve essere assente da value_gap, mai
    presente con 0.0."""
    key = (MANUFACT_KEY_WITHOUT_RATE, PLANT_FOR_MANUFACT_WITHOUT_RATE, 202609)
    result = engine.full_recalculate()

    assert key in result.values["gap_req_conf"], "la cella deve esistere fino a gap_req_conf"
    assert key not in result.values["value_gap"], "assente, non 0.0: nessuna tariffa applicabile"
    assert result.values["value_gap"].get(key) is None
    assert result.values["value_gap"].get(key, "sentinel-not-equal-to-zero") != 0.0


def test_gap_cell_with_rate_coverage_has_a_nonzero_value_gap_entry(engine):
    """Contrasto diretto: la stessa pipeline, per un manufacturing_key CON
    copertura rate_card, produce una cella value_gap reale (e diversa da
    zero, dato che gap_req_conf per questa combinazione non è nullo)."""
    key = (MANUFACT_KEY_WITH_RATE, PLANT_FOR_MANUFACT_WITH_RATE, 202609)
    result = engine.full_recalculate()

    assert key in result.values["gap_req_conf"]
    assert key in result.values["value_gap"]
    assert result.values["value_gap"][key] != 0.0


def test_editing_requested_production_never_materialises_value_gap_for_uncovered_category(engine):
    """Un edit reale a monte (che cambia sicuramente gap_req_conf) non deve
    far comparire una cella value_gap per una categoria priva di tariffa,
    non importa quanto grande sia il nuovo valore."""
    product, division, date = 6, 1, 202609  # product 6 -> splits su 1663 (Cluster 11, non coperto)
    key = (MANUFACT_KEY_WITHOUT_RATE, PLANT_FOR_MANUFACT_WITHOUT_RATE, date)

    result = engine.recalculate([RequestedProductionEdit(product, division, date, 999_999.0)])

    assert result.stats.computed > 0  # l'edit ha davvero mosso qualcosa a valle
    assert key not in result.values["value_gap"]
