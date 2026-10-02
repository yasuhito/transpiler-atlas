import pytest
from qiskit import QuantumCircuit, qasm2

from atlas import (
    check_equivalence,
    compile_once,
    edges_for,
    generate_inputs,
    metrics,
    validation_copy,
)


def test_depth_respects_one_qubit_dependencies():
    circuit = QuantumCircuit(3)
    circuit.cx(0, 1)
    circuit.sx(1)
    circuit.cx(1, 2)
    result = metrics(circuit, edges_for(3, "line"))
    assert result["two_qubit_count"] == 2
    assert result["two_qubit_depth"] == 2
    assert result["total_depth"] == 3


def test_invalid_coupling_and_gate_are_rejected():
    circuit = QuantumCircuit(3)
    circuit.cx(0, 2)
    with pytest.raises(ValueError, match="coupling"):
        metrics(circuit, edges_for(3, "line"))
    circuit = QuantumCircuit(1)
    circuit.h(0)
    with pytest.raises(ValueError, match="gate"):
        metrics(circuit, [])


def test_bad_maps_are_rejected():
    with pytest.raises(ValueError, match="bijective"):
        validation_copy(QuantumCircuit(2), [0, 0], [0, 1])


def test_checker_detects_corrupted_circuit_and_output_map():
    original = QuantumCircuit(2)
    original.cx(0, 1)
    assert check_equivalence(original, original, [0, 1], [0, 1])["accepted"]
    corrupt = original.copy()
    corrupt.x(1)
    assert not check_equivalence(original, corrupt, [0, 1], [0, 1])["accepted"]
    assert not check_equivalence(original, original, [0, 1], [1, 0])["accepted"]


@pytest.mark.parametrize("compiler", ["qiskit", "pytket"])
@pytest.mark.parametrize("family", ["qft-4q", "qaoa-4q", "adder-6q"])
def test_actual_pipeline_preserves_input_including_multiple_registers(compiler, family):
    cases = generate_inputs()
    case = next(c for c in cases if c["id"] == family)
    original = qasm2.load(case["path"])
    native, _, initial, final = compile_once(original, compiler, "line", 7)
    metrics(native, edges_for(original.num_qubits, "line"))
    assert check_equivalence(original, native, initial, final)["accepted"]
