"""Overlay a grafo (A4): query su `edge` + risoluzione item lato vendita ->
item manifatturieri via `item_link` (F7).

Due limiti misurati e corretti in revisione (round 1, critic FAIL) restano
documentati qui perché il codice da solo non li rende ovvi:

1. **Case di `rel_type`**: le righe di `edge` derivate da `item_link`
   portano `rel_type` in maiuscolo (`db/seed/graph.py` fa
   `r["link_type"].upper()` — 'PRODUCES', 'AGGREGATES', 'SPLITS',
   'DEPENDENT_DEMAND'), mentre `item_link.link_type` resta minuscolo
   ('produces', ...) perché è quello il case del CHECK di schema.
   `neighbors()` normalizza `rel_type` in maiuscolo prima di interrogare
   `edge`, così `neighbors(..., "produces")` e `neighbors(..., "PRODUCES")`
   sono equivalenti — non serve più che il chiamante lo sappia.

2. **`edge` non è un ledger storico per le relazioni item->item**:
   `db/seed/graph.py` materializza in `edge` **solo l'ultimo periodo** di
   ogni `(from_item, to_item, link_type)` (vedi `latest_period` lì), non
   l'intera storia time-phased che `item_link` porta invece riga per riga.
   Questo significa che `neighbors()` con un `as_of` **nel passato**
   (`as_of < oggi` — non un `as_of` futuro: il piano guarda avanti fino a
   24 mesi, e per quello lo snapshot corrente è la risposta corretta) **non
   può** rispondere "come era il grafo allora" per le relazioni item->item
   derivate da `item_link` ('PRODUCES'/'AGGREGATES'/'SPLITS'/
   'DEPENDENT_DEMAND'). Per la storia completa, time-phased, usa
   `resolve_manufacturing_items()`, che interroga `item_link` direttamente
   ed è la fonte autorevole per le relazioni di produzione item->item.

   Per non restituire silenziosamente `[]` quando la domanda cade in questo
   buco (la risposta sembra plausibile ma è vuota per il limite dello
   snapshot, non perché la relazione non esistesse), `neighbors()` solleva
   `GraphSnapshotLimitationError` per **ogni** `as_of` passato esplicito:
   sia quando `rel_type` è uno dei quattro tipi sopra, sia quando
   `rel_type=None` — in quel caso non si può filtrare "i tipi sicuri" dal
   risultato perché non c'è modo di sapere, guardando solo `edge`, se per
   quel nodo esistevano anche relazioni item->item in quel periodo che lo
   snapshot ha da tempo sovrascritto: una risposta parziale sarebbe silenziosa
   quanto una vuota. Chi vuole solo i tipi strutturali (`BELONGS_TO`,
   `TARGETS`, `INFLUENCES`, `CONSTRAINS` — quelli con `valid_from` di
   default all'epoca e nessuna sovrascrittura da snapshot) a una data
   passata deve passare quel `rel_type` esplicitamente.

   **Per rimuovere davvero il limite** servirebbe un cambio in T1
   (`db/seed/graph.py`, non di competenza di T2): emettere un arco `edge`
   per *ogni* periodo di `item_link`, non solo per il più recente — a quel
   punto `neighbors()` potrebbe leggere la storia direttamente da `edge`
   senza più bisogno della guardia esplicita qui sotto.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass

_MANUFACTURING_LINK_TYPES = ("produces", "aggregates", "splits")

# rel_type con cui `edge` materializza solo l'ultimo periodo di `item_link`
# (vedi punto 2 sopra) — usati per la guardia esplicita in `neighbors()`.
_ITEM_LINK_SNAPSHOT_REL_TYPES = frozenset(
    t.upper() for t in (*_MANUFACTURING_LINK_TYPES, "dependent_demand")
)


class GraphSnapshotLimitationError(ValueError):
    """`edge` porta solo l'ultimo periodo noto per le relazioni item->item
    derivate da `item_link`: interrogarlo con un `as_of` nel passato, per
    uno di questi `rel_type` (o senza `rel_type`, che potrebbe includerli),
    non può dare una risposta storica corretta. Sollevata invece di
    restituire `[]` o un sottoinsieme silenzioso — vedi il docstring di
    modulo."""


@dataclass(frozen=True)
class Edge:
    edge_id: int
    from_type: str
    from_key: str
    rel_type: str
    to_type: str
    to_key: str
    valid_from: dt.date
    valid_to: dt.date | None
    attrs: dict


def _parse_edge(row) -> Edge:
    edge_id, from_type, from_key, rel_type, to_type, to_key, valid_from, valid_to, attrs_json = row
    return Edge(
        edge_id=edge_id, from_type=from_type, from_key=from_key, rel_type=rel_type,
        to_type=to_type, to_key=to_key, valid_from=valid_from, valid_to=valid_to,
        attrs=json.loads(attrs_json) if attrs_json else {},
    )


_EDGE_COLUMNS = (
    "edge_id, from_type, from_key, rel_type, to_type, to_key, valid_from, valid_to, attrs_json"
)


def _validity_clause(alias: str = "") -> str:
    """`valid_from <= ? AND (valid_to IS NULL OR valid_to > ?)`, opzionalmente
    con prefisso di alias tabella (serve quando la query fa un JOIN e la
    colonna da sola sarebbe ambigua)."""
    col_from = f"{alias}.valid_from" if alias else "valid_from"
    col_to = f"{alias}.valid_to" if alias else "valid_to"
    return f"{col_from} <= ? AND ({col_to} IS NULL OR {col_to} > ?)"


def neighbors(
    con,
    node_type: str,
    node_key: str,
    rel_type: str | None = None,
    *,
    direction: str = "out",
    as_of: dt.date | None = None,
) -> list[Edge]:
    """Vicini di `(node_type, node_key)` su `edge`, rispettando la validità
    datata (`valid_from`/`valid_to`).

    `rel_type` è normalizzato in maiuscolo prima della query (vedi punto 1
    del docstring di modulo): il chiamante può passare sia 'produces' sia
    'PRODUCES'.

    `direction`: 'out' segue gli archi uscenti (`from_type`/`from_key`
    combaciano), 'in' quelli entranti (`to_type`/`to_key`), 'both' entrambi.
    `as_of` default a oggi. Se `as_of` è esplicito e **nel passato**
    (`as_of < oggi` — un `as_of` futuro è la normale interrogazione
    dell'orizzonte di piano e non solleva nulla) e `rel_type` è uno dei
    tipi derivati da `item_link` (produces/aggregates/splits/
    dependent_demand) **oppure `rel_type=None`**, solleva
    `GraphSnapshotLimitationError` invece di restituire silenziosamente
    `[]` o un sottoinsieme parziale — vedi punto 2 del docstring di modulo.
    Per la storia time-phased di quelle relazioni usa
    `resolve_manufacturing_items()`; per una query storica sui soli tipi
    strutturali, passa quel `rel_type` esplicitamente.
    """
    if direction not in ("out", "in", "both"):
        raise ValueError(f"direction sconosciuta: {direction!r} (attesa 'out'/'in'/'both')")

    if rel_type is not None:
        rel_type = rel_type.upper()

    as_of_explicit = as_of is not None
    as_of = as_of or dt.date.today()
    is_historical = as_of_explicit and as_of < dt.date.today()

    if is_historical and (rel_type is None or rel_type in _ITEM_LINK_SNAPSHOT_REL_TYPES):
        reason = (
            f"rel_type={rel_type!r} è derivato da item_link"
            if rel_type is not None
            else "rel_type=None potrebbe includere relazioni derivate da item_link"
        )
        raise GraphSnapshotLimitationError(
            f"edge materializza solo l'ultimo periodo noto per le relazioni item->item "
            f"({reason}): non può rispondere per as_of={as_of} nel passato. Usa "
            "resolve_manufacturing_items() per la storia time-phased, oppure passa "
            "esplicitamente un rel_type strutturale (BELONGS_TO/TARGETS/INFLUENCES/"
            "CONSTRAINS) per una query storica sicura."
        )

    validity = _validity_clause()
    queries: list[tuple[str, list]] = []
    if direction in ("out", "both"):
        sql = f"SELECT {_EDGE_COLUMNS} FROM edge WHERE from_type = ? AND from_key = ? AND {validity}"
        params: list = [node_type, node_key, as_of, as_of]
        if rel_type is not None:
            sql += " AND rel_type = ?"
            params.append(rel_type)
        queries.append((sql, params))
    if direction in ("in", "both"):
        sql = f"SELECT {_EDGE_COLUMNS} FROM edge WHERE to_type = ? AND to_key = ? AND {validity}"
        params = [node_type, node_key, as_of, as_of]
        if rel_type is not None:
            sql += " AND rel_type = ?"
            params.append(rel_type)
        queries.append((sql, params))

    rows = []
    for sql, params in queries:
        rows.extend(con.execute(sql, params).fetchall())
    return [_parse_edge(r) for r in rows]


@dataclass(frozen=True)
class ItemIdentity:
    """Le identità di un item valide a una data (`item_identifier`): può
    portare più `id_type` contemporaneamente (element_name + caption +
    sap_material) — è ciò che chiude il caption drift, non un solo nome."""

    item_key: int
    identifiers: dict[str, str]


def resolve_identity(con, item_key: int, as_of: dt.date | None = None) -> ItemIdentity:
    as_of = as_of or dt.date.today()
    rows = con.execute(
        f"SELECT id_type, value FROM item_identifier WHERE item_key = ? AND {_validity_clause()}",
        [item_key, as_of, as_of],
    ).fetchall()
    return ItemIdentity(item_key=item_key, identifiers={r[0]: r[1] for r in rows})


@dataclass(frozen=True)
class ManufacturingRealisation:
    """Una riga `item_link` risolta: a quale item manifatturiero
    (`to_item`) l'item di vendita si realizza, con quota/fonte/offset presi
    dal dato (non da una regola in codice), il cluster (`item.
    manufacturing_category`, i "Cluster 10-15/31-33/38" del vault) e
    l'identità corrente dell'item manifatturiero."""

    to_item: int
    link_type: str
    period: dt.date
    quota: float
    quota_source: str
    quota_window_months: int | None
    offset_months: int
    manufacturing_category: str | None
    identity: ItemIdentity


def resolve_manufacturing_items(
    con, product_key: int, as_of: dt.date | None = None
) -> list[ManufacturingRealisation]:
    """Risolve un item lato vendita (`item.role = 'planning_model'`) agli
    item manifatturieri che lo realizzano, camminando `item_link` per
    'produces'/'aggregates'/'splits' (F7 — non 'dependent_demand', che è la
    domanda del semilavorato *dal lato manifatturiero*, un salto successivo
    nella rete, non parte della risoluzione vendita->produzione).

    `item_link` è time-phased per `period` entro ciascun `(from_item,
    link_type)`: si individua il `period` più recente `<= as_of` **per
    quella coppia** (non per singolo `to_item` — farlo per singolo `to_item`
    farebbe sopravvivere un target rimosso dal mix più recente, rompendo
    l'invariante "le quote di un `(from_item, link_type, period)` sommano a
    100" che `db/build_db.py` verifica sul seed), poi si ritornano **tutte**
    le righe di quel periodo. Rispetta anche `valid_from`/`valid_to` di
    `item_link` (i legami possono essere chiusi) e di `item_identifier`
    (l'identità del target è quella valida alla stessa data `as_of`) — le
    due validità sono indipendenti e vanno entrambe onorate.

    Solleva `KeyError` se `product_key` non esiste, `ValueError` se esiste
    ma non è un planning model (l'errore più comune: passare per sbaglio una
    manufacturing key).
    """
    as_of = as_of or dt.date.today()

    role_row = con.execute("SELECT role FROM item WHERE item_key = ?", [product_key]).fetchone()
    if role_row is None:
        raise KeyError(f"item_key sconosciuto: {product_key}")
    if role_row[0] != "planning_model":
        raise ValueError(
            f"item_key {product_key} ha role={role_row[0]!r}, atteso 'planning_model'"
        )

    placeholders = ", ".join("?" for _ in _MANUFACTURING_LINK_TYPES)
    sql = f"""
        WITH latest AS (
            SELECT link_type, MAX(period) AS period
            FROM item_link
            WHERE from_item = ?
              AND link_type IN ({placeholders})
              AND period <= ?
              AND {_validity_clause()}
            GROUP BY link_type
        )
        SELECT il.to_item, il.link_type, il.period, il.quota_pct, il.quota_source,
               il.quota_window_months, il.offset_months, i.manufacturing_category
        FROM item_link il
        JOIN latest l ON il.link_type = l.link_type AND il.period = l.period
        LEFT JOIN item i ON i.item_key = il.to_item
        WHERE il.from_item = ?
          AND {_validity_clause('il')}
        ORDER BY il.link_type, il.to_item
    """
    params = [
        product_key, *_MANUFACTURING_LINK_TYPES, as_of, as_of, as_of,  # CTE
        product_key, as_of, as_of,  # query esterna
    ]
    rows = con.execute(sql, params).fetchall()
    return [
        ManufacturingRealisation(
            to_item=r[0], link_type=r[1], period=r[2], quota=float(r[3]),
            quota_source=r[4], quota_window_months=r[5], offset_months=r[6],
            manufacturing_category=r[7],
            identity=resolve_identity(con, r[0], as_of),
        )
        for r in rows
    ]
