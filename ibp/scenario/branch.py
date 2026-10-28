"""Ciclo di vita dello scenario: `branch()` lo crea, `mark_evaluated()` e
`discard()` lo spostano lungo la macchina a stati di `ibp.domain.scenario`
(la stessa, non una seconda dichiarata qui — vedi T2 done_when).

`mark_evaluated()` è il punto d'aggancio (seam) per T3: il motore di
ricalcolo (fuori scope di questo task, in sviluppo concorrente) valuterà lo
scenario e poi chiamerà questa funzione per registrare l'esito nello stato
— T4 non calcola nulla, offre solo la transizione.
"""
from __future__ import annotations

import datetime as dt
import uuid

from ..domain.scenario import Scenario
from .errors import MismatchedBaseVersionError
from .overlay import base_content_digest, load_scenario, version_exists


def _new_scenario_id() -> str:
    """ID opaco, generato senza bisogno di leggere il DB prima (niente
    `MAX(...)+1` in corsa con un altro scrittore) — DuckDB è single-writer
    di processo (README, gotcha A6) ma un ID auto-sufficiente resta più
    semplice da ragionare."""
    return f"SCN-{uuid.uuid4().hex[:12]}"


def branch(
    con,
    *,
    name: str,
    base_version_key: int,
    owner: str,
    parent_scenario_id: str | None = None,
    scenario_id: str | None = None,
    created_at: dt.datetime | None = None,
) -> Scenario:
    """Crea uno scenario come branch su `base_version_key` (una `DVERSIONS`
    esistente). Registra `base_snapshot_id` come impronta di contenuto del
    base **al momento del branch** (`base_content_digest`): è ciò che
    `promote()` ricalcola per rilevare una base mossa (AC16) — non un
    timestamp, un contenuto.

    Non scrive mai un membro `DVERSIONS`: lo scenario nasce come riga di
    `scenario`, non come versione — coerente con la nota portante del task
    (le misure DAX di Power BI ricostruiscono i nomi `DVERSIONS` come
    stringhe; un what-if non ne è mai membro finché non promosso).

    Solleva `UnknownVersionError` se `base_version_key` non esiste,
    `UnknownScenarioError` se `parent_scenario_id` è indicato ma non esiste,
    `MismatchedBaseVersionError` (AC15) se `parent_scenario_id` esiste ma
    ha un `base_version_key` diverso — uno scenario annidato deve
    condividere la base del proprio antenato, altrimenti la catena di
    overlay mischierebbe celle scritte sotto basi diverse (vedi
    `overlay.materialize_ref`).
    """
    version_exists(con, base_version_key)
    if parent_scenario_id is not None:
        parent = load_scenario(con, parent_scenario_id)
        if parent.base_version_key != base_version_key:
            raise MismatchedBaseVersionError(
                parent_scenario_id, parent.base_version_key, base_version_key
            )

    scenario_id = scenario_id or _new_scenario_id()
    created_at = created_at or dt.datetime.now()
    snapshot = base_content_digest(con, base_version_key)
    base_snapshot_id = f"SNAP_{base_version_key}_{snapshot}"

    scenario = Scenario(
        scenario_id=scenario_id,
        name=name,
        base_version_key=base_version_key,
        base_snapshot_id=base_snapshot_id,
        parent_scenario_id=parent_scenario_id,
        owner=owner,
        state="Draft",
        created_at=created_at,
    )

    con.execute("BEGIN TRANSACTION")
    try:
        con.execute(
            "INSERT INTO scenario (scenario_id, name, base_version_key, base_snapshot_id, "
            "parent_scenario_id, owner, state, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                scenario.scenario_id, scenario.name, scenario.base_version_key,
                scenario.base_snapshot_id, scenario.parent_scenario_id, scenario.owner,
                scenario.state, scenario.created_at,
            ],
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return scenario


def _persist_state(con, scenario: Scenario) -> None:
    con.execute(
        "UPDATE scenario SET state = ? WHERE scenario_id = ?",
        [scenario.state, scenario.scenario_id],
    )


def mark_evaluated(con, scenario_id: str) -> Scenario:
    """`Draft -> Evaluated`. Il seam per T3: chiamata dopo che il motore ha
    valutato l'overlay dello scenario contro il DAG di misure. Solleva
    `InvalidTransitionError`/`UnknownStateError` (`ibp.domain.errors`) se lo
    stato corrente non ammette la transizione."""
    scenario = load_scenario(con, scenario_id)
    updated = scenario.transition_to("Evaluated")
    con.execute("BEGIN TRANSACTION")
    try:
        _persist_state(con, updated)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return updated


def discard(con, scenario_id: str) -> Scenario:
    """`Draft|Evaluated -> Discarded`, terminale: lo scenario non si riapre."""
    scenario = load_scenario(con, scenario_id)
    updated = scenario.transition_to("Discarded")
    con.execute("BEGIN TRANSACTION")
    try:
        _persist_state(con, updated)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return updated
