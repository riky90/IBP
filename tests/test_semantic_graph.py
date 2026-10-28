"""Overlay a grafo: `neighbors()` (su `edge`) e `resolve_manufacturing_items()`
(su `item_link`) devono riflettere esattamente ciò che il seed ha scritto,
inclusi `quota`/`quota_source`/`offset_months`, e onorare la validità datata.

Round 2 (critic FAIL su round 1, ora corretto in `ibp/semantic/graph.py`):
- **F1**: `resolve_manufacturing_items` raggruppa per `(from_item,
  link_type)` — non più per singolo `to_item` — cosi' un target uscito dal
  mix più recente non sopravvive come riga "stale". Il test cardine di
  questo file lo riproduce esattamente come il critic (inserisce un
  override 100% su un solo target e verifica che l'altro sparisca e le
  quote tornino a sommare 100).
- **F2**: `neighbors()` normalizza `rel_type` in maiuscolo prima di
  interrogare `edge` — case-insensitive per il chiamante.
- **F3**: `neighbors()` solleva `GraphSnapshotLimitationError` per un
  `as_of` storico esplicito su un `rel_type` derivato da item_link
  (produces/aggregates/splits/dependent_demand), perché `edge` porta solo
  l'ultimo periodo noto di quelle relazioni — non per gli altri rel_type,
  che portano davvero una finestra di validità propria.

Round 3 (critic FAIL su round 2, ora corretto in `ibp/semantic/graph.py` e
`dimensions.py`):
- La guardia F3 ora scatta solo su `as_of < oggi` (non più `as_of != oggi`):
  un `as_of` futuro è la normale interrogazione dell'orizzonte a 24 mesi e
  non deve più sollevare.
- La guardia scatta anche quando `rel_type=None` e `as_of` è storico, su
  entrambe le `direction`: prima tornava silenziosamente `[]` anche se
  l'item aveva relazioni item_link-derivate a quella data. I rel_type
  strutturali (`BELONGS_TO`/`TARGETS`/`INFLUENCES`/`CONSTRAINS`) restano
  interrogabili storicamente se passati esplicitamente.
- `list_item_factors(role=...)` solleva `ValueError` per un `role` fuori
  dal CHECK di `item.role`, invece di tornare `[]`.
- (`PlantCapacity`/`ItemFactors` — nessun `Decimal`: vedi
  `test_semantic_numeric_types.py`.)

Fixture del seed usate qui (verificate contro `data/ibp.duckdb` reale):
- item 6 (planning_model) -> 'splits' su item 1663/1665: quota
  60/40 osservata (quota_source='observed_history') fino al period
  2026-08-01, poi un override manuale 55/45 al period 2026-09-01
  (quota_source='manual_override') — l'override del planner tracciato e
  distinguibile dal valore di regola (D2/AC7/AC8).
- item 1663 -> 'dependent_demand' su item 3008, offset_months=2 (routing
  obbligatorio Ganderkesee->Cerritos, AC6).
- item 1663: manufacturing_key, manufacturing_category='Cluster 11',
  slot_equivalence_factor=1.750, average_assembly_hours=38.85.
- item 1 (planning_model): manufacturing_category NULL, il caso
  null/assente di ItemFactors.
- edge (assumption, '2') --INFLUENCES--> (measure, '11'), valid_from
  2026-01-01, valid_to 2026-12-31: unico arco del seed con una finestra di
  validità chiusa, usato per il test di validità datata (e per il "non
  deve sollevare" di F3, perché INFLUENCES non è derivato da item_link).
"""
from __future__ import annotations

import datetime as dt

import pytest

from ibp.semantic.graph import GraphSnapshotLimitationError

SPLIT_SOURCE_ITEM = 6
SPLIT_TARGETS = {1663: 60.0, 1665: 40.0}
DEPENDENT_DEMAND_FROM = 1663
DEPENDENT_DEMAND_TO = 3008
MANUFACTURING_ITEM_WITH_FACTORS = 1663  # Cluster 11, factor 1.750, 38.85h
PLANNING_MODEL_WITHOUT_CATEGORY = 1


