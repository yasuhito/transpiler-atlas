import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import atlas


def test_new_campaign_refuses_retry_without_touching_history(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    path = tmp_path / "data/results.json"
    path.write_text(
        json.dumps({"suite": "pilot-v0.4", "protocol": {"worker_timeout_seconds": 600}})
    )
    before = path.read_bytes()
    monkeypatch.setattr(atlas, "ROOT", tmp_path)
    command = subprocess.run(
        [sys.executable, str(Path(atlas.__file__)), "retry-timeouts"],
        capture_output=True,
        text=True,
    )
    assert command.returncode == 2
    assert "invalid choice" in command.stderr
    assert path.read_bytes() == before
    assert not (tmp_path / "data/attempts").exists()
    with pytest.raises(RuntimeError, match="cannot overwrite"):
        atlas.run_pilot(overwrite=True)
    with pytest.raises(RuntimeError, match="cannot overwrite"):
        atlas.run_pilot(resume_log=tmp_path / "old-log")


def test_job_timeout_uses_shared_budget_and_kills_process_group(monkeypatch):
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
    for config in atlas.CONFIGURATIONS:
        result = atlas.execute_job(
            {"id": "qft-4q", "family": "QFT", "qubits": 4}, config["id"], "line", 7, {}
        )
        assert result["status"] == "timeout"
        assert result["worker_timeout_seconds"] == atlas.WORKER_TIMEOUT_SECONDS == 420
        assert result["error"] == f"{atlas.WORKER_TIMEOUT_SECONDS} s worker budget exceeded"
    assert waits == [atlas.WORKER_TIMEOUT_SECONDS, None] * 12
    assert killed == [123] * 12


def test_interrupted_job_kills_and_reaps_group(monkeypatch):
    killed = []

    class Process:
        pid = 456
        calls = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def communicate(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise KeyboardInterrupt
            return "", ""

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: Process())
    monkeypatch.setattr(os, "killpg", lambda pid, signal: killed.append(pid))
    with pytest.raises(KeyboardInterrupt):
        atlas.execute_job(
            {"id": "qft-4q", "family": "QFT", "qubits": 4}, "qiskit-l2", "line", 7, {}
        )
    assert killed == [456]


def test_historical_log_reader_rejects_wrong_schedule_and_missing_artifacts(tmp_path, monkeypatch):
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
