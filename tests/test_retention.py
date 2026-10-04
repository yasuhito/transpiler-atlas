"""Real-process and native-storage gates for the standalone protocol."""

import io
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

import retention as h


def test_locked_qcec_criterion_table():
    import importlib.metadata

    from mqt.qcec.pyqcec import EquivalenceCriterion

    assert importlib.metadata.version("mqt.qcec") == "3.10.1"
    assert set(EquivalenceCriterion.__members__) == set(h.CRITERIA)


@pytest.mark.parametrize("criterion,state", list(h.CRITERIA.items()) + [("future_enum", "error")])
def test_criterion(criterion, state):
    assert h._classification(criterion) == state


def saved(state="passed"):
    return h.SavedTrial(h.Compiled(0, Path("unused"), 1), h.Check(state, None, None, 0))


@pytest.mark.parametrize(
    "facts,fault,label",
    [
        ((saved(), saved(), saved()), None, "passed"),
        ((saved(), saved("verification_incomplete"), saved()), None, "verification_incomplete"),
        (
            (saved("not_equivalent"), saved("verification_incomplete"), saved()),
            None,
            "not_equivalent",
        ),
        (
            (h.MissingTrial(0, "budget"), saved("not_equivalent"), saved()),
            None,
            "compile_incomplete",
        ),
        ((saved(), saved("error"), saved()), None, "error"),
        ((saved(), saved(), saved()), "cleanup_fault", "error"),
    ],
)
def test_rollup(facts, fault, label):
    report = h.Report(h.Job("case", "config", "line", 7), facts, fault)
    assert report.status == label
    assert report.accepted == sum(
        isinstance(t, h.SavedTrial) and t.check.state == "passed" for t in facts
    )


def _fake(directory, mode):
    pidfile = directory / "descendant.pid"
    code = (
        "import subprocess,sys,time,pathlib; "
        "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
        f"pathlib.Path({str(pidfile)!r}).write_text(str(p.pid)); "
        + ("time.sleep(60)" if mode == "timeout" else "sys.exit(0)")
    )
    result = h._supervise(
        [sys.executable, "-c", code],
        directory,
        mode,
        time.monotonic() + (0.5 if mode == "timeout" else 3),
    )
    pid = int(pidfile.read_text())
    assert not Path(f"/proc/{pid}").exists()
    assert pid in [r["pid"] for r in result["adopted_reaped"]]
    assert not result["members_after_cleanup"]
    assert not h._members(result["pid"])
    return result


@pytest.mark.parametrize("mode", ["timeout", "normal"])
def test_reap_real_descendant(tmp_path, mode):
    result = _fake(tmp_path, mode)
    assert result["state"] == ("timeout" if mode == "timeout" else "completed")


def test_no_budget_no_spawn(tmp_path):
    result = h._supervise(
        [sys.executable, "-c", "raise Exception()"], tmp_path, "never", time.monotonic() - 1
    )
    assert result["state"] == "not_started"
    assert list(tmp_path.iterdir()) == [tmp_path / "never.process.json"]


def test_outer_cancel_real_group(tmp_path):
    pidfile = tmp_path / "descendant.pid"
    driver = (
        "import sys,time,subprocess,pathlib,os; import retention as h; "
        f"d=pathlib.Path({str(tmp_path)!r}); "
        'code="import subprocess,sys,time,pathlib; '
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']); "
        f'pathlib.Path({str(pidfile)!r}).write_text(str(p.pid));time.sleep(60)"; '
        "h._supervise([sys.executable,'-c',code],d,'cancel',time.monotonic()+30)"
    )
    with (tmp_path / "driver.log").open("w") as log:
        parent = subprocess.Popen(
            [sys.executable, "-c", driver], cwd=h.ROOT, stdout=log, stderr=log
        )
        try:
            limit = time.monotonic() + 5
            while not pidfile.exists() and time.monotonic() < limit:
                time.sleep(0.02)
            assert pidfile.exists()
            os.kill(parent.pid, signal.SIGTERM)
            parent.wait(timeout=5)
            assert parent.returncode != 0
            pid = int(pidfile.read_text())
            assert not Path(f"/proc/{pid}").exists()
            evidence = json.loads((tmp_path / "cancel.process.json").read_text())
            assert evidence["state"] == "cancelled"
            assert not evidence["members_after_cleanup"]
        finally:
            if parent.poll() is None:
                parent.kill()
                parent.wait()