def test_resolve_manufacturing_items_returns_splits_with_quota_and_source(registry):
    # 2026-08-15 risolve al period 2026-08-01, prima dell'override manuale
    # del mese successivo: qui la quota è ancora quella osservata a consuntivo.
    results = registry.resolve_manufacturing_items(SPLIT_SOURCE_ITEM, as_of=dt.date(2026, 8, 15))
    splits = {r.to_item: r for r in results if r.link_type == "splits"}
    assert set(splits) == set(SPLIT_TARGETS)
    for to_item, expected_quota in SPLIT_TARGETS.items():
        row = splits[to_item]
        assert row.quota == pytest.approx(expected_quota)
        assert row.quota_source == "observed_history"
        assert row.identity.item_key == to_item


def test_resolve_manufacturing_items_surfaces_manual_override_distinctly(registry):
    """AC7/AC8: l'override del planner (period 2026-09-01, 55/45) è tracciato
    e distinguibile dal valore di regola/osservato (60/40) dei mesi precedenti."""
    results = registry.resolve_manufacturing_items(SPLIT_SOURCE_ITEM, as_of=dt.date(2026, 9, 1))
    splits = {r.to_item: r for r in results if r.link_type == "splits"}
    assert splits[1663].quota == pytest.approx(55.0)
    assert splits[1665].quota == pytest.approx(45.0)
    assert splits[1663].quota_source == "manual_override"
    assert splits[1665].quota_source == "manual_override"


def test_resolve_manufacturing_items_excludes_dependent_demand(registry):
    """F7: la risoluzione vendita->produzione cammina solo
    produces/aggregates/splits; dependent_demand è un salto successivo,
    lasciato a T3 per esplicita nota dell'implementatore."""
    results = registry.resolve_manufacturing_items(SPLIT_SOURCE_ITEM, as_of=dt.date(2026, 9, 1))
    assert all(r.link_type != "dependent_demand" for r in results)


def test_resolve_manufacturing_items_unknown_item_raises_key_error(registry):
    with pytest.raises(KeyError):
        registry.resolve_manufacturing_items(999_999_999)


def test_resolve_manufacturing_items_rejects_non_planning_model(registry, con):
    manufacturing_key = con.execute(
        "SELECT item_key FROM item WHERE role = 'manufacturing_key' LIMIT 1"
    ).fetchone()[0]
    with pytest.raises(ValueError):
        registry.resolve_manufacturing_items(manufacturing_key)


def test_resolve_manufacturing_items_honours_period_validity(registry):
    """`item_link` è time-phased per `period`; chiedere una data precedente
    a qualsiasi period seedato per questo link non deve restituire righe
    'in anticipo sul tempo'."""
    too_early = dt.date(2026, 1, 1)  # prima del primo period seedato (2026-04-01)
    results = registry.resolve_manufacturing_items(SPLIT_SOURCE_ITEM, as_of=too_early)
    assert results == []


def test_dependent_demand_link_exists_with_offset_two_months(con):
    """La domanda dipendente del semilavorato è una riga con offset_months=2
    (AC6) — verificato direttamente su item_link, dato che
    resolve_manufacturing_items() la esclude di proposito."""
    rows = con.execute(
        "SELECT DISTINCT offset_months FROM item_link "
        "WHERE from_item = ? AND to_item = ? AND link_type = 'dependent_demand'",
        [DEPENDENT_DEMAND_FROM, DEPENDENT_DEMAND_TO],
    ).fetchall()
    assert rows, "atteso almeno un item_link dependent_demand per la fixture nota"
    assert all(r[0] == 2 for r in rows)


