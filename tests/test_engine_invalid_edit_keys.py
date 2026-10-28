"""Il difetto misurato dal critic ("no test exercises an invalid
manufact_key, which is why 176 pass"): `recalculate()` validava
`RequestedProductionEdit` risolvendo `product_key` **prima** di scrivere
stato, ma assumeva — scorrettamente — che `ConfirmedProductionEdit` non
avesse nulla da risolvere. `manufact_key` non veniva verificato da nessuna
parte finché la propagazione non arrivava a `value_gap` via `_item_factor`,
**dopo** che `_confirmed_production` era già stato scritto: un
`ConfirmedProductionEdit` con `manufact_key` inesistente sollevava
`KeyError` a batch già applicato, lasciando una chiave avvelenata nello
stato. `recalculate([])` continuava a tornare senza sollevare (l'heap resta
vuoto, nessuna propagazione), quindi la corruzione restava **latente**
finché qualcuno non chiamava `full_recalculate()` — che da quel momento in
poi sollevava la stessa eccezione **per sempre**.

Il difetto reale non era "un manufact_key invalido rompe il motore": era
"la validazione era per tipo, e un tipo è stato dimenticato". I test qui
sono quindi generali per costruzione, non pinnati al solo
`ConfirmedProductionEdit`: iterano su un registro di factory
valida/non-risolvibile per **ogni** tipo dichiarato in `CellEdit`
(`ibp/engine/cells.py`), e un canarino fallisce esplicitamente se un nuovo
tipo di edit viene aggiunto a `CellEdit` senza una entry corrispondente qui
— così la prossima volta che "un tipo viene dimenticato" è un test rosso,
non un silenzio che arriva a 176 passati lo stesso.
"""
from __future__ import annotations

import typing

import pytest

from ibp.engine import CellEdit, ConfirmedProductionEdit, RequestedProductionEdit

from _engine_support import CONFIRMED_PRODUCTION_KEY_POOL, REQUESTED_PRODUCTION_KEY_POOL

UNRESOLVABLE_KEY = 999_999_999  # non esiste in `item` — stesso valore usato dal critic per riprodurlo
ARBITRARY_DATE_KEY = 202609


def _valid_requested_production_edit() -> RequestedProductionEdit:
    product, division, date = REQUESTED_PRODUCTION_KEY_POOL[0]
    return RequestedProductionEdit(product, division, date, 5.0)


def _invalid_requested_production_edit() -> RequestedProductionEdit:
    return RequestedProductionEdit(UNRESOLVABLE_KEY, 1, ARBITRARY_DATE_KEY, 5.0)


def _valid_confirmed_production_edit() -> ConfirmedProductionEdit:
    manufact, plant, date = CONFIRMED_PRODUCTION_KEY_POOL[0]
    return ConfirmedProductionEdit(manufact, plant, date, 5.0)


def _invalid_confirmed_production_edit() -> ConfirmedProductionEdit:
    return ConfirmedProductionEdit(UNRESOLVABLE_KEY, 37, ARBITRARY_DATE_KEY, 5.0)


# Registro: ogni tipo dichiarato in `CellEdit` deve avere qui una coppia di
# factory (edit valido, edit con una chiave non risolvibile). Vedi
# `test_every_declared_edit_type_has_registered_invalid_key_coverage`.
_EDIT_FACTORIES: dict[type, tuple[typing.Callable[[], object], typing.Callable[[], object]]] = {
    RequestedProductionEdit: (_valid_requested_production_edit, _invalid_requested_production_edit),
    ConfirmedProductionEdit: (_valid_confirmed_production_edit, _invalid_confirmed_production_edit),
}


def _other_valid_edit(edit_type: type) -> object:
    """Un edit valido di un tipo diverso da `edit_type`, per esercitare
    anche la convalida incrociata fra tipi nello stesso batch. Se
    `_EDIT_FACTORIES` avesse un solo tipo registrato, ricade su un secondo
    edit valido dello stesso tipo — resta un batch a due elementi."""
    for candidate_type, (valid_factory, _) in _EDIT_FACTORIES.items():
        if candidate_type is not edit_type:
            return valid_factory()
    return _EDIT_FACTORIES[edit_type][0]()


