import copy
import json
import os
import subprocess
import sys

import pytest
from publication_fixtures import qmap_publication_map

import atlas
import build_site
import campaign


@pytest.fixture
def workspace(tmp_path):
    return campaign.create(
        tmp_path / "campaigns",
        prepare_only=True,
        inherited_file_map=qmap_publication_map(atlas.ROOT),
    )


def synthetic_document(root):
    """Test-only unmeasured error outcomes, never a published measurement fixture."""
    spec = json.loads((root / "campaign.json").read_text())
    historical = json.loads((atlas.ROOT / "data/results.json").read_text())
    doc = copy.deepcopy(historical)
    doc.update(
        suite=atlas.MEASUREMENT_SUITE,
        campaign_id=spec["campaign_id"],
        source_commit=spec["source_commit"],
        cases=spec["cases"],
    )
    doc["protocol"].update(
        configurations=atlas.MEASURED_CONFIGURATIONS,
        compilers=["cirq"],
        sdk_packages={"cirq": "cirq-core"},
        worker_timeout_seconds=atlas.WORKER_TIMEOUT_SECONDS,
        seeds=atlas.SEEDS,
        timing_repeats=atlas.REPEATS,
        cirq_pipeline=atlas.configuration_for("cirq-routecqc-maponly-v1")["recipe"],
        cirq_seed_note="Unseeded independent slots",
    )
    for field in (
        "timeout_retry_entries",
        "initial_worker_timeout_seconds",
        "initial_attempt_snapshot",
    ):
        doc["protocol"].pop(field, None)
    doc["results"] = [
        {
            "case_id": case["id"],
            "family": case["family"],
            "qubits": case["qubits"],
            "configuration_id": config["id"],
            "compiler": config["compiler"],
            "seed_supported": config["seed_supported"],
            "target": target,
            "seed": seed,
            "worker_timeout_seconds": atlas.WORKER_TIMEOUT_SECONDS,
            "status": "error",
            "error": "Synthetic test fixture, not measured",
        }
        for case in spec["cases"]
        for config in atlas.MEASURED_CONFIGURATIONS
        for target in ("line", "all-to-all")
        for seed in atlas.SEEDS
    ]
    doc["environment"]["versions"]["cirq-core"] = "1.7.0"
    (root / "RUN_STARTED").write_text("test-only\n")
    (root / "data/run.jsonl").write_text("test-only\n")
    return doc


def test_prepare_create_only_and_fixed_spec(workspace):
    spec = campaign.validate_workspace(workspace)
    assert spec["suite"] == atlas.SUITE
    from publication import load

    inherited, _ = load(atlas.ROOT, file_map=qmap_publication_map(atlas.ROOT))
    assert (
        spec["configurations"]
        == inherited["protocol"]["configurations"] + atlas.MEASURED_CONFIGURATIONS
    )
    assert len(spec["measurement_configurations"]) == 1
    assert spec["measured_entries"] == 72
    assert spec["worker_timeout_seconds"] == atlas.WORKER_TIMEOUT_SECONDS == 420
    assert not (workspace / "RUN_STARTED").exists()
    assert not (workspace / "data/results.json").exists()
    assert (workspace / "history/pilot-v0.4/data/results.json").read_bytes() == (
        atlas.ROOT / "data/results.json"
    ).read_bytes()
    assert "../history/pilot-v0.4/data/" in (workspace / "docs/pilot.md").read_text()


def test_builder_refuses_incomplete_workspace(workspace, monkeypatch):
    monkeypatch.setattr(build_site, "ROOT", workspace)
    doc = synthetic_document(workspace)
    (workspace / "data/results.json").write_text(json.dumps(doc))
    with pytest.raises(ValueError):
        build_site.build()
    assert not (workspace / "index.html").exists()


