"""AC2 come test reale: `Max Slots`, il fattore di granularità e le soglie
di capacità sono master data su `DPLANT`, mai literal nel codice di
calcolo. Aggiungere un plant deve cambiare ciò che il registry riporta
*senza alcuna modifica a Python*.
"""
from __future__ import annotations

import ast
import pathlib

from ibp.semantic.registry import SemanticRegistry

# Round-1 critic finding: uno scan su `int` puro, su tutto `ibp/`, è sia
# troppo permissivo (`30.0`, `"30"`, `29 + 1` lo eludono banalmente) sia
# troppo aggressivo (falsi positivi certi su T10: HTTP `500`, un qualunque
# `8` incidentale altrove nel dominio che non ha nulla a che fare con la
# capacità). AC2 riguarda il codice che *calcola* con la capacità.
#
# Round-2 critic non-blocking note: scoparlo alla sola `ibp/semantic/`
# (che oggi non calcola nulla — T2 dichiara, T3 esegue) significa che un
# `30` letterale in `ibp/engine/` (in scrittura per T3) o in un futuro
# `ibp/capacity/` passerebbe inosservato finché nessuno ricorda di allargare
# la lista. La lista di root è quindi dichiarata qui per tutto il codice di
# calcolo *previsto* dal design (D7, plan.md) e filtrata per esistenza a
# runtime: scansiona ciò che esiste oggi, e comincia a mordere nel momento
# stesso in cui `ibp/engine/`/`ibp/capacity/` compaiono, senza dover
# ritoccare questo file.
_IBP_ROOT = pathlib.Path(__file__).resolve().parents[1] / "ibp"
_CALCULATION_ROOT_CANDIDATES = (
    _IBP_ROOT / "semantic",  # T2: registry misure/dimensioni (oggi)
    _IBP_ROOT / "engine",    # T3: recalc/allocation/financialization (in scrittura)
    _IBP_ROOT / "capacity",  # eventuale modulo dedicato di capacità (non ancora nel design)
)


def _existing_calculation_roots() -> list[pathlib.Path]:
    return [root for root in _CALCULATION_ROOT_CANDIDATES if root.is_dir()]

# AC2 (docs/01-plan-m1.md): "Un test fallisce se 30, 8 o 500 compaiono nel
# codice di calcolo." — i valori di capacità seedati (Westvale 30, isole 8,
# soglia gap <500).
FORBIDDEN_CAPACITY_NUMBERS = {30, 8, 500}
FORBIDDEN_CAPACITY_STRINGS = {"30", "8", "500"}