def _state_snapshot(engine) -> dict:
    """Istantanea profonda dello stato mutabile privato del motore (non
    solo i due dizionari sorgente): usata per l'asserzione "byte-identico a
    prima della chiamata" — indipendente da un `full_recalculate()`, che è
    verificato separatamente e per un motivo diverso (la corruzione era
    silenziosa finché qualcuno non lo richiamava)."""
    return {
        "requested_production": dict(engine._requested_production),
        "confirmed_production": dict(engine._confirmed_production),
        "rp_by_product_date": {k: set(v) for k, v in engine._rp_by_product_date.items()},
        "values": {node: dict(vals) for node, vals in engine._values.items()},
    }


def test_every_declared_edit_type_has_registered_invalid_key_coverage():
    """Canarino: se `CellEdit` cresce di un tipo senza che questo file
    cresca con lui, il test fallisce qui — esplicitamente — invece di
    lasciare che il resto della suite passi senza aver mai esercitato una
    chiave non risolvibile per quel tipo. È la forma esatta del difetto
    trovato dal critic, riprodotta lato test invece che lato motore."""
    declared_types = set(typing.get_args(CellEdit))
    assert declared_types, "CellEdit non dichiara alcun tipo: il test non starebbe verificando nulla"
    registered_types = set(_EDIT_FACTORIES)
    missing = declared_types - registered_types
    assert not missing, (
        f"CellEdit dichiara {[t.__name__ for t in missing]} senza una coppia di factory "
        "valida/non-risolvibile in questo file — aggiungere una entry a _EDIT_FACTORIES"
    )


@pytest.mark.parametrize("edit_type", list(_EDIT_FACTORIES), ids=lambda t: t.__name__)
@pytest.mark.parametrize("position", ["alone", "first", "last"])
def test_unresolvable_edit_raises_leaves_state_untouched_and_full_recalculate_intact(engine, edit_type, position):
    """Il test cardine di questo file, generalizzato su tipo di edit e
    posizione nel batch:

    1. l'edit con una chiave non risolvibile deve sollevare;
    2. lo stato mutabile privato del motore deve restare byte-identico a
       prima della chiamata (nessuna scrittura parziale, `alone`/`first`
       verificano che nulla si scriva mai; `last` verifica che nemmeno
       l'edit valido *precedente* nello stesso batch sopravviva — 'tutto o
       niente');
    3. una `full_recalculate()` successiva deve **funzionare** (non restare
       rotta per sempre, il sintomo esatto del difetto) e dare lo stesso
       risultato di una chiamata equivalente fatta prima del tentativo
       fallito — non solo "non sollevare", ma "dare lo stesso risultato"."""
    _, invalid_factory = _EDIT_FACTORIES[edit_type]
    invalid_edit = invalid_factory()
    valid_edit = _other_valid_edit(edit_type)

    if position == "alone":
        batch = [invalid_edit]
    elif position == "first":
        batch = [invalid_edit, valid_edit]
    else:
        batch = [valid_edit, invalid_edit]

    baseline_full = engine.full_recalculate()
    state_before = _state_snapshot(engine)

    with pytest.raises((KeyError, ValueError)):
        engine.recalculate(batch)

    state_after = _state_snapshot(engine)
    assert state_after == state_before, (
        f"stato del motore mutato da un batch rifiutato (edit_type={edit_type.__name__}, "
        f"position={position!r}): il batch deve essere tutto-o-niente"
    )

    # Il sintomo esatto del difetto: non solo "full_recalculate() non solleva",
    # ma "dà lo stesso risultato di prima" — una corruzione latente che
    # cambiasse silenziosamente il risultato non basterebbe a far passare
    # solo un controllo "non solleva".
    after_full = engine.full_recalculate()
    assert after_full.values == baseline_full.values, (
        f"full_recalculate() dopo un batch rifiutato (edit_type={edit_type.__name__}, "
        f"position={position!r}) non corrisponde più al risultato di prima del tentativo"
    )