def test_seal_rebuild_hash_and_closed_links(workspace, monkeypatch):
    doc = synthetic_document(workspace)
    campaign.finish(workspace, doc)
    snapshot = campaign.validate_completed(workspace)
    assert snapshot["worker_timeout_seconds"] == atlas.WORKER_TIMEOUT_SECONDS
    assert snapshot["seal_format_version"] == 2
    assert snapshot["measured_entries"] == 72
    from publication import load

    inherited, _ = load(atlas.ROOT, file_map=qmap_publication_map(atlas.ROOT))
    assert snapshot["reused_entries"] == len(inherited["results"])
    raw = (workspace / "data/results.json").read_bytes()
    with pytest.raises(FileExistsError):
        campaign.finish(workspace, doc)
    monkeypatch.setattr(build_site, "ROOT", workspace)
    build_site.build()
    first = (workspace / "index.html").read_bytes()
    notes = json.loads((workspace / "data/configuration-notes.json").read_text())
    combined = json.loads(raw)
    legacy = json.loads((atlas.ROOT / "data/results.json").read_text())
    assert combined["results"][:792] == legacy["results"]
    assert "worker_timeout_seconds" not in combined["protocol"]
    assert combined["protocol"]["measurement_sources"]["v0.4"]["protocol"] == legacy["protocol"]
    assert notes["campaign_id"] == doc["campaign_id"]
    assert notes["raw_sha256"] == campaign.digest(workspace / "data/results.json")
    build_site.build()
    assert (workspace / "data/results.json").read_bytes() == raw
    assert (workspace / "index.html").read_bytes() == first
    assert "Generated by build_site.py" in first.decode()
    assert (workspace / "docs/qmap.html").exists()
    (workspace / "qmap_adapter.py").write_text("corrupted")
    with pytest.raises(ValueError, match="hash"):
        build_site.build()


@pytest.mark.parametrize(
    "arguments", [["run", "--prepare-only"], ["campaign", "--into", "ignored", "--overwrite"]]
)
def test_cli_refuses_ambiguous_or_unsafe_flags(arguments):
    result = subprocess.run(
        [sys.executable, str(atlas.ROOT / "atlas.py"), *arguments], capture_output=True, text=True
    )
    assert result.returncode == 2
    assert "error:" in result.stderr


def test_protocol_budget_cannot_be_relabeled(workspace):
    doc = synthetic_document(workspace)
    doc["protocol"]["worker_timeout_seconds"] = 600
    with pytest.raises(ValueError, match="protocol"):
        campaign.finish(workspace, doc)
    assert not (workspace / "data/results.json").exists()


def test_reject_duplicate_missing_budget_and_unsafe_paths(workspace):
    doc = synthetic_document(workspace)
    doc["results"].pop()
    with pytest.raises(ValueError, match="incomplete"):
        campaign.finish(workspace, doc)
    for path in ("../escape", "/absolute", "data/../atlas.py", "data\\input"):
        with pytest.raises(ValueError):
            campaign.relative_file(workspace, path)
    (workspace / "bad").symlink_to(workspace / "atlas.py")
    with pytest.raises(ValueError):
        campaign.relative_file(workspace, "bad")
    assert not (workspace / "MEASUREMENT_COMPLETE").exists()


def test_artifact_directory_cannot_escape_through_symlink(workspace, monkeypatch):
    outside = workspace.parent / "outside"
    outside.mkdir()
    (workspace / "data/outputs").rename(workspace / "data/outputs-saved")
    (workspace / "data/outputs").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(atlas, "ROOT", workspace)
    case = next(c for c in campaign.input_cases(workspace) if c["id"] == "qft-4q")
    with pytest.raises(ValueError, match="Symlink artifact"):
        atlas.worker(case, "qmap-sc-heuristic-maponly-v1", "line", 7)
    assert list(outside.iterdir()) == []


def test_real_subprocess_reads_copied_source_and_writes_only_own_artifacts(workspace, monkeypatch):
    (workspace / "RUN_STARTED").write_text("test\n")
    monkeypatch.setattr(atlas, "ROOT", workspace)
    case = next(c for c in campaign.input_cases(workspace) if c["id"] == "qft-4q")
    result = atlas.execute_job(case, "cirq-routecqc-maponly-v1", "line", 7, dict(os.environ))
    assert result["status"] == "passed"
    campaign.validate_record(workspace, result, case, "cirq-routecqc-maponly-v1", "line", 7)
    assert len(result["trials"]) == 3
    assert result["worker_timeout_seconds"] == 420
    assert sys.executable
    for trial in result["trials"]:
        assert (workspace / trial["artifact"]).is_file()
        assert "global_phase" in trial
