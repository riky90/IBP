"""Semantic layer (A4/D1, T2): registry dimensioni + misure (catalogo e DAG
dichiarato) e overlay a grafo sopra il mirror dEPM. Nessuna connessione
DuckDB propria: ogni funzione/metodo qui riceve una connessione aperta da
`ibp.db`.
"""
from __future__ import annotations

from . import dimensions, graph, measures
from .dimensions import Dimension, DimensionAttribute, ItemFactors, PlantCapacity
from .graph import Edge, GraphSnapshotLimitationError, ItemIdentity, ManufacturingRealisation
from .measures import MeasureDef, MeasureNode
from .registry import SemanticRegistry

__all__ = [
    "dimensions",
    "graph",
    "measures",
    "Dimension",
    "DimensionAttribute",
    "ItemFactors",
    "PlantCapacity",
    "Edge",
    "GraphSnapshotLimitationError",
    "ItemIdentity",
    "ManufacturingRealisation",
    "MeasureDef",
    "MeasureNode",
    "SemanticRegistry",
]
