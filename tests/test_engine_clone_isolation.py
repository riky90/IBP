"""`_engine_support.clone_engine()` è infrastruttura di test, non codice di
prodotto — ma un difetto lì produce falsi negativi/positivi indistinguibili
da un vero bug di `ibp/engine/`, ed è esattamente il tipo di cosa che un
critic esterno deve poter probare. Segnalato dal critic T3: `clone_engine`
condivideva `_rp_targets`/`_dmd_reverse` fra cloni; un edit su una
combinazione `(product_key, date_key)` mai vista prima dal costruttore li
estende in place (`_ensure_rp_targets`), e quell'estensione era visibile
anche dai cloni "gemelli" che non avevano mai visto quell'edit — uno stato
di un test che trapela in un altro, silenziosamente, mesi dopo.

Questo file prova che il fix (copia un livello in profondità per ogni
clone) chiude davvero la falla, con la stessa identica combinazione usata
per misurarla (product 6, date_key 202801 — fuori dal perimetro caricato
da `DEMAND_VERSION_KEY=369`)."""
from __future__ import annotations

from ibp.engine import RequestedProductionEdit

from _engine_support import clone_engine

_UNSEEN_PRODUCT_DATE = (6, 202801)  # non presente in TSOP_DEMAND per DEMAND_VERSION_KEY (369)


def test_unseen_product_date_is_not_yet_resolved_on_the_warm_engine(warm_engine):
    """Non-vacuità: la combinazione usata da questo test deve davvero non
    essere già nella cache del motore riscaldato, altrimenti l'edit sotto
    non eserciterebbe il percorso di estensione in place che ha causato la
    falla."""
    assert _UNSEEN_PRODUCT_DATE not in warm_engine._rp_targets


def test_editing_a_never_seen_product_date_on_one_clone_does_not_leak_to_a_sibling_clone(warm_engine):
    clone_a = clone_engine(warm_engine)
    clone_b = clone_engine(warm_engine)

    product, date = _UNSEEN_PRODUCT_DATE
    clone_a.recalculate([RequestedProductionEdit(product, 1, date, 999.0)])

    assert _UNSEEN_PRODUCT_DATE in clone_a._rp_targets, (
        "non-vacuità: l'edit deve davvero aver popolato la cache di clone_a"
    )
    assert _UNSEEN_PRODUCT_DATE not in clone_b._rp_targets, (
        "clone_engine() deve isolare _rp_targets: l'edit su clone_a non deve comparire in clone_b"
    )
    assert not any(key[1] == date for key in clone_b._dmd_reverse), (
        "clone_engine() deve isolare _dmd_reverse: nessuna entry per la nuova data deve "
        "comparire in clone_b, che non ha mai visto quell'edit"
    )


def test_editing_a_never_seen_product_date_on_one_clone_does_not_leak_back_to_the_warm_engine(warm_engine):
    """Lo stesso, verso l'engine riscaldato condiviso da tutta la sessione:
    se la falla ci fosse ancora, ogni test successivo della sessione
    erediterebbe silenziosamente questo edit."""
    clone_a = clone_engine(warm_engine)
    product, date = _UNSEEN_PRODUCT_DATE
    clone_a.recalculate([RequestedProductionEdit(product, 1, date, 999.0)])

    assert _UNSEEN_PRODUCT_DATE not in warm_engine._rp_targets
    assert not any(key[1] == date for key in warm_engine._dmd_reverse)
