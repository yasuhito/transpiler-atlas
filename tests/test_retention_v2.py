"""Current verifier identity and historical read compatibility."""

import copy
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

import atlas
import publication
import retention as h
import retention_campaign as campaign


def historical():
    selector = json.loads((atlas.ROOT / "diagnostics/compile-retention/report.json").read_text())
    mapping = json.loads((atlas.ROOT / selector["file_map"]).read_text())
    return selector, mapping


def test_new_suite_is_distinct():
    assert campaign.SUITE == "pilot-compile-retention-v2-qcec3102-420s-check60"
    assert h.CURRENT.qcec_version == "3.10.2"
    assert h.CURRENT.policy()["verifier"] == "mqt.qcec.verify_with_hard_timeout"


def test_real_sealed_v1_reads_without_verification(monkeypatch):
    from mqt import qcec

    def forbidden(*args, **kwargs):
        pytest.fail("Reading sealed evidence must not execute a verifier")

    monkeypatch.setattr(qcec, "verify", forbidden)
    monkeypatch.setattr(qcec, "verify_with_hard_timeout", forbidden)
    monkeypatch.setattr(h, "_check_child", forbidden)
    selector, mapping = historical()
    before = {name: h._digest(atlas.ROOT / path) for name, path in mapping.items()}
    data, _ = publication.load(atlas.ROOT, file_map=selector["file_map"])
    spec = json.loads((atlas.ROOT / mapping["campaign.json"]).read_text())
    assert campaign.frozen_suite(spec) == h.V1
    assert spec["policy"] == h.V1.policy()
    assert data["suite"] == h.V1.name
    assert len(data["results"]) == 18
    assert before == {name: h._digest(atlas.ROOT / path) for name, path in mapping.items()}


@pytest.mark.parametrize(
    "mutation", ["version", "suite", "duplicate", "policy", "revision", "prefix"]
)
def test_historical_identity_rejects_mislabeling(mutation):
    _, mapping = historical()
    spec = copy.deepcopy(json.loads((atlas.ROOT / mapping["campaign.json"]).read_text()))
    if mutation == "version":
        spec["versions"]["mqt-qcec"] = "3.10.2"
    elif mutation == "suite":
        spec["suite"] = "unknown-suite"
    elif mutation == "duplicate":
        spec["versions"]["mqt.qcec"] = "3.10.1"
    elif mutation == "policy":
        spec["policy"]["check_hard_seconds"] = 61
    elif mutation == "revision":
        spec["protocol"]["protocol_version"] = 2
    else:
        spec["campaign_id"] = "wrong-prefix"
    with pytest.raises(ValueError):
        campaign.frozen_suite(spec)


def test_real_api_process_dict_qpy_timeout_and_exception(monkeypatch):
    from mqt import qcec
    from qiskit import QuantumCircuit, qpy

    circuit = QuantumCircuit(2)
    circuit.h(0)
    circuit.cx(0, 1)
    circuit.global_phase = 0.375
    stream = io.BytesIO()
    qpy.dump(circuit, stream)
    restored = qpy.load(io.BytesIO(stream.getvalue()))[0]
    assert restored == circuit and float(restored.global_phase) == 0.375
    spawned = []
    popen = subprocess.Popen

    def observe(*args, **kwargs):
        process = popen(*args, **kwargs)
        spawned.append(process.pid)
        return process

    monkeypatch.setattr(subprocess, "Popen", observe)
    result = qcec.verify_with_hard_timeout(
        circuit, restored, deadline=10, **atlas.STRICT_CHECKER_OPTIONS
    )
    assert isinstance(result, dict) and result["equivalence"] == "equivalent"
    assert "check_time" in result and "checkers" in result
    assert len(spawned) == 1 and spawned[0] != os.getpid()
    assert not Path(f"/proc/{spawned[0]}").exists()
    with pytest.raises(TimeoutError):
        qcec.verify_with_hard_timeout(circuit, restored, deadline=0.0001)
    with pytest.raises(RuntimeError, match="FileNotFoundError"):
        qcec.verify_with_hard_timeout("missing.qasm", "missing.qasm", deadline=10)


def check_fixture(tmp_path, monkeypatch, mode):
    """Execute the child interface; only the API and clock are synthetic."""
    from mqt import qcec
    from qiskit import QuantumCircuit, qasm2

    circuit = QuantumCircuit(2)
    circuit.h(0)
    circuit.cx(0, 1)
    native = circuit.copy()
    native.global_phase = 0.375
    source = tmp_path / "input.qasm"
    source.write_text(qasm2.dumps(circuit))
    job = h.Job("toy", "qiskit-l2", "line", 7)
    record = {"job": h.asdict(job), "initial_map": [1, 0], "final_map": [0, 1]}
    h._json(tmp_path / "spec.json", {"protocol": h.CURRENT.policy()})
    h._durable(tmp_path / "r0.compile.json", b"Synthetic committed fixture\n")
    manifest = h._digest(tmp_path / "r0.compile.json")
    now = time.monotonic_ns()
    clock = [now]
    cutoff = now / 1e9 + 10
    start = {
        "monotonic_ns": now,
        "effective_budget_seconds": 10,
        "check_deadline_monotonic": cutoff,
        "compile_manifest_sha256": manifest,
    }
    h._json(tmp_path / "r0.verification-start.json", start)
    monkeypatch.setattr(h, "_native", lambda *_: (native, record))
    monkeypatch.setattr(h, "_case", lambda *_: ({}, source))
    monkeypatch.setattr(h.time, "monotonic_ns", lambda: clock[0])
    calls = []

    def verify(before, after, *, deadline, **options):
        calls.append(deadline)
        assert options == atlas.STRICT_CHECKER_OPTIONS
        assert before == atlas.strict_pair(circuit, native, [1, 0], [0, 1])[0]
        assert after == atlas.validation_copy(native, [1, 0], [0, 1])
        assert float(after.global_phase) == 0.375
        assert 8.999999 <= deadline <= 9.000001
        if mode == "timeout":
            clock[0] += round(deadline * 1e9)
            raise TimeoutError("Synthetic upstream forced timeout")
        if mode == "exception":
            raise RuntimeError("Synthetic upstream worker failure")
        return {"equivalence": mode, "checkers": []}

    monkeypatch.setattr(qcec, "verify_with_hard_timeout", verify)
    if mode == "budget":
        clock[0] += 9_500_000_000
    if mode == "exception":
        with pytest.raises(RuntimeError, match="worker failure"):
            h._check_child(tmp_path, 0)
        assert not (tmp_path / "r0.reply.json").exists()
        return None, calls
    h._check_child(tmp_path, 0)
    reply = json.loads((tmp_path / "r0.reply.json").read_text())
    result = h.decode_check_reply(
        h.CURRENT,
        reply,
        manifest,
        start,
        clock[0] / 1e9 + 0.01,
        h._digest(tmp_path / "r0.verification-start.json"),
    )
    return (result, reply, start, manifest, clock[0] / 1e9 + 0.01), calls


