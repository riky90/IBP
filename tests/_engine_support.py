"""Supporto condiviso per i test di `ibp/engine/` (T3). Non è un file di
test (nessun `test_*`): fixture-helper e dati di fixture reali, verificati
contro `data/ibp.duckdb`.

Perché una coppia di versioni specifica: `RecalcEngine.__init__` carica **per
intero** `TSOP_DEMAND` per `demand_version_key` e chiama subito
`full_recalculate()` — sul DB reale questo costa decine di secondi (query +
risoluzione `item_link` per ogni `(product_key, date_key)` scoperto). Le
uniche versioni in cui sia `TSOP_OPS` (per `confirmed_production`) sia
`TWSC_PAR_CALWEEK` (per `weeks_production`, quindi `slots_requested` non
sempre-zero) avrebbero dati *insieme* non esistono nel seed corrente (limite
di volume dichiarato in README.md, non un difetto di T3): `TWSC_PAR_CALWEEK`
esiste **solo** per la versione 371 (`SOP_2026_09_SUPPLY_A`, il ciclo
aperto), mentre `TSOP_OPS` per quella versione è vuoto. Si usa quindi
`demand_version_key=369` (`SOP_2026_09_DEMAND_P`, stesso ciclo) +
`ops_version_key=371`: `weeks_production` risolve per davvero (quindi
`slots_requested` è quasi ovunque non-zero), e `confirmed_production` parte
vuoto — il che è la condizione ideale per testare `ConfirmedProductionEdit`
come root esogeno senza stato preesistente da confondere con l'edit.
"""
from __future__ import annotations

import math

DEMAND_VERSION_KEY = 369  # SOP_2026_09_DEMAND_P
OPS_VERSION_KEY = 371  # SOP_2026_09_SUPPLY_A (unica versione con TWSC_PAR_CALWEEK)

# Manufacturing key con copertura rate_card (Cluster 10 è una delle 4/14
# categorie coperte nel seed) — usato per i test dove value_gap deve esistere.
MANUFACT_KEY_WITH_RATE = 1662
PLANT_FOR_MANUFACT_WITH_RATE = 37  # production_eligibility.priority minima

# Manufacturing key SENZA copertura rate_card (Cluster 11/13) — usato per il
# caso "assente, non zero".
MANUFACT_KEY_WITHOUT_RATE = 1663
PLANT_FOR_MANUFACT_WITHOUT_RATE = 50

# Due planning model che 'aggregates' sullo stesso manufacturing_key 1662
# (item_link, F7): editarli nello stesso batch è il caso "diamante" — la
# stessa cella derived_manufacturing_demand è raggiunta da due percorsi.
AGGREGATING_PRODUCTS_INTO_1662 = (9, 11)

# Pool di (product_key, division_key, date_key) realmente presenti in
# TSOP_DEMAND per version_key=369, measure REQ_PROD — verificato contro il
# DB reale (66 combinazioni per i prodotti 6/9/11/14).
REQUESTED_PRODUCTION_KEY_POOL: tuple[tuple[int, int, int], ...] = (
    (6, 1, 202609), (6, 1, 202610), (6, 1, 202611), (6, 1, 202612), (6, 1, 202701), (6, 1, 202702),
    (6, 11, 202609), (6, 11, 202610), (6, 11, 202611), (6, 11, 202612), (6, 11, 202701), (6, 11, 202702),
    (6, 15, 202609), (6, 15, 202610), (6, 15, 202611), (6, 15, 202612), (6, 15, 202701), (6, 15, 202702),
    (6, 49, 202609), (6, 49, 202610), (6, 49, 202611), (6, 49, 202612), (6, 49, 202701), (6, 49, 202702),
    (6, 58, 202609), (6, 58, 202610), (6, 58, 202611), (6, 58, 202612), (6, 58, 202701), (6, 58, 202702),
    (9, 9, 202609), (9, 9, 202610), (9, 9, 202611), (9, 9, 202612), (9, 9, 202701),
    (9, 32, 202609), (9, 32, 202610), (9, 32, 202611), (9, 32, 202612), (9, 32, 202701),
    (11, 2, 202609), (11, 2, 202610), (11, 2, 202611), (11, 2, 202612),
    (11, 15, 202609), (11, 15, 202610), (11, 15, 202611), (11, 15, 202612),
)

# Pool di celle confirmed_production da editare (chiave esogena, non serve
# che esistano già in TSOP_OPS — vedi docstring modulo: per questa coppia di
# versioni TSOP_OPS parte vuoto).
CONFIRMED_PRODUCTION_KEY_POOL: tuple[tuple[int, int, int], ...] = (
    (1662, 37, 202609), (1662, 37, 202610), (1662, 48, 202609),
    (1663, 50, 202609), (1663, 50, 202610), (1663, 6, 202609),
    (1665, 46, 202609), (1665, 46, 202610),
)


