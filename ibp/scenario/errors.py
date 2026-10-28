"""Eccezioni di `ibp.scenario`. Uno stesso principio di `ibp.domain.errors`:
un guasto riconoscibile per tipo, mai un `ValueError` generico né, peggio,
un fallimento silenzioso (branch/edit/compare/promote non devono mai
tornare un risultato plausibile ma sbagliato).

Le transizioni di stato dello scenario (Draft/Evaluated/Promoted/Discarded)
restano di competenza di `ibp.domain.scenario.SCENARIO_STATE`: le eccezioni
che ne derivano (`InvalidTransitionError`, `UnknownStateError`) sono quelle
di `ibp.domain.errors`, non duplicate qui — vedi `branch.py`/`promote.py`.
"""
from __future__ import annotations


class ScenarioError(Exception):
    """Base per tutte le eccezioni di `ibp.scenario`."""


class UnknownVersionError(ScenarioError):
    """`version_key` citato (come base di un branch o come `ref` di
    `compare`) non esiste in `DVERSIONS`."""

    def __init__(self, version_key: int):
        super().__init__(f"version_key sconosciuto in DVERSIONS: {version_key}")
        self.version_key = version_key


class UnknownScenarioError(ScenarioError):
    """`scenario_id` citato non esiste in `scenario`."""

    def __init__(self, scenario_id: str):
        super().__init__(f"scenario_id sconosciuto: {scenario_id!r}")
        self.scenario_id = scenario_id


class InvalidCellKeyError(ScenarioError):
    """Una cella di scenario è identificata da `product_key` (lato demand)
    **oppure** `plant_key` (lato ops), mai entrambi o nessuno dei due — è la
    stessa distinzione che `overlay`/`TSOP_DEMAND`/`TSOP_OPS` fanno nello
    schema (`db/schema.sql`, commento su `item`)."""


class ScenarioWriteRejectedError(ScenarioError):
    """Scrittura rifiutata su uno scenario in uno stato terminale
    (`Promoted`/`Discarded`, vedi `ibp.domain.scenario.SCENARIO_TRANSITIONS`
    — nessuna transizione uscente): una volta promosso o scartato, uno
    scenario non si riapre."""

    def __init__(self, scenario_id: str, state: str):
        super().__init__(
            f"scenario {scenario_id!r} è {state} (stato terminale): scrittura rifiutata"
        )
        self.scenario_id = scenario_id
        self.state = state


class DuplicateVersionError(ScenarioError):
    """`promote()` rifiuta di scrivere su un'istanza `DVERSIONS` già
    esistente (stesso `version_name`): la promozione crea sempre una nuova
    istanza, non sovrascrive mai quella corrente."""

    def __init__(self, version_name: str):
        super().__init__(
            f"esiste già un'istanza DVERSIONS con nome {version_name!r}: "
            "promote() non scrive mai su un'istanza esistente"
        )
        self.version_name = version_name


class PromotionConflictError(ScenarioError):
    """AC16: la base (`scenario.base_version_key`) si è mossa dal branch
    time — il contenuto corrente di `TSOP_DEMAND`/`TSOP_OPS` per quella
    `version_key` non corrisponde più a `base_snapshot_id` registrato al
    momento del branch. La promozione si rifiuta invece di sovrascrivere
    silenziosamente: il chiamante deve ribasare lo scenario (fuori scope di
    questo modulo) o accettare esplicitamente il conflitto altrove."""

    def __init__(self, scenario_id: str, expected_snapshot: str, actual_snapshot: str):
        super().__init__(
            f"scenario {scenario_id!r}: la base si è mossa dal branch time "
            f"(snapshot atteso {expected_snapshot!r}, attuale {actual_snapshot!r}) — "
            "promozione rifiutata"
        )
        self.scenario_id = scenario_id
        self.expected_snapshot = expected_snapshot
        self.actual_snapshot = actual_snapshot


class UnknownMeasureError(ScenarioError):
    """`measure_key` di una `CellKey` non esiste nel catalogo atteso
    (`DMEASURE_DEMAND` lato demand, `DMEASURE_OPS` lato ops — le due
    tabelle hanno chiavi indipendenti, lo stesso intero non è la stessa
    misura sui due lati)."""

    def __init__(self, side: str, measure_key: int):
        super().__init__(f"measure_key sconosciuto nel catalogo {side}: {measure_key}")
        self.side = side
        self.measure_key = measure_key


