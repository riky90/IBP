"""T2 done_when #5 / plan.md notes: `ibp/db.py` è l'unico punto di apertura
di connessioni DuckDB nel package `ibp`; gli altri moduli ricevono una
connessione, non ne aprono di proprie. Verificato strutturalmente (AST) sul
sorgente, non per ispezione manuale.
"""
from __future__ import annotations

import ast
import pathlib

IBP_ROOT = pathlib.Path(__file__).resolve().parents[1] / "ibp"


def _imports_duckdb(tree: ast.AST) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == "duckdb" for alias in node.names):
                lines.append(node.lineno)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "duckdb":
                lines.append(node.lineno)
    return lines


def test_only_db_module_imports_duckdb():
    offenders: dict[str, list[int]] = {}
    for path in sorted(IBP_ROOT.rglob("*.py")):
        if path.name == "db.py" and path.parent == IBP_ROOT:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        lines = _imports_duckdb(tree)
        if lines:
            offenders[str(path.relative_to(IBP_ROOT.parent))] = lines
    assert not offenders, f"import diretto di duckdb fuori da ibp/db.py: {offenders}"


def test_db_module_itself_does_import_duckdb():
    # controllo di non-vacuità: se questo fallisse il test sopra sarebbe inutile.
    tree = ast.parse((IBP_ROOT / "db.py").read_text(encoding="utf-8"))
    assert _imports_duckdb(tree)


def test_db_module_exposes_connect_and_session():
    from ibp import db as ibp_db

    assert callable(ibp_db.connect)
    assert callable(ibp_db.session)
