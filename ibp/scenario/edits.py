"""Scritture sparse: ogni scrittura produce **sempre** una riga append-only
in `edits` (il log, mai mutato né cancellato) e aggiorna (insert-or-update)
la riga corrispondente in `overlay` (la cache del valore corrente risolto
per quella cella — coerente con il commento di schema "Cache derivata dal
log"). Le tre operazioni pubbliche (`set_cell`/`increment_cell`/
`delete_cell`) sono tutte `op` diverse sullo stesso percorso interno.

Un edit su uno scenario `Evaluated` lo rimette in `Draft` (vedi
`ibp.domain.scenario`, commento di modulo: "un nuovo edit dopo la
valutazione lo rimette in lavorazione"). Uno scenario `Promoted`/
`Discarded` è terminale: la scrittura è rifiutata, non silenziosamente
accettata.
"""
from __future__ import annotations

import datetime as dt
import json

from .errors import CellVersionMismatchError, ScenarioWriteRejectedError
from .models import CellKey, ResolvedCell
from .overlay import load_scenario, resolve_cell as _resolve_cell


def resolve_cell(con, ref: int | str, cell: CellKey) -> ResolvedCell:
    """Ri-esportata da `overlay.py`: lettura, non scrittura — punto
    d'ingresso pubblico unico per risolvere una cella su un `ref`
    (versione o scenario)."""
    return _resolve_cell(con, ref, cell)


def _next_id(con, table: str, pk_column: str) -> int:
    row = con.execute(f"SELECT COALESCE(MAX({pk_column}), 0) + 1 FROM {table}").fetchone()
    return int(row[0])


def _cell_key_json(cell: CellKey) -> str:
    return json.dumps(
        {
            "version_key": cell.version_key,
            "product_key": cell.product_key,
            "plant_key": cell.plant_key,
            "date_key": cell.date_key,
            "measure_key": cell.measure_key,
        },
        sort_keys=True,
    )


def _writable_scenario(con, scenario_id: str):
    """Carica lo scenario, rifiuta la scrittura se in stato terminale, e
    riporta a `Draft` uno scenario `Evaluated` (persistendo la transizione)
    — coerente con la macchina a stati di `ibp.domain.scenario`."""
    scenario = load_scenario(con, scenario_id)
    if scenario.state in ("Promoted", "Discarded"):
        raise ScenarioWriteRejectedError(scenario_id, scenario.state)
    if scenario.state == "Evaluated":
        scenario = scenario.transition_to("Draft")
        con.execute(
            "UPDATE scenario SET state = ? WHERE scenario_id = ?",
            [scenario.state, scenario.scenario_id],
        )
    return scenario


def _upsert_overlay(con, scenario_id: str, cell: CellKey, value: float | None, is_deleted: bool) -> None:
    existing = con.execute(
        "SELECT overlay_id FROM overlay WHERE scenario_id = ? AND version_key = ? "
        "AND date_key = ? AND measure_key = ? "
        "AND product_key IS NOT DISTINCT FROM ? AND plant_key IS NOT DISTINCT FROM ?",
        [scenario_id, cell.version_key, cell.date_key, cell.measure_key, cell.product_key, cell.plant_key],
    ).fetchone()
    if existing is None:
        overlay_id = _next_id(con, "overlay", "overlay_id")
        con.execute(
            "INSERT INTO overlay (overlay_id, scenario_id, version_key, product_key, plant_key, "
            "date_key, measure_key, value, is_deleted) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                overlay_id, scenario_id, cell.version_key, cell.product_key, cell.plant_key,
                cell.date_key, cell.measure_key, value, is_deleted,
            ],
        )
    else:
        con.execute(
            "UPDATE overlay SET value = ?, is_deleted = ? WHERE overlay_id = ?",
            [value, is_deleted, existing[0]],
        )


def _apply_edit(
    con, scenario_id: str, cell: CellKey, op: str, amount: float | None, user: str, ts: dt.datetime | None,
) -> None:
    ts = ts or dt.datetime.now()
    con.execute("BEGIN TRANSACTION")
    try:
        scenario = _writable_scenario(con, scenario_id)
        if cell.version_key != scenario.base_version_key:
            # AC15: una cella scritta sotto un version_key diverso dalla
            # base dello scenario non sarebbe mai risolta in modo coerente
            # da nessuna lettura del suo stack — rifiutata alla scrittura,
            # non lasciata come riga di overlay silenziosamente orfana.
            raise CellVersionMismatchError(scenario_id, scenario.base_version_key, cell.version_key)
        current = _resolve_cell(con, scenario_id, cell)
        old_value = None if current.is_deleted else current.value

        if op == "set":
            new_value: float | None = amount
            is_deleted = False
        elif op == "increment":
            base = old_value if old_value is not None else 0.0
            new_value = base + (amount or 0.0)
            is_deleted = False
        elif op == "delete":
            new_value = None
            is_deleted = True
        else:
            raise ValueError(f"op sconosciuto: {op!r} (atteso 'set'/'increment'/'delete')")

        edit_id = _next_id(con, "edits", "edit_id")
        con.execute(
            'INSERT INTO edits (edit_id, scenario_id, ts, "user", cell_key_json, measure_key, '
            "old_value, new_value, op) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                edit_id, scenario_id, ts, user, _cell_key_json(cell), cell.measure_key,
                old_value, new_value, op,
            ],
        )
        _upsert_overlay(con, scenario_id, cell, new_value, is_deleted)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


def set_cell(con, scenario_id: str, cell: CellKey, value: float, *, user: str, ts: dt.datetime | None = None) -> None:
    """Scrive `value` come valore assoluto della cella (op `set`)."""
    _apply_edit(con, scenario_id, cell, "set", value, user, ts)


def increment_cell(con, scenario_id: str, cell: CellKey, delta: float, *, user: str, ts: dt.datetime | None = None) -> None:
    """Somma `delta` al valore corrente risolto della cella (base o overlay
    di uno scenario antenato); una cella mai scritta o cancellata parte da
    `0.0` (op `increment`)."""
    _apply_edit(con, scenario_id, cell, "increment", delta, user, ts)


def delete_cell(con, scenario_id: str, cell: CellKey, *, user: str, ts: dt.datetime | None = None) -> None:
    """Tombstone esplicito (AC14): `is_deleted=TRUE`, `value=NULL`. La
    cella non ricompare più dal base per questo scenario (né per un
    discendente che non la riscriva a sua volta)."""
    _apply_edit(con, scenario_id, cell, "delete", None, user, ts)
