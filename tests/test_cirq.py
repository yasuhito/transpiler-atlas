import hashlib
import math

import pytest
from qiskit import QuantumCircuit, qasm2
from test_qmap import case

import atlas
from cirq_adapter import compile_native, recipe_metadata
from qmap_adapter import CompilationError, NativeTarget


@pytest.mark.parametrize(
    "name", ["multiple-registers", "idle-wires", "width-one", "phase", "idle-routing", "empty"]
)
@pytest.mark.parametrize("target", ["line", "all-to-all"])
def test_irregular_native_input_maps_phase_and_width(name, target, bounded_qcec):
    original = case(name)
    order = tuple((r.name, i) for r in original.qregs for i in range(r.size))
    data = qasm2.dumps(original).encode()
    target_spec = NativeTarget(
        original.num_qubits,
        tuple(atlas.edges_for(original.num_qubits, target)),
        ("cx", "rz", "sx", "x"),
    )
    native, elapsed, initial, final = compile_native(
        data, order, target_spec, input_phase=float(original.global_phase)
    )
    assert elapsed > 0
    assert native.num_qubits == original.num_qubits
    assert not native.ancillas and not native.num_clbits
    atlas.metrics(native, list(target_spec.directed_edges))
    assert sorted(initial) == sorted(final) == list(range(original.num_qubits))
    assert bounded_qcec(original, native, initial, final)["accepted"]


def test_known_input_scalar_restored_once():
    original = QuantumCircuit(1)
    original.x(0)
    original.global_phase = 0.37
    native, _, _, _ = atlas.compile_once(original, "cirq-routecqc-maponly-v1", "line", 7)
    assert math.isclose(float(native.global_phase), 0.37, abs_tol=1e-14)


def test_worker_uses_frozen_bytes_not_reexport(tmp_path, monkeypatch):
    source = atlas.ROOT / "data/inputs/qft-4q.qasm"
    data = source.read_bytes()
    (tmp_path / "data/inputs").mkdir(parents=True)
    (tmp_path / "data/inputs/qft-4q.qasm").write_bytes(data)
    record = {
        "id": "qft-4q",
        "path": "data/inputs/qft-4q.qasm",
        "qubits": 4,
        "family": "QFT",
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    monkeypatch.setattr(atlas, "ROOT", tmp_path)
    import cirq_adapter

    actual = cirq_adapter.compile_native
    seen = []

    def capture(raw, *args, **kwargs):
        seen.append(raw)
        return actual(raw, *args, **kwargs)

    monkeypatch.setattr(cirq_adapter, "compile_native", capture)
    result = atlas.worker(record, "cirq-routecqc-maponly-v1", "line", 7)
    assert result["status"] == "passed"
    assert seen == [data] * 3
    assert result["seed_supported"] is False


def test_descriptor_copy_and_unsupported_gate():
    desc = recipe_metadata()
    desc["tags_to_ignore"].append("ignored")
    assert recipe_metadata()["tags_to_ignore"] == []
    raw = b'OPENQASM 2.0; include "qelib1.inc"; qreg q[1]; u3(0.3,0.2,0.1) q[0];'
    with pytest.raises(CompilationError):
        compile_native(raw, (("q", 0),), NativeTarget(1, (), ("cx", "rz", "sx", "x")))


def test_reproducible_outputs_and_corruption(bounded_qcec):
    original = qasm2.load(atlas.ROOT / "data/inputs/qft-4q.qasm")
    outputs = [
        atlas.compile_once(original, "cirq-routecqc-maponly-v1", "line", slot)
        for slot in (7, 19, 43)
    ]
    a = outputs[0]
    assert all(
        qasm2.dumps(x[0]) == qasm2.dumps(a[0])
        and x[2:] == a[2:]
        and float(x[0].global_phase) == float(a[0].global_phase)
        for x in outputs
    )
    broken = a[0].copy()
    broken.x(0)
    assert not bounded_qcec(original, broken, a[2], a[3])["accepted"]
    wrong = list(a[3])
    wrong[0], wrong[1] = wrong[1], wrong[0]
    assert not bounded_qcec(original, a[0], a[2], wrong)["accepted"]
