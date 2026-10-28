"""Registry delle dimensioni (A4/D1): metadata caricati dal DB, mai literal.

`list_dimensions` introspeziona `information_schema.columns` per ogni
tabella-dimensione nota — l'elenco di attributi non è una lista Python
mantenuta a mano, è quello che lo schema *in quel momento* dichiara.
`list_plants`/`get_plant_capacity` leggono `DPLANT` riga per riga: AC2 vuole
`max_slots`, `slot_granularity_factor` e il layout come master data, non
come literal (`30`, `8`, `4.0`) nel codice — qui non ce n'è nessuno.
`get_item_factors`/`list_item_factors` fanno lo stesso per `item.
slot_equivalence_factor` (AC2, il "x2" di Westvale generalizzato) e
`item.average_assembly_hours` (AC3, la seconda valuta di capacità): T3
(`slots_requested`) li legge da qui invece di scrivere SQL proprio su una
tabella che non possiede.

Nota sulla mappa `_DIMENSION_KEYS`: i nomi di tabella e la colonna chiave
sono struttura di schema (coerente con `db/schema.sql`), non regole di
business — è la stessa distinzione che README.md fa esplicitamente per
`encoding="utf-8"` a proposito di AC2: un nome di colonna non è una soglia
di capacità.
"""
from __future__ import annotations

from dataclasses import dataclass

# Tabelle-dimensione del mirror dEPM + item master (db/schema.sql, sezione 1).
_DIMENSION_KEYS: dict[str, str] = {
    "item": "item_key",
    "DPLANT": "plant_key",
    "DSALES_DIVISION": "division_key",
    "DVERSIONS": "version_key",
    "DIM_DATE": "date_key",
    "DMEASURE_DEMAND": "measure_key",
    "DMEASURE_OPS": "measure_key",
}


@dataclass(frozen=True)
class DimensionAttribute:
    name: str
    dtype: str


@dataclass(frozen=True)
class Dimension:
    name: str
    table: str
    key_column: str
    attributes: tuple[DimensionAttribute, ...]


def list_dimensions(con) -> list[Dimension]:
    """Una `Dimension` per ogni tabella nota, con gli attributi letti da
    `information_schema.columns` (mai una lista Python hardcoded)."""
    out: list[Dimension] = []
    for table, key_col in _DIMENSION_KEYS.items():
        rows = con.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = ? ORDER BY ordinal_position",
            [table],
        ).fetchall()
        if not rows:
            raise RuntimeError(f"dimensione dichiarata ma tabella assente dal DB: {table}")
        attrs = tuple(DimensionAttribute(name=r[0], dtype=r[1]) for r in rows)
        out.append(Dimension(name=table, table=table, key_column=key_col, attributes=attrs))
    return out


def get_dimension(con, table: str) -> Dimension:
    for d in list_dimensions(con):
        if d.table == table:
            return d
    raise KeyError(f"dimensione sconosciuta: {table}")


@dataclass(frozen=True)
class PlantCapacity:
    """Riga `DPLANT` come valore di dominio: layout, capacità (slot/ore) e
    tipo di plant, tutti letti dal DB (AC2). `slot_granularity_factor` è il
    "x2" di Westvale reso dato — qui è semplicemente il valore della colonna.

    `slot_granularity_factor` è `float`, non `Decimal`: nello schema è
    `DECIMAL(6,3)`, ma l'unico uso previsto (T3, `slots_requested`) lo
    moltiplica contro misure `DOUBLE` (`TSOP_OPS`/`TWSC_PAR_CALWEEK`) — è
    aritmetica di capacità contro un cubo a doppia precisione, non un
    ammontare che deve sommare esattamente (a differenza delle quote di
    `item_link`, che restano `float` anch'esse ma per una ragione diversa:
    il seed le genera già come frazioni di 100 non decimali esatte). Un
    `Decimal` qui costringerebbe ogni chiamante a convertire prima di
    moltiplicare contro `DOUBLE` — è quel salto silenzioso che ha rotto
    l'uso previsto in revisione."""

    plant_key: int
    plant_code: str
    plant_name: str
    plant_region: str
    plant_type: str
    layout_type: str
    max_slots: int
    slot_granularity_factor: float


