import hashlib
import shutil

import pytest
from qiskit import QuantumCircuit, qasm2

import atlas
from atlas import (
    check_equivalence,
    compile_once,
    corpus_unitary,
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


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    shutil.copytree(atlas.ROOT / "corpora", tmp_path / "corpora")
    monkeypatch.setattr(atlas, "ROOT", tmp_path)
    return generate_inputs()


@pytest.mark.parametrize("compiler", ["qiskit", "pytket"])
@pytest.mark.parametrize(
    "family", ["qft-4q", "qaoa-4q", "adder-6q"] + [f"qasmbench-{c}" for c in atlas.CORPUS_CASES]
)
def test_actual_pipeline_preserves_input_including_multiple_registers(compiler, family, inputs):
    case = next(c for c in inputs if c["id"] == family)
    original = qasm2.load(atlas.ROOT / case["path"])
    native, _, initial, final = compile_once(original, compiler, "line", 7)
    metrics(native, edges_for(original.num_qubits, "line"))
    assert check_equivalence(original, native, initial, final)["accepted"]


def test_manifest_provenance_and_regeneration_are_stable(inputs):
    assert len(inputs) == 12
    assert len({c["family"] for c in inputs}) == 6
    assert generate_inputs() == inputs
    for case in inputs:
        assert (
            hashlib.sha256((atlas.ROOT / case["path"]).read_bytes()).hexdigest() == case["sha256"]
        )
        if "provenance" in case:
            p = case["provenance"]
            assert (
                hashlib.sha256((atlas.ROOT / p["source_path"]).read_bytes()).hexdigest()
                == p["source_sha256"]
            )
            assert (atlas.ROOT / p["license_path"]).exists()


@pytest.mark.parametrize("instruction", ["x q[0];", "reset q[0];"])
def test_corpus_rejects_nonterminal_measurement_and_reset(tmp_path, instruction):
    path = tmp_path / "invalid.qasm"
    path.write_text(
        'OPENQASM 2.0; include "qelib1.inc"; qreg q[1]; creg c[1]; '
        f"measure q[0] -> c[0]; {instruction}"
    )
    with pytest.raises(ValueError):
        corpus_unitary(path)


def test_corpus_allows_disjoint_gates_after_readout(tmp_path):
    path = tmp_path / "readout.qasm"
    path.write_text(
        'OPENQASM 2.0; include "qelib1.inc"; qreg q[2]; creg c[2]; '
        "h q[0]; measure q[0] -> c[0]; x q[1]; measure q[1] -> c[1];"
    )
    circuit, removed = corpus_unitary(path)
    assert [item.operation.name for item in circuit.data] == ["h", "x"]
    assert removed == {"measure": 2, "barrier": 0}
    assert circuit.num_clbits == 0


def test_existing_suite_requires_explicit_overwrite(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    (tmp_path / "data/results.json").write_text('{"suite": "pilot-v0.2"}')
    monkeypatch.setattr(atlas, "ROOT", tmp_path)
    with pytest.raises(RuntimeError, match="--overwrite"):
        atlas.run_pilot()


def test_suite_change_requires_matching_archive(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    (tmp_path / "data/results.json").write_text('{"suite": "pilot-v0.1"}')
    monkeypatch.setattr(atlas, "ROOT", tmp_path)
    with pytest.raises(RuntimeError, match="Archive"):
        atlas.run_pilot()