def clone_engine(engine):
    """Copia indipendente di uno stato di `RecalcEngine`, senza ripagare il
    costo di `__init__` (query + `full_recalculate()` iniziale, decine di
    secondi sul DB reale).

    Condivide `con` e le cache *davvero* pure, quelle indicizzate solo da
    identificatori di master data statici e mai estese in place in un modo
    che dipenda dallo stato di un edit (`_item_factor_cache`,
    `_plant_capacity_cache`, `_eligible_plant_cache`, `_weeks_cache`,
    `_rate_cache`, `_heights`): una chiave mancante viene letta dal DB e
    scritta una volta sola, con lo stesso valore indipendentemente da quale
    clone l'ha causata — condividerle è sicuro e le tiene calde (nessuna
    nuova query DB per le chiavi già scoperte dal `full_recalculate()`
    iniziale, che copre l'intero perimetro `TSOP_DEMAND` caricato).

    **Non** condivide `_rp_targets`/`_dmd_reverse` (fix di un difetto
    segnalato dal critic T3): `_ensure_rp_targets()` le estende in place
    quando incontra un `(product_key, date_key)` mai visto prima —
    `self._dmd_reverse.setdefault(target_key, set()).add(...)` può mutare
    un `set` già esistente nel dizionario condiviso, non solo aggiungere una
    chiave nuova. Nessun test attuale edita una combinazione fuori dal
    perimetro caricato al costruttore (quindi il sintomo non si è ancora
    visto), ma è esattamente la forma di edit che le probe del critic usano
    — condividerle avrebbe fatto trapelare lo stato di un edit di un test in
    un altro clone, producendo un fallimento irriproducibile mesi dopo. Sono
    quindi copiate un livello in profondità (dict-di-dict, dict-di-set) per
    ogni clone, non solo al primo livello.

    Copia sempre, per ogni clone, gli stati mutabili da un edit:
    `_requested_production`, `_confirmed_production`, `_rp_by_product_date`
    (le division note per `(product, date)`, che un edit può estendere), e
    `_values` (lo stato calcolato corrente di ogni nodo)."""
    clone = object.__new__(type(engine))
    clone.__dict__.update(engine.__dict__)
    clone._requested_production = dict(engine._requested_production)
    clone._confirmed_production = dict(engine._confirmed_production)
    clone._rp_by_product_date = {k: set(v) for k, v in engine._rp_by_product_date.items()}
    clone._values = {node: dict(vals) for node, vals in engine._values.items()}
    clone._rp_targets = {k: dict(v) for k, v in engine._rp_targets.items()}
    clone._dmd_reverse = {k: set(v) for k, v in engine._dmd_reverse.items()}
    return clone


def values_close(a: dict, b: dict, *, rel_tol: float = 0.0, abs_tol: float = 0.0) -> bool:
    """Confronta due `CellValues` (`dict[str, dict[CellKey, float]]`).

    Round critic T3 (era necessaria una tolleranza, ora non più):
    `_compute_dmd_cell` sommava iterando direttamente su `set`
    (`_dmd_reverse`/`_rp_by_product_date`), il cui ordine non è garantito
    stabile fra una cache costruita incrementalmente (edit dopo edit) e una
    ricostruita da zero — la somma in virgola mobile non è associativa,
    quindi un confronto `==` esatto falliva per rumore nell'ultimo bit (8
    batch su 120 nelle prove originali). Il motore ora somma su
    `sorted(...)`, un ordine totale esplicito: l'ordine di accumulo è
    identico per costruzione fra `recalculate()` e `full_recalculate()`, e
    il confronto può tornare a essere `==` esatto (`rel_tol=abs_tol=0.0` di
    default). I parametri restano configurabili — se un caso reale
    richiedesse ancora una tolleranza, sarebbe un fatto sul motore da
    riportare, non da nascondere qui allentando silenziosamente il default."""
    if set(a) != set(b):
        return False
    for node in a:
        node_a, node_b = a[node], b[node]
        if set(node_a) != set(node_b):
            return False
        for key, value_a in node_a.items():
            value_b = node_b[key]
            if rel_tol == 0.0 and abs_tol == 0.0:
                if value_a != value_b:
                    return False
            elif not math.isclose(value_a, value_b, rel_tol=rel_tol, abs_tol=abs_tol):
                return False
    return True


def diff_values(a: dict, b: dict) -> list[tuple[str, object, object, object]]:
    """Elenco delle differenze esatte `(node, key, valore_a, valore_b)` fra
    due `CellValues`, per messaggi d'errore leggibili quando `values_close`
    fallisce."""
    diffs: list[tuple[str, object, object, object]] = []
    for node in sorted(set(a) | set(b)):
        node_a, node_b = a.get(node, {}), b.get(node, {})
        for key in sorted(set(node_a) | set(node_b), key=repr):
            va, vb = node_a.get(key), node_b.get(key)
            if va != vb:
                diffs.append((node, key, va, vb))
    return diffs


def assert_matches_full_recalculate(engine, result) -> None:
    """Il cuore di AC10: dopo aver applicato un batch via `recalculate()`
    (il cui esito è `result`), un `full_recalculate()` sullo **stesso** stato
    sorgente deve produrre valori **esattamente identici** (`==`, non più
    entro tolleranza — vedi `values_close`) per ogni nodo e ogni chiave —
    non un sottoinsieme, non un superinsieme."""
    full = engine.full_recalculate()
    assert values_close(result.values, full.values), (
        f"recalculate() diverge da full_recalculate(): {diff_values(result.values, full.values)[:10]}"
    )
