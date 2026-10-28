"""Valori di dominio di `ibp.scenario`. `Scenario` stesso resta quello di
`ibp.domain.scenario` (T2) — qui non lo si ridichiara, lo si ri-esporta.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..domain.scenario import SCENARIO_STATE, SCENARIO_TRANSITIONS, Scenario

__all__ = [
    "SCENARIO_STATE",
    "SCENARIO_TRANSITIONS",
    "Scenario",
    "CellKey",
    "ResolvedCell",
    "CompareRow",
    "ScenarioStack",
    "PromotionResult",
]


@dataclass(frozen=True)
class CellKey:
    """Identifica una cella allo stesso livello di grana di `overlay`
    (`db/schema.sql`): `(version_key, date_key, measure_key, product_key |
    plant_key)`. Esattamente uno fra `product_key` (lato demand) e
    `plant_key` (lato ops) deve essere valorizzato — mai entrambi, mai
    nessuno dei due: è la stessa regola che il commento di `overlay` rende
    esplicita ("product_key valorizzato lato demand, plant_key lato ops").

    Nota di grana (da dichiarare, non da nascondere): `overlay` non porta
    `division_key`/`region` (lato demand) né `manufact_key`/`division_key`/
    `region` (lato ops) — è più larga della grana piena di `TSOP_DEMAND`/
    `TSOP_OPS`. La lettura di una cella scenario aggrega (somma) su quelle
    coordinate quando risolve dal base; vedi `overlay.py`.
    """

    version_key: int
    date_key: int
    measure_key: int
    product_key: int | None = None
    plant_key: int | None = None

    def __post_init__(self) -> None:
        from .errors import InvalidCellKeyError

        if (self.product_key is None) == (self.plant_key is None):
            raise InvalidCellKeyError(
                "CellKey richiede esattamente uno fra product_key (lato demand) e "
                f"plant_key (lato ops): product_key={self.product_key!r}, "
                f"plant_key={self.plant_key!r}"
            )

    @property
    def side(self) -> str:
        return "demand" if self.product_key is not None else "ops"

    def as_slice(self) -> tuple:
        """Chiave di slice indipendente dalla versione — usata da `compare()`
        per confrontare celle fra `ref` diversi (versioni e/o scenari)."""
        return (self.product_key, self.plant_key, self.date_key, self.measure_key)


@dataclass(frozen=True)
class ResolvedCell:
    """Risultato di `resolve_cell()`: il valore di una cella dopo aver
    risolto l'overlay sopra il base (o solo il base, per un `ref` versione
    pura). `is_deleted=True` con `value=None` è l'unica rappresentazione del
    tombstone (AC14) — mai `value=None` da solo per dire "cancellato"."""

    cell: CellKey
    value: float | None
    is_deleted: bool
    source: str  # 'overlay' | 'base' | 'none'


@dataclass(frozen=True)
class CompareRow:
    """Una riga del delta di `compare(ref_a, ref_b)`: valori assoluti
    (`float`, mai `Decimal`, coerente con il contratto del semantic layer)
    su entrambi i lati e la loro differenza. Una cella assente in un lato
    (mai scritta, o cancellata da un tombstone) vale `0.0` per il confronto
    — la stessa semantica additiva del cubo."""

    product_key: int | None
    plant_key: int | None
    date_key: int
    measure_key: int
    value_a: float
    value_b: float
    delta: float


@dataclass(frozen=True)
class ScenarioStack:
    """La chiave di isolamento (AC15): `base_version_key` più la catena
    **ordinata radice -> foglia** degli `scenario_id` annidati (`()` per un
    `ref` che è una versione pura, senza scenario). `cache_key()` è quello
    che qualunque cache di aggregati a valle (T3, l'engine) deve includere
    per intero nella propria chiave — mai solo lo scenario foglia, altrimenti
    due scenari annidati con la stessa foglia ma antenati diversi
    collassano sulla stessa voce di cache, servendo un aggregato calcolato
    sotto lo scenario sbagliato."""

    base_version_key: int
    chain: tuple[str, ...]

    def cache_key(self) -> tuple[int, tuple[str, ...]]:
        return (self.base_version_key, self.chain)


@dataclass(frozen=True)
class PromotionResult:
    """Esito di `promote()`: la nuova istanza `DVERSIONS` materializzata e
    lo scenario aggiornato (stato `Promoted`).

    `base_verified` (AC16): `True` se `base_snapshot_id` era nel formato
    prodotto da `branch()` (`SNAP_{version_key}_{sha256}`) e il controllo
    "la base non si è mossa" è stato effettivamente eseguito; `False` se
    `base_snapshot_id` è in un formato non riconosciuto (tipicamente uno
    scenario del seed, pre-T4: `db/seed/scenario.py` scrive ancora
    `SNAP_{version_name}_{iso_ts}`, un'etichetta non un'impronta di
    contenuto) e la promozione è quindi passata **senza verifica**, non
    perché la base sia stata confermata immobile. Un chiamante non deve
    dover ri-analizzare `base_snapshot_id` con la regex privata di
    `promote.py` per saperlo — è per questo che il campo esiste."""

    version_key: int
    version_name: str
    scenario: Scenario
    base_verified: bool