def _fold_numeric(node: ast.AST) -> float | int | None:
    """Valore numerico di un nodo se è un letterale, o una combinazione
    aritmetica *immediata* di letterali (`29 + 1`, `-30`, `4 * 2`): copre il
    modo più ovvio di eludere uno scan che guarda solo `ast.Constant`."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _fold_numeric(node.operand)
        if operand is None:
            return None
        return -operand if isinstance(node.op, ast.USub) else operand
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        left = _fold_numeric(node.left)
        right = _fold_numeric(node.right)
        if left is None or right is None:
            return None
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        return left / right if right else None
    return None


def test_known_plants_report_capacity_from_master_data(registry: SemanticRegistry):
    plants = {p.plant_code: p for p in registry.plants()}
    assert plants["FR-WESTVALE"].max_slots == 30
    assert plants["FR-WESTVALE"].layout_type == "flow_line"
    assert plants["DE-GANDERKESEE"].max_slots == 8
    assert plants["DE-GANDERKESEE"].layout_type == "assembly_island"


def test_plant_capacity_single_lookup_matches_list(registry: SemanticRegistry):
    single = registry.plant_capacity(1)
    assert single.plant_code == "FR-WESTVALE"
    assert single.max_slots == 30


def test_unknown_plant_key_raises_key_error(registry: SemanticRegistry):
    import pytest

    with pytest.raises(KeyError):
        registry.plant_capacity(999_999)


def test_adding_a_plant_row_changes_registry_output_with_no_code_change(writable_db_copy):
    """Il cuore di AC2: la stessa classe Python, senza toccare un rigo di
    `ibp/semantic`, deve riflettere un nuovo plant appena inserito come dato."""
    con = writable_db_copy
    new_key = con.execute("SELECT MAX(plant_key) + 1 FROM DPLANT").fetchone()[0]

    registry = SemanticRegistry(con)
    codes_before = {p.plant_code for p in registry.plants()}
    assert "ZZ-TESTPLANT" not in codes_before

    con.execute(
        """
        INSERT INTO DPLANT
            (plant_key, plant_code, plant_name, plant_activity, plant_region,
             plant_type, layout_type, max_slots, slot_granularity_factor)
        VALUES (?, 'ZZ-TESTPLANT', 'Test Plant', 'Assembly', 'EMEA',
                'internal', 'flow_line', 77, 9.5)
        """,
        [new_key],
    )

    codes_after = {p.plant_code for p in registry.plants()}
    assert "ZZ-TESTPLANT" in codes_after

    added = registry.plant_capacity(new_key)
    assert added.max_slots == 77
    assert float(added.slot_granularity_factor) == 9.5
    assert added.layout_type == "flow_line"


def test_no_capacity_literals_in_calculation_code():
    """Scansione AST (non testuale) di ogni root di `_CALCULATION_ROOT_CANDIDATES`
    che esiste oggi (`ibp/semantic/` di sicuro; `ibp/engine/`/`ibp/capacity/`
    quando compariranno) — non di tutto `ibp/`, per evitare falsi positivi su
    moduli che non calcolano nulla con la capacità (es. HTTP `500` in un
    futuro `ibp/api/`).

    Un nodo fallisce se è, o si riduce per aritmetica immediata a, uno dei
    valori proibiti in forma `int` **o** `float` (elude `30.0`), oppure se
    è una stringa che coincide esattamente con la forma testuale del
    valore proibito (elude `"30"`). Lo stesso valore dentro una stringa di
    docstring/commento più lunga (es. "il caso 30, 8, 4.0") non conta: non
    è una stringa *uguale* a "30"."""
    roots = _existing_calculation_roots()
    assert roots, "nessuna root di calcolo trovata: ibp/semantic/ dovrebbe sempre esistere in T2+"

    violations: list[tuple[str, int, object]] = []
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                numeric = _fold_numeric(node)
                if numeric is not None and numeric in FORBIDDEN_CAPACITY_NUMBERS:
                    violations.append((str(path.relative_to(_IBP_ROOT.parent)), node.lineno, numeric))
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if node.value.strip() in FORBIDDEN_CAPACITY_STRINGS:
                        violations.append((str(path.relative_to(_IBP_ROOT.parent)), node.lineno, node.value))
    assert not violations, f"literal di capacità trovati nel codice di calcolo: {violations}"


def test_calculation_root_candidates_are_existence_tolerant():
    """Non-vacuità della tolleranza: `ibp/engine/`/`ibp/capacity/` non
    esistono ancora in T2 e non devono far fallire la raccolta dei test né
    la scansione sopra (che deve limitarsi a ciò che esiste)."""
    engine_root = _IBP_ROOT / "engine"
    capacity_root = _IBP_ROOT / "capacity"
    # Quando questo test inizia a fallire perché una delle due esiste, è il
    # segnale che lo scan sopra ha iniziato a coprirla per davvero.
    existing = _existing_calculation_roots()
    assert (_IBP_ROOT / "semantic") in existing
    if not engine_root.is_dir():
        assert engine_root not in existing
    if not capacity_root.is_dir():
        assert capacity_root not in existing


def test_capacity_literal_scan_actually_detects_evasive_forms():
    """Controllo di non-vacuità del test sopra: verifica che lo scanner
    stesso riconosca le forme che il round 1 non catturava (float, stringa,
    aritmetica immediata), su un frammento sintetico — non sul sorgente
    reale, che non deve contenerle."""
    sample = "x = 30.0\ny = '30'\nz = 29 + 1\n"
    tree = ast.parse(sample)
    found: set[object] = set()
    for node in ast.walk(tree):
        numeric = _fold_numeric(node)
        if numeric is not None and numeric in FORBIDDEN_CAPACITY_NUMBERS:
            found.add(numeric)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.strip() in FORBIDDEN_CAPACITY_STRINGS:
                found.add(node.value)
    assert 30 in found  # x = 30.0 (30.0 == 30, la stessa entry copre anche z = 29 + 1)
    assert "30" in found  # y = '30'
    assert len(found) == 2