class NonAdditiveMeasureError(ScenarioError):
    """AC12: min/max/ratio/avg/count si ricalcolano sul gruppo, non si
    sommano né si delta-aggiornano — è `ibp.engine` (T3) a possedere quella
    regola, non `ibp.scenario`. `overlay` non traccia le coordinate
    (`division_key`/`region`/`manufact_key`) su cui una cella scenario può
    coprire più righe base: sommarle sarebbe l'unica operazione che questo
    modulo sa fare, ed è quella sbagliata per una misura non additiva
    (`CAPACITY_UTIL` sommato non è una media, `SLOTS_AVAILABLE` sommato non
    è un massimo). Rifiutata esplicitamente invece di restituire un numero
    plausibile ma privo di senso."""

    def __init__(self, measure_key: int, agg_method: str):
        super().__init__(
            f"measure_key={measure_key} ha agg_method={agg_method!r} (non 'sum'): "
            "ibp.scenario non combina celle non additive sulle coordinate che overlay "
            "non traccia — operazione rifiutata"
        )
        self.measure_key = measure_key
        self.agg_method = agg_method


class MismatchedBaseVersionError(ScenarioError):
    """AC15: uno scenario annidato (`parent_scenario_id`) deve condividere
    lo stesso `base_version_key` dell'antenato. Senza questo vincolo, la
    catena di overlay di `materialize_ref()`/`resolve_cell()` mischierebbe
    celle scritte sotto basi diverse in un unico risultato plausibile ma
    calcolato sulla base sbagliata — l'esatta falla di isolamento che AC15
    vieta."""

    def __init__(self, parent_scenario_id: str, parent_base_version_key: int, base_version_key: int):
        super().__init__(
            f"parent_scenario_id={parent_scenario_id!r} ha base_version_key="
            f"{parent_base_version_key}, diverso da base_version_key={base_version_key} "
            "richiesto per il nuovo scenario: uno scenario annidato deve condividere "
            "la base del proprio antenato"
        )
        self.parent_scenario_id = parent_scenario_id
        self.parent_base_version_key = parent_base_version_key
        self.base_version_key = base_version_key


class CellVersionMismatchError(ScenarioError):
    """`cell.version_key` deve corrispondere a `scenario.base_version_key`:
    scrivere una cella con un `version_key` diverso da quello della base
    dello scenario produrrebbe una riga di `overlay` che nessuna lettura
    dello stack di quello scenario risolverebbe mai in modo coerente
    (AC15) — rifiutata alla scrittura, non lasciata come dato silenzioso."""

    def __init__(self, scenario_id: str, scenario_base_version_key: int, cell_version_key: int):
        super().__init__(
            f"scenario {scenario_id!r} ha base_version_key={scenario_base_version_key}, "
            f"diverso da version_key={cell_version_key} della cella scritta: scrittura rifiutata"
        )
        self.scenario_id = scenario_id
        self.scenario_base_version_key = scenario_base_version_key
        self.cell_version_key = cell_version_key


class SideMismatchError(ScenarioError):
    """`promote()` rifiuta un `side` incoerente con `DVERSIONS.side` della
    base dello scenario: un'istanza `SOP_..._SUPPLY_*` che contiene righe
    `TSOP_DEMAND` è un nome che mente rispetto al dato, ed è esattamente
    la stringa che le misure DAX di Power BI ricostruiscono per decidere
    cosa leggere."""

    def __init__(self, base_version_key: int, base_side: str, requested_side: str):
        super().__init__(
            f"base_version_key={base_version_key} ha side={base_side!r} in DVERSIONS, "
            f"diverso da side={requested_side!r} richiesto per la promozione: rifiutata"
        )
        self.base_version_key = base_version_key
        self.base_side = base_side
        self.requested_side = requested_side


class UnmaterializableCellError(ScenarioError):
    """Una riga di `overlay` non ha alcuna riga base corrispondente
    (stesso `product_key`/`plant_key` + `date_key` + `measure_key`) in
    `TSOP_DEMAND`/`TSOP_OPS` per `base_version_key`. `overlay` non porta
    `division_key`/`region`/`manufact_key` (la sua grana è più larga di
    quella dei fatti, per costruzione dello schema, T1): senza una riga
    base da cui ereditare quelle coordinate, `promote()` non può inventare
    una riga piena — la rifiuta esplicitamente invece di indovinare."""

    def __init__(self, cell_key: object):
        super().__init__(
            f"cella di overlay senza riga base corrispondente, non materializzabile "
            f"in una nuova istanza DVERSIONS: {cell_key!r}"
        )
        self.cell_key = cell_key
