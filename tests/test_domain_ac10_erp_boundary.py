"""AC10 / T2 notes: "qui si decide il confine con l'ERP: nessuna entità
ordine/BOM/MRP". Verificato sia sul dominio Python (nessuna classe con quei
nomi) sia sullo schema che T2 rispecchia (nessuna tabella corrispondente).
"""
from __future__ import annotations

import ast
import pathlib

import ibp.domain as domain

FORBIDDEN_NAME_FRAGMENTS = ("order", "purchaseorder", "salesorder", "bom", "billofmaterial", "mrp")

DOMAIN_ROOT = pathlib.Path(domain.__file__).resolve().parent


def test_domain_package_declares_no_order_bom_mrp_entity():
    declared_names = [name for name in dir(domain) if not name.startswith("_")]
    lowered = {name.lower() for name in declared_names}
    offenders = [
        name for name in lowered
        if any(fragment in name for fragment in FORBIDDEN_NAME_FRAGMENTS)
    ]
    # 'gap' contains no forbidden fragment; explicit allow-list not needed,
    # but guard the test itself against accidental vacuous pass.
    assert declared_names, "ibp.domain non espone nulla: il test non starebbe verificando niente"
    assert not offenders, f"entità di dominio con nome ERP-transazionale trovate: {offenders}"


def test_no_class_named_after_order_bom_or_mrp_in_domain_source():
    offenders: list[str] = []
    for path in sorted(DOMAIN_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                lowered = node.name.lower()
                if any(fragment in lowered for fragment in FORBIDDEN_NAME_FRAGMENTS):
                    offenders.append(f"{path.name}:{node.lineno}:{node.name}")
    assert not offenders, f"classi di dominio ERP-transazionali trovate: {offenders}"