def test_neighbors_on_edge_returns_split_edges_uppercase_rel_type(registry):
    edges = registry.neighbors("item", str(SPLIT_SOURCE_ITEM), rel_type="SPLITS")
    to_keys = {int(e.to_key) for e in edges}
    assert to_keys == set(SPLIT_TARGETS)
    assert all(e.rel_type == "SPLITS" for e in edges)


def test_neighbors_rel_type_is_case_insensitive(registry):
    """F2 (round 1 -> critic FAIL -> corretto): `edge.rel_type` è sempre
    maiuscolo per gli archi derivati da item_link, ma `neighbors()`
    normalizza `rel_type` prima della query — il case del chiamante non
    deve cambiare il risultato, in nessuna delle due direzioni."""
    lower = registry.neighbors("item", str(SPLIT_SOURCE_ITEM), rel_type="splits")
    upper = registry.neighbors("item", str(SPLIT_SOURCE_ITEM), rel_type="SPLITS")
    mixed = registry.neighbors("item", str(SPLIT_SOURCE_ITEM), rel_type="SpLiTs")

    assert lower != []  # non-vacuo: se fosse [] il test non proverebbe nulla
    assert lower == upper == mixed
    assert {int(e.to_key) for e in lower} == set(SPLIT_TARGETS)


def test_neighbors_rejects_unknown_direction(registry):
    with pytest.raises(ValueError):
        registry.neighbors("item", str(SPLIT_SOURCE_ITEM), direction="sideways")


def test_neighbors_honours_dated_validity_window(registry):
    """L'unico arco del seed con una finestra di validità chiusa
    (assumption '2' -INFLUENCES-> measure '11', 2026-01-01..2026-12-31):
    visibile dentro la finestra, non visibile dopo `valid_to`."""
    inside = registry.neighbors(
        "assumption", "2", rel_type="INFLUENCES", as_of=dt.date(2026, 6, 1)
    )
    assert len(inside) == 1
    assert inside[0].to_key == "11"

    after_expiry = registry.neighbors(
        "assumption", "2", rel_type="INFLUENCES", as_of=dt.date(2027, 1, 1)
    )
    assert after_expiry == [], "un arco scaduto (valid_to superato) non deve essere restituito"

    before_start = registry.neighbors(
        "assumption", "2", rel_type="INFLUENCES", as_of=dt.date(2025, 6, 1)
    )
    assert before_start == [], "un arco non ancora valido (prima di valid_from) non deve essere restituito"


def test_resolve_identity_returns_known_identifier_types(registry, con):
    item_key = con.execute("SELECT item_key FROM item_identifier LIMIT 1").fetchone()[0]
    identity = registry.resolve_identity(item_key, as_of=dt.date(2026, 9, 1))
    assert identity.item_key == item_key
    assert isinstance(identity.identifiers, dict)
    assert set(identity.identifiers).issubset({"element_name", "caption", "sap_material", "legacy"})


# ---------------------------------------------------------------------------
# F1 — regressione sul bug misurato dal critic: una riga stale (target
# uscito dal mix più recente) non deve sopravvivere alla risoluzione, e le
# quote del period restituito devono sempre sommare a 100 (l'invariante che
# `db/build_db.py` verifica sul seed, e che T3/T6 assumeranno vera). Costruito
# su una copia scrivibile del DB — mai sul file reale.
# ---------------------------------------------------------------------------