@pytest.mark.parametrize(
    "mode,state,reason",
    [
        ("equivalent", "passed", None),
        ("equivalent_up_to_global_phase", "passed", None),
        ("not_equivalent", "not_equivalent", None),
        ("no_information", "verification_incomplete", "nonconclusive_criterion"),
        ("future", "error", "unknown_criterion"),
        ("timeout", "verification_incomplete", "qcec_hard_timeout"),
        ("budget", "verification_incomplete", "check_budget"),
        ("exception", "error", "check_child_failure"),
    ],
)
def test_hard_child_routes_and_remaining_budget(tmp_path, monkeypatch, mode, state, reason):
    facts, calls = check_fixture(tmp_path, monkeypatch, mode)
    if mode == "exception":
        assert len(calls) == 1
        return
    result, reply, start, manifest, observed = facts
    assert (result[0], result[2]) == (state, reason)
    assert len(calls) == (mode != "budget")
    assert reply["inner_seconds"] < 10
    for field, value in [
        ("inner_seconds", 60),
        ("called_monotonic_ns", start["monotonic_ns"] - 1),
        ("verification_start_sha256", "wrong"),
        ("outcome", "invented"),
        ("returned_monotonic_ns", int((observed + 1) * 1e9)),
    ]:
        bad = {**reply, field: value}
        with pytest.raises((ValueError, KeyError, TypeError)):
            h.decode_check_reply(
                h.CURRENT,
                bad,
                manifest,
                start,
                observed,
                h._digest(tmp_path / "r0.verification-start.json"),
            )


def test_actual_nested_api_timeout_reaps_grandchild(tmp_path):
    pidfile = tmp_path / "descendant.pid"
    worker = (
        "import subprocess,sys,time;from pathlib import Path;"
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);"
        f"Path({str(pidfile)!r}).write_text(str(p.pid));time.sleep(30)"
    )
    driver = f"""
import importlib, subprocess, sys
from qiskit import QuantumCircuit
m = importlib.import_module('mqt.qcec.verify_hard_timeout')
real = subprocess.run
def instrument(command, **kwargs):
    return real([sys.executable, '-c', {worker!r}], **kwargs)
m.subprocess.run = instrument
try:
    m.verify_with_hard_timeout(QuantumCircuit(1), QuantumCircuit(1), .5)
except TimeoutError:
    print('inner timeout', flush=True)
"""
    process = h._supervise([sys.executable, "-c", driver], tmp_path, "nested", time.monotonic() + 5)
    pid = int(pidfile.read_text())
    assert process["state"] == "completed" and process["returncode"] == 0
    assert "inner timeout" in (tmp_path / "nested.stdout.log").read_text()
    assert pid in [entry["pid"] for entry in process["adopted_reaped"]]
    assert not process["members_after_cleanup"] and not Path(f"/proc/{pid}").exists()


def test_completion_observed_after_cutoff_is_timeout(tmp_path, monkeypatch):
    waitid = h.os.waitid

    def delayed_observation(*args, **kwargs):
        status = waitid(*args, **kwargs)
        if status is not None:
            time.sleep(0.2)  # Scheduler delay after exit was found, before its receipt.
        return status

    monkeypatch.setattr(h.os, "waitid", delayed_observation)
    process = h._supervise(
        [sys.executable, "-c", "pass"], tmp_path, "late-observation", time.monotonic() + 0.15
    )
    assert process["observed_monotonic"] >= process["deadline_monotonic"]
    assert process["state"] == "timeout"
    assert not process["members_after_cleanup"]


def test_outer_deadline_includes_upstream_serialization(tmp_path):
    marker = tmp_path / "serialization-started"
    driver = f"""
import importlib, time
from pathlib import Path
from qiskit import QuantumCircuit
m = importlib.import_module('mqt.qcec.verify_hard_timeout')
def slow(circuit):
    Path({str(marker)!r}).write_text('started')
    time.sleep(30)
m._encode_circuit = slow
m.verify_with_hard_timeout(QuantumCircuit(1), QuantumCircuit(1), 60)
"""
    process = h._supervise(
        [sys.executable, "-c", driver], tmp_path, "serialization", time.monotonic() + 2
    )
    assert marker.is_file()
    assert process["state"] == "timeout"
    assert process["wall_seconds"] < 2.5
    assert not process["members_after_cleanup"]
