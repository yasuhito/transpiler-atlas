import json
import shutil

import pytest
from qiskit import qasm2

import atlas


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    shutil.copytree(atlas.ROOT / "corpora", tmp_path / "corpora")
    monkeypatch.setattr(atlas, "ROOT", tmp_path)
    return atlas.generate_inputs()


def test_configuration_registry_has_supported_levels_and_fixed_reference():
    assert len({c["id"] for c in atlas.CONFIGURATIONS}) == 11
    assert [c["optimization_level"] for c in atlas.CONFIGURATIONS if c["compiler"] == "qiskit"] == [
        0,
        1,
        2,
        3,
    ]
    assert [c["optimization_level"] for c in atlas.CONFIGURATIONS if c["compiler"] == "bqskit"] == [
        1,
        2,
        3,
        4,
    ]
    assert atlas.configuration_for(atlas.REFERENCE_CONFIGURATION)["optimization_level"] == 2
    assert atlas.configuration_for("pytket-pauli")["seed_supported"]
    assert not atlas.configuration_for("pytket-peephole")["seed_supported"]
    with pytest.raises(ValueError, match="Unknown configuration"):
        atlas.configuration_for("qiskit-l4")


@pytest.mark.parametrize("configuration", [c["id"] for c in atlas.CONFIGURATIONS])
def test_all_effort_configurations_compile_real_shared_input(inputs, configuration):
    case = next(c for c in inputs if c["id"] == "qasmbench-qaoa_n3")
    original = qasm2.load(atlas.ROOT / case["path"])
    native, elapsed, initial, final = atlas.compile_once(original, configuration, "line", 7)
    assert elapsed > 0
    atlas.metrics(native, atlas.edges_for(original.num_qubits, "line"))
    assert sorted(initial) == sorted(final) == list(range(original.num_qubits))
    assert atlas.check_equivalence(original, native, initial, final)["accepted"]


def test_worker_artifacts_and_results_do_not_collide_between_levels(inputs):
    case = next(c for c in inputs if c["id"] == "qft-4q")
    records = [atlas.worker(case, c, "line", 7) for c in ["qiskit-l0", "qiskit-l1"]]
    assert {r["compiler"] for r in records} == {"qiskit"}
    assert {r["configuration_id"] for r in records} == {"qiskit-l0", "qiskit-l1"}
    artifacts = [t["artifact"] for r in records for t in r["trials"]]
    assert len(set(artifacts)) == 6
    for r in records:
        assert r["status"] == "passed"
        assert len(r["timing_samples_ms"]) == 3
        for trial in r["trials"]:
            assert r["configuration_id"] in trial["artifact"]
            assert (atlas.ROOT / trial["artifact"]).is_file()
    json.dumps(records)