def test_resolve_manufacturing_items_drops_stale_target_after_override(registry_copy, writable_db_copy):
    """Riproduce esattamente il caso del critic: un override 100% su un solo
    target al period successivo deve far sparire l'altro target (che
    altrimenti resterebbe come riga stale dal period precedente), non
    affiancarlo. Prima della correzione: 1663=100 + 1665=45 (stale) = 145%."""
    con = writable_db_copy
    new_link_id = con.execute("SELECT MAX(link_id) + 1 FROM item_link").fetchone()[0]
    con.execute(
        """
        INSERT INTO item_link
            (link_id, from_item, to_item, link_type, period, quota_pct, quota_source,
             quota_window_months, offset_months, override_by, override_at, valid_from, valid_to)
        VALUES (?, ?, ?, 'splits', DATE '2026-10-01', 100, 'manual_override',
                NULL, 0, 'test-harness', NULL, DATE '2026-10-01', NULL)
        """,
        [new_link_id, SPLIT_SOURCE_ITEM, 1663],
    )

    results = registry_copy.resolve_manufacturing_items(SPLIT_SOURCE_ITEM, as_of=dt.date(2026, 10, 15))
    splits = {r.to_item: r for r in results if r.link_type == "splits"}

    assert 1665 not in splits, "il target uscito dal mix (1665) non deve sopravvivere come riga stale"
    assert set(splits) == {1663}
    assert sum(r.quota for r in splits.values()) == pytest.approx(100.0)
    assert splits[1663].quota == pytest.approx(100.0)
    assert splits[1663].quota_source == "manual_override"


def test_resolve_manufacturing_items_partial_period_still_sums_to_100(registry_copy, writable_db_copy):
    """Variante: l'override del nuovo period copre solo un target ma è
    scritto come 100%, quindi resta l'unico membro del mix a quel period —
    non un mix con quota 'a metà' che sommerebbe a meno di 100. Verifica
    che il raggruppamento sia per (from_item, link_type) e non più per
    (from_item, to_item, link_type): il vecchio period (60/40, due righe)
    non deve mescolarsi col nuovo (100, una riga)."""
    con = writable_db_copy
    new_link_id = con.execute("SELECT MAX(link_id) + 1 FROM item_link").fetchone()[0]
    con.execute(
        """
        INSERT INTO item_link
            (link_id, from_item, to_item, link_type, period, quota_pct, quota_source,
             quota_window_months, offset_months, override_by, override_at, valid_from, valid_to)
        VALUES (?, ?, ?, 'splits', DATE '2026-10-01', 100, 'manual_override',
                NULL, 0, 'test-harness', NULL, DATE '2026-10-01', NULL)
        """,
        [new_link_id, SPLIT_SOURCE_ITEM, 1663],
    )

    old_period_results = registry_copy.resolve_manufacturing_items(SPLIT_SOURCE_ITEM, as_of=dt.date(2026, 8, 15))
    old_splits = {r.to_item: r for r in old_period_results if r.link_type == "splits"}
    assert set(old_splits) == {1663, 1665}
    assert sum(r.quota for r in old_splits.values()) == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# F3 — `GraphSnapshotLimitationError`: sollevata per un `as_of` storico
# esplicito sui rel_type derivati da item_link, non per gli altri.
# ---------------------------------------------------------------------------


def test_neighbors_raises_snapshot_limitation_for_historical_as_of_on_item_link_rel_type(registry):
    with pytest.raises(GraphSnapshotLimitationError):
        registry.neighbors("item", str(SPLIT_SOURCE_ITEM), rel_type="splits", as_of=dt.date(2026, 1, 1))


@pytest.mark.parametrize("rel_type", ["produces", "AGGREGATES", "splits", "dependent_demand"])
def test_neighbors_raises_snapshot_limitation_for_every_item_link_rel_type(registry, rel_type):
    with pytest.raises(GraphSnapshotLimitationError):
        registry.neighbors("item", str(SPLIT_SOURCE_ITEM), rel_type=rel_type, as_of=dt.date(2026, 1, 1))


def test_neighbors_does_not_raise_snapshot_limitation_for_non_item_link_rel_type(registry):
    """INFLUENCES porta una vera finestra di validità propria su `edge`
    (non è materializzato solo per l'ultimo period di item_link): un
    `as_of` storico è legittimo e non deve sollevare `GraphSnapshotLimitationError`."""
    result = registry.neighbors("assumption", "2", rel_type="INFLUENCES", as_of=dt.date(2025, 6, 1))
    assert result == []  # validità onorata (vedi test dedicato sopra), ma nessuna eccezione


