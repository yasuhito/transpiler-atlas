import json
import os
import subprocess

import pytest

import atlas
import campaign
from mixed_sources import record_budget_seconds


def test_explicit_budget_does_not_evaluate_missing_fallback():
    doc = {
        "protocol": {
            "configuration_sources": {"id": "source"},
            "measurement_sources": {
                "source": {"protocol": {"initial_worker_timeout_seconds": 120}}
            },
        }
    }
    assert (
        record_budget_seconds(doc, {"configuration_id": "id", "worker_timeout_seconds": 600}) == 600
    )
    assert record_budget_seconds(doc, {"configuration_id": "id"}) == 120


def test_unknown_workspace_format_rejected(tmp_path):
    root = campaign.create(tmp_path, prepare_only=True)
    spec = json.loads((root / "campaign.json").read_text())
    spec["spec_format_version"] = 99
    (root / "campaign.json").write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="settings"):
        campaign.validate_workspace(root)


def test_missing_worker_identity_is_not_filled_into_success(monkeypatch):
    class Process:
        returncode = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def communicate(self, timeout=None):
            return json.dumps({"status": "passed"}), ""

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: Process())
    row = atlas.execute_job(
        {"id": "qft-4q", "family": "QFT", "qubits": 4},
        "cirq-routecqc-maponly-v1",
        "line",
        7,
        dict(os.environ),
    )
    assert row["status"] == "error"
    assert "identity" in row["error"]