_PLANT_COLUMNS = (
    "plant_key, plant_code, plant_name, plant_region, plant_type, "
    "layout_type, max_slots, slot_granularity_factor"
)


def _plant_capacity_from_row(r) -> PlantCapacity:
    return PlantCapacity(
        plant_key=r[0], plant_code=r[1], plant_name=r[2], plant_region=r[3],
        plant_type=r[4], layout_type=r[5], max_slots=r[6],
        slot_granularity_factor=float(r[7]),
    )


def list_plants(con) -> list[PlantCapacity]:
    rows = con.execute(f"SELECT {_PLANT_COLUMNS} FROM DPLANT ORDER BY plant_key").fetchall()
    return [_plant_capacity_from_row(r) for r in rows]


def get_plant_capacity(con, plant_key: int) -> PlantCapacity:
    rows = con.execute(
        f"SELECT {_PLANT_COLUMNS} FROM DPLANT WHERE plant_key = ?", [plant_key]
    ).fetchall()
    if not rows:
        raise KeyError(f"plant_key sconosciuto: {plant_key}")
    return _plant_capacity_from_row(rows[0])


# Valori del CHECK su item.role (db/schema.sql) — non una soglia di capacità
# (AC2), solo l'enumerazione già chiusa dallo schema, usata per validare
# l'input di list_item_factors invece di lasciar passare un typo silenzioso.
_ITEM_ROLES = frozenset({"planning_model", "manufacturing_key", "semi_finished"})


@dataclass(frozen=True)
class ItemFactors:
    """I due fattori di capacità che vivono su `item` invece che su
    `DPLANT`: `slot_equivalence_factor` (AC2, quanti slot standard equivale
    un'unità di questo item) e `average_assembly_hours` (AC3, la seconda
    valuta di capacità per i plant a isole). Valorizzati per
    `manufacturing_key`/`semi_finished`; `0.0` per default sui
    `planning_model` (vedi `item` in db/schema.sql).

    Entrambi `float`, non `Decimal`, per lo stesso motivo di
    `PlantCapacity.slot_granularity_factor`: l'uso previsto (T3) li
    moltiplica contro la domanda derivata, che è `DOUBLE` nel cubo
    (`TSOP_OPS`) — mescolare `Decimal` e `float` nella stessa espressione
    solleva `TypeError` invece di un numero, ed è esattamente il difetto
    corretto in questa revisione."""

    item_key: int
    role: str
    manufacturing_category: str | None
    slot_equivalence_factor: float
    average_assembly_hours: float


_ITEM_FACTOR_COLUMNS = (
    "item_key, role, manufacturing_category, slot_equivalence_factor, average_assembly_hours"
)


def _item_factors_from_row(r) -> ItemFactors:
    return ItemFactors(
        item_key=r[0], role=r[1], manufacturing_category=r[2],
        slot_equivalence_factor=float(r[3]), average_assembly_hours=float(r[4]),
    )


def get_item_factors(con, item_key: int) -> ItemFactors:
    rows = con.execute(
        f"SELECT {_ITEM_FACTOR_COLUMNS} FROM item WHERE item_key = ?", [item_key]
    ).fetchall()
    if not rows:
        raise KeyError(f"item_key sconosciuto: {item_key}")
    return _item_factors_from_row(rows[0])


def list_item_factors(con, role: str | None = None) -> list[ItemFactors]:
    """`role=None` ritorna tutti gli item; passare `role='manufacturing_key'`
    (o `'semi_finished'`) filtra ai soli item che consumano davvero le due
    valute di capacità. Solleva `ValueError` per un `role` che non è fra
    quelli del CHECK di schema — un typo qui non deve tornare silenziosamente
    una lista vuota che si legge come "nessun item di quel ruolo"."""
    if role is not None and role not in _ITEM_ROLES:
        raise ValueError(f"role sconosciuto: {role!r} (atteso uno tra {sorted(_ITEM_ROLES)})")
    if role is not None:
        rows = con.execute(
            f"SELECT {_ITEM_FACTOR_COLUMNS} FROM item WHERE role = ? ORDER BY item_key",
            [role],
        ).fetchall()
    else:
        rows = con.execute(f"SELECT {_ITEM_FACTOR_COLUMNS} FROM item ORDER BY item_key").fetchall()
    return [_item_factors_from_row(r) for r in rows]