def test_neighbors_does_not_raise_when_as_of_omitted_even_for_item_link_rel_type(registry):
    """La guardia scatta solo per un `as_of` esplicito e diverso da oggi:
    senza `as_of` (default oggi) la stessa query non deve sollevare."""
    registry.neighbors("item", str(SPLIT_SOURCE_ITEM), rel_type="splits")  # non deve sollevare


def test_neighbors_does_not_raise_when_as_of_is_explicitly_today(registry):
    registry.neighbors(
        "item", str(SPLIT_SOURCE_ITEM), rel_type="splits", as_of=dt.date.today()
    )  # non deve sollevare


# ---------------------------------------------------------------------------
# get_item_factors / list_item_factors (AC2 generalizzato su `item`, AC3)
# ---------------------------------------------------------------------------


def test_item_factors_returns_known_manufacturing_item_values(registry, con):
    expected = con.execute(
        "SELECT manufacturing_category, slot_equivalence_factor, average_assembly_hours "
        "FROM item WHERE item_key = ?",
        [MANUFACTURING_ITEM_WITH_FACTORS],
    ).fetchone()
    factors = registry.item_factors(MANUFACTURING_ITEM_WITH_FACTORS)
    assert factors.item_key == MANUFACTURING_ITEM_WITH_FACTORS
    assert factors.role == "manufacturing_key"
    assert factors.manufacturing_category == expected[0] == "Cluster 11"
    assert float(factors.slot_equivalence_factor) == pytest.approx(float(expected[1]))
    assert float(factors.average_assembly_hours) == pytest.approx(float(expected[2]))


def test_item_factors_null_manufacturing_category_for_planning_model(registry):
    """Caso null/assente: un planning_model non ha manufacturing_category
    (valorizzata solo per manufacturing_key/semi_finished, vedi db/schema.sql)."""
    factors = registry.item_factors(PLANNING_MODEL_WITHOUT_CATEGORY)
    assert factors.role == "planning_model"
    assert factors.manufacturing_category is None
    # slot_equivalence_factor/average_assembly_hours hanno DEFAULT (1.0 / 0.0),
    # non NULL — restano numeri validi anche per un planning_model.
    assert float(factors.slot_equivalence_factor) == pytest.approx(1.0)
    assert float(factors.average_assembly_hours) == pytest.approx(0.0)


def test_item_factors_unknown_item_raises_key_error(registry):
    with pytest.raises(KeyError):
        registry.item_factors(999_999_999)


def test_list_item_factors_filters_by_role(registry, con):
    total = con.execute("SELECT count(*) FROM item").fetchone()[0]
    manufacturing = con.execute("SELECT count(*) FROM item WHERE role = 'manufacturing_key'").fetchone()[0]

    assert len(registry.list_item_factors()) == total
    manufacturing_only = registry.list_item_factors(role="manufacturing_key")
    assert len(manufacturing_only) == manufacturing
    assert all(f.role == "manufacturing_key" for f in manufacturing_only)


# ---------------------------------------------------------------------------
# manufacturing_category su ManufacturingRealisation
# ---------------------------------------------------------------------------


def test_manufacturing_realisation_carries_manufacturing_category(registry):
    results = registry.resolve_manufacturing_items(SPLIT_SOURCE_ITEM, as_of=dt.date(2026, 8, 15))
    by_item = {r.to_item: r for r in results}
    assert by_item[1663].manufacturing_category == "Cluster 11"
    assert by_item[1665].manufacturing_category == "Cluster 13"


# ---------------------------------------------------------------------------
# Round 3 — as_of futuro non deve più sollevare (orizzonte di piano a 24 mesi)
# ---------------------------------------------------------------------------


def _months_from_today(months: int) -> dt.date:
    today = dt.date.today()
    year = today.year + (today.month - 1 + months) // 12
    month = (today.month - 1 + months) % 12 + 1
    return dt.date(year, month, 1)