def test_exclusive_and_orphan(tmp_path):
    qasm = tmp_path / "r0.qasm"
    h._durable(qasm, b"orphan")
    assert h._read_compile(tmp_path, 0) is None
    with pytest.raises(FileExistsError):
        h._durable(qasm, b"replace")
    assert qasm.read_bytes() == b"orphan"


def _bundle(tmp_path):
    from qiskit import QuantumCircuit, qasm2, qpy

    import atlas

    job = h.Job("toy", "qiskit-l2", "line", 7)
    h._json(
        tmp_path / "spec.json", {"job": h.asdict(job), "qubits": 2, "input_sha256": "test-input"}
    )
    native = QuantumCircuit(2)
    native.rz(0.125, 0)
    native.cx(0, 1)
    native.global_phase = 0.375
    buffer = io.BytesIO()
    qpy.dump(native, buffer)
    for kind, data in [("qasm", (qasm2.dumps(native) + "\n").encode()), ("qpy", buffer.getvalue())]:
        h._durable(tmp_path / f"r0.{kind}", data)
    record = {
        "job": h.asdict(job),
        "repeat": 0,
        "spec_sha256": h._digest(tmp_path / "spec.json"),
        "input_sha256": "test-input",
        "compile_ms": 1.5,
        "initial_map": [1, 0],
        "final_map": [0, 1],
        "global_phase": 0.375,
        "metrics": atlas.metrics(native, atlas.edges_for(2, "line")),
    }
    for kind in ("qasm", "qpy"):
        record[kind] = {"path": f"r0.{kind}", "sha256": h._digest(tmp_path / f"r0.{kind}")}
    h._json(tmp_path / "r0.compile.json", record)
    return native


def test_native_snapshot_phase_maps(tmp_path):
    native = _bundle(tmp_path)
    restored, record = h._native(tmp_path, 0)
    assert native == restored
    assert float(restored.global_phase) == 0.375
    assert record["initial_map"] == [1, 0]
    assert record["final_map"] == [0, 1]


def test_tamper_not_silent_missing(tmp_path):
    _bundle(tmp_path)
    (tmp_path / "r0.qasm").write_text("tampered")
    with pytest.raises(ValueError, match="integrity"):
        h._read_compile(tmp_path, 0)


@pytest.mark.parametrize(
    "field,value",
    [
        ("global_phase", 0.875),
        ("initial_map", [0, 0]),
        ("metrics", {"two_qubit_count": 999}),
    ],
)
def test_native_rederives_phase_maps_and_metrics(tmp_path, field, value):
    _bundle(tmp_path)
    path = tmp_path / "r0.compile.json"
    record = json.loads(path.read_text())
    record[field] = value
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError):
        h._native(tmp_path, 0)


def test_corrupt_map_and_scalars():
    good = {"initial_map": [0, 1], "final_map": [1, 0], "compile_ms": 1, "global_phase": 0}
    for bad in [
        {**good, "initial_map": [0, 0]},
        {**good, "final_map": [False, 1]},
        {**good, "compile_ms": -1},
        {**good, "global_phase": float("nan")},
    ]:
        with pytest.raises(ValueError):
            h._maps_phase(bad, 2)


def test_real_qcec_phase_snapshot_and_corruption(tmp_path):
    import atlas

    native = _bundle(tmp_path)
    restored, _ = h._native(tmp_path, 0)
    direct = atlas.check_equivalence(native, native, [0, 1], [0, 1])
    transported = atlas.check_equivalence(native, restored, [0, 1], [0, 1])
    assert direct["accepted"] and transported["criterion"] == direct["criterion"]
    broken = restored.copy()
    broken.x(0)
    assert atlas.check_equivalence(native, broken, [0, 1], [0, 1])["criterion"] == "not_equivalent"
