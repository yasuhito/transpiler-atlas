import math
from types import SimpleNamespace

import pytest
from mqt.qcec.pyqcec import Configuration
from mqt.qmap import sc
from qiskit import QuantumCircuit, QuantumRegister, qasm2
from qiskit.quantum_info import Operator

import atlas
from qmap_adapter import SETTINGS, CompilationError, invert_permutation, recipe_metadata


def case(name):
    if name == "multiple-registers":
        qc = QuantumCircuit(QuantumRegister(2, "z"), QuantumRegister(2, "a"))
        qc.h(0)
        qc.cx(0, 3)
        qc.rx(0.31, 1)
        qc.ry(-0.23, 2)
    elif name == "idle-wires":
        qc = QuantumCircuit(5)
        qc.h(4)
        qc.cx(4, 1)
        qc.rx(0.19, 1)
    elif name == "width-one":
        qc = QuantumCircuit(1)
        qc.h(0)
        qc.rz(0.11, 0)
    elif name == "phase":
        qc = QuantumCircuit(2)
        qc.h(0)
        qc.cx(0, 1)
        qc.global_phase = 0.37
    elif name == "idle-routing":
        qc = QuantumCircuit(6)
        qc.h(5)
        qc.cx(5, 1)
        qc.cx(1, 3)
        qc.cx(5, 3)
        qc.cx(3, 1)
    else:
        qc = QuantumCircuit(1)
        qc.global_phase = 0.29
    return qc


@pytest.mark.parametrize(
    "name", ["multiple-registers", "idle-wires", "width-one", "phase", "idle-routing", "empty"]
)
@pytest.mark.parametrize("target", ["line", "all-to-all"])
def test_irregular_inputs_preserve_all_input_states(name, target, bounded_qcec):
    original = case(name)
    before = original.copy()
    native, elapsed, initial, final = atlas.compile_once(
        original, "qmap-sc-heuristic-maponly-v1", target, 7
    )
    assert elapsed > 0
    assert original == before
    assert native.num_qubits == original.num_qubits
    assert not native.ancillas
    atlas.metrics(native, atlas.edges_for(original.num_qubits, target))
    assert sorted(initial) == sorted(final) == list(range(original.num_qubits))
    assert bounded_qcec(original, native, initial, final)["accepted"]


def test_scalar_phase_preserved_exactly_not_only_qcec_global_gauge():
    original = QuantumCircuit(1)
    original.x(0)
    original.global_phase = 0.37
    native, _, _, _ = atlas.compile_once(original, "qmap-sc-heuristic-maponly-v1", "line", 7)
    assert math.isclose(float(native.global_phase), 0.37)
    assert Operator(native) == Operator(original)


def test_all_configuration_properties_explicit_and_metadata_independent():
    properties = {
        key for key, value in vars(sc.Configuration).items() if isinstance(value, property)
    }
    assert properties == set(SETTINGS)
    assert len(SETTINGS) == 30
    metadata = recipe_metadata()
    metadata["pre_mapping_optimizations"] = True
    assert recipe_metadata()["pre_mapping_optimizations"] is False
    assert atlas.configuration_for("qmap-sc-heuristic-maponly-v1")["seed_supported"] is False
    assert Configuration().functionality.trace_threshold == 1e-8
    assert Configuration().functionality.check_approximate_equivalence is False


def test_internal_timeout_is_rejected_before_conversion(monkeypatch):
    monkeypatch.setattr(sc, "map_", lambda *_: (None, SimpleNamespace(timeout=True)))
    with pytest.raises(CompilationError, match="qmap_internal_timeout"):
        atlas.compile_once(case("width-one"), "qmap-sc-heuristic-maponly-v1", "line", 7)


def test_non_self_inverse_permutations_and_corruption():
    assert invert_permutation({0: 1, 1: 2, 2: 0}, 3) == [2, 0, 1]
    for corrupt in ({0: 0}, {0: 0, 1: 0}, {0: 1, 1: 2}):
        with pytest.raises(CompilationError):
            invert_permutation(corrupt, 2)


def test_routing_reproducibility_and_corrupt_map_rejection(bounded_qcec):
    original = qasm2.load(atlas.ROOT / "data/inputs/qft-4q.qasm")
    outputs = [
        atlas.compile_once(original, "qmap-sc-heuristic-maponly-v1", "line", seed)
        for seed in (7, 19)
    ]
    a, b = outputs
    assert qasm2.dumps(a[0]) == qasm2.dumps(b[0])
    assert a[2:] == b[2:]
    assert a[2] != a[3]
    assert bounded_qcec(original, a[0], a[2], a[3])["accepted"]
    bad_final = list(a[3])
    bad_final[0], bad_final[1] = bad_final[1], bad_final[0]
    assert bounded_qcec(original, a[0], a[2], bad_final)["accepted"] is False