def test_neighbors_forward_as_of_inside_planning_horizon_does_not_raise_and_returns_results(registry):
    """Dentro l'orizzonte di piano a 24 mesi (qui: +6 mesi) — la query
    normale che T6/T7 faranno."""
    future_as_of = _months_from_today(6)
    edges = registry.neighbors("item", str(SPLIT_SOURCE_ITEM), rel_type="SPLITS", as_of=future_as_of)
    assert edges != []
    assert {int(e.to_key) for e in edges} == set(SPLIT_TARGETS)


def test_neighbors_forward_as_of_beyond_24_months_does_not_raise(registry):
    """Anche oltre l'orizzonte dichiarato (+30 mesi): la guardia F3 riguarda
    solo il passato, non il futuro, per quanto lontano."""
    far_future_as_of = _months_from_today(30)
    edges = registry.neighbors("item", str(SPLIT_SOURCE_ITEM), rel_type="SPLITS", as_of=far_future_as_of)
    assert edges != []
    assert {int(e.to_key) for e in edges} == set(SPLIT_TARGETS)


def test_neighbors_forward_as_of_with_no_rel_type_does_not_raise(registry):
    """Il `rel_type=None` guardato riguarda solo lo storico: in avanti deve
    continuare a funzionare senza filtro esplicito."""
    future_as_of = _months_from_today(6)
    edges = registry.neighbors("item", str(SPLIT_SOURCE_ITEM), as_of=future_as_of)
    assert edges != []


# ---------------------------------------------------------------------------
# Round 3 — rel_type=None con as_of storico: guardata su entrambe le
# direction; i rel_type strutturali restano interrogabili storicamente.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("direction", ["out", "in"])
def test_neighbors_rel_type_none_historical_as_of_raises_on_both_directions(registry, direction):
    """Il caso esatto misurato dal critic: senza rel_type esplicito,
    neighbors("item","6", as_of=<passato>) tornava [] anche se l'item aveva
    SPLITS 60/40 a quella data — ora solleva invece di rispondere in modo
    plausibile ma sbagliato."""
    with pytest.raises(GraphSnapshotLimitationError):
        registry.neighbors(
            "item", str(SPLIT_SOURCE_ITEM), rel_type=None, direction=direction, as_of=dt.date(2026, 6, 1)
        )


def test_neighbors_rel_type_none_as_of_omitted_does_not_raise(registry):
    registry.neighbors("item", str(SPLIT_SOURCE_ITEM))  # non deve sollevare


def test_neighbors_rel_type_none_as_of_today_does_not_raise(registry):
    registry.neighbors("item", str(SPLIT_SOURCE_ITEM), as_of=dt.date.today())  # non deve sollevare


@pytest.mark.parametrize("direction", ["out", "in"])
def test_neighbors_structural_rel_type_resolves_historically_when_explicit(registry, direction):
    """`INFLUENCES` (structural, non derivato da item_link) passato
    esplicitamente resta interrogabile con un `as_of` storico, su entrambe
    le direction — solo `rel_type=None` è guardato."""
    result = registry.neighbors(
        "assumption", "2", rel_type="INFLUENCES", direction=direction, as_of=dt.date(2026, 6, 1)
    )
    # direction='out' trova l'arco (assumption e' from_type), 'in' no — ma
    # nessuna delle due deve sollevare GraphSnapshotLimitationError.
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Round 3 — list_item_factors: ValueError su role invalido, ok su ogni role valido
# ---------------------------------------------------------------------------


def test_list_item_factors_invalid_role_raises_value_error(registry):
    with pytest.raises(ValueError):
        registry.list_item_factors(role="not_a_real_role")


@pytest.mark.parametrize("role", ["planning_model", "manufacturing_key", "semi_finished"])
def test_list_item_factors_works_for_every_valid_role(registry, role, con):
    expected_count = con.execute("SELECT count(*) FROM item WHERE role = ?", [role]).fetchone()[0]
    result = registry.list_item_factors(role=role)
    assert len(result) == expected_count
    assert all(f.role == role for f in result)
