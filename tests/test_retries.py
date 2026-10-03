import copy
import json
import os
import shutil
import subprocess

import pytest

import atlas


def test_timeout_retry_preserves_completed_values_and_attempt_history(tmp_path, monkeypatch):
    shutil.copytree(atlas.ROOT / "corpora", tmp_path / "corpora")
    monkeypatch.setattr(atlas, "ROOT", tmp_path)
    cases = atlas.generate_inputs()
    case = cases[0]
    rows = [
        {
            "case_id": case["id"],
            "configuration_id": "qiskit-l2",
            "target": "line",
            "seed": 7,
            "status": "passed",
            "compile_ms": 7.25,
        },
        {
            "case_id": case["id"],
            "configuration_id": "bqskit-l3",
            "target": "line",
            "seed": 7,
            "status": "timeout",
            "error": "120 s worker budget exceeded",
        },
        {
            "case_id": case["id"],
            "configuration_id": "bqskit-l4",
            "target": "line",
            "seed": 7,
            "status": "timeout",
            "error": "120 s worker budget exceeded",
        },
    ]
    document = {
        "suite": atlas.SUITE,
        "cases": cases,
        "results": rows,
        "protocol": {"configurations": atlas.CONFIGURATIONS, "worker_timeout_seconds": 120},
        "environment": {
            "versions": {},
            "cpu_affinity": [min(os.sched_getaffinity(0))],
            "thread_env": {"OMP_NUM_THREADS": "1"},
        },
    }
    path = tmp_path / "data/results.json"
    original = json.dumps(document, indent=2) + "\n"
    path.write_text(original)
    affinity = []
    monkeypatch.setattr(os, "sched_setaffinity", lambda pid, cpus: affinity.append(cpus))
    calls = []

    def execute(case, configuration, target, seed, env):
        assert env["OMP_NUM_THREADS"] == "1"
        calls.append(configuration)
        result = copy.deepcopy(next(r for r in rows if r["configuration_id"] == configuration))
        result.update(
            status="verification_failed" if configuration == "bqskit-l3" else "timeout",
            worker_timeout_seconds=600,
        )
        return result

    monkeypatch.setattr(atlas, "execute_job", execute)
    atlas.retry_timeouts()
    updated = json.loads(path.read_text())
    assert calls == ["bqskit-l3", "bqskit-l4"]
    assert affinity == [set(document["environment"]["cpu_affinity"])]
    assert updated["protocol"]["worker_timeout_seconds"] == 600
    assert updated["protocol"]["initial_worker_timeout_seconds"] == 120
    assert updated["protocol"]["timeout_retry_entries"] == 2
    assert updated["results"][0] == rows[0]
    assert updated["results"][1]["previous_attempts"] == [rows[1]]
    assert updated["results"][2]["previous_attempts"] == [rows[2]]
    snapshot = tmp_path / updated["protocol"]["initial_attempt_snapshot"]
    assert snapshot.read_text() == original
    atlas.retry_timeouts()
    assert calls == ["bqskit-l3", "bqskit-l4"], (
        "Already retried 600-second timeouts are not repeated"
    )
    assert snapshot.read_text() == original


def test_job_timeout_uses_shared_600_second_budget_and_kills_process_group(monkeypatch):
    waits = []
    killed = []

    class Process:
        pid = 123

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def communicate(self, timeout=None):
            waits.append(timeout)
            if timeout is not None:
                raise subprocess.TimeoutExpired("worker", timeout)
            return "", ""

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: Process())
    monkeypatch.setattr(os, "killpg", lambda pid, signal: killed.append(pid))
    result = atlas.execute_job(
        {"id": "qft-4q", "family": "QFT", "qubits": 4}, "bqskit-l4", "line", 7, {}
    )
    assert waits == [600, None]
    assert killed == [123]
    assert result["status"] == "timeout"
    assert result["worker_timeout_seconds"] == 600
    assert result["error"] == "600 s worker budget exceeded"


def test_resume_rejects_wrong_schedule_and_missing_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(atlas, "ROOT", tmp_path)
    case = {"id": "qft-4q"}
    jobs = [(case, "qiskit-l2", "line", 7)]
    row = {
        "case_id": "qft-4q",
        "configuration_id": "qiskit-l2",
        "compiler": "qiskit",
        "target": "line",
        "seed": 7,
        "trials": [],
    }
    log = tmp_path / "run.jsonl"
    entry = {"scheduled": 1, "completed": 1, "result": row}
    log.write_text(json.dumps(entry) + "\n")
    assert atlas.read_completed_results(log, jobs) == [row]
    row["seed"] = 19
    log.write_text(json.dumps(entry) + "\n")
    with pytest.raises(ValueError, match="schedule"):
        atlas.read_completed_results(log, jobs)
    row["seed"] = 7
    row["trials"] = [{"artifact": "missing.qasm"}]
    log.write_text(json.dumps(entry) + "\n")
    with pytest.raises(ValueError, match="artifact"):
        atlas.read_completed_results(log, jobs)
