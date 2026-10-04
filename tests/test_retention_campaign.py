import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from retention_fixtures import finish_fixture, simulate

import atlas
import build_site
import campaign as legacy
import publication
import retention as h
import retention_campaign as campaign


@pytest.fixture
def workspace(tmp_path):
    root = campaign.create(
        tmp_path / "campaigns",
        prepare_only=True,
        identities=[h.Job("qft-4q", "qiskit-l2", "line", 7)],
    )
    return root, campaign.validate_workspace(root)


@pytest.fixture(scope="module")
def measured(tmp_path_factory):
    root = campaign.create(
        tmp_path_factory.mktemp("retention-real"),
        prepare_only=True,
        identities=[h.Job("qft-4q", config, "line", 7) for config in ("qiskit-l1", "qiskit-l2")],
    )
    run = subprocess.run(
        [sys.executable, str(root / "atlas.py"), "retention-run"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert run.returncode == 0, run.stderr
    return root


def test_schedule_frozen_and_origin_authenticated(tmp_path):
    first = campaign.create(tmp_path / "campaigns", prepare_only=True)
    second = campaign.create(tmp_path / "campaigns", prepare_only=True)
    a, b = campaign.validate_workspace(first), campaign.validate_workspace(second)
    assert a["schedule"] == b["schedule"]
    assert len(a["schedule"]) == 18 and len(a["execution_identities"]) == 18
    assert a["shuffle_seed"] == 20261004
    assert a["policy"] == campaign.policy()
    assert a["origin"]["purpose"] == "historical-timeout-diagnostic"
    assert a["source_inventory"]["uv.lock"] == legacy.digest(atlas.ROOT / "uv.lock")
    assert not (first / "RUN_STARTED").exists()
    assert not (first / "data/results.json").exists()
    with pytest.raises(ValueError, match="identities"):
        campaign.timeout_identities({"results": []})


def test_real_compile_check_seal_and_create_only(measured, monkeypatch):
    snapshot = legacy.validate_completed(measured)
    assert snapshot["seal_format_version"] == 3 and snapshot["potential_trials"] == 6
    raw = json.loads((measured / "data/results.json").read_text())
    assert all(r["status"] == "passed" for r in raw["results"])
    assert all(
        r["coverage"] == {"compiled": 3, "required_repeats": 3, "accepted_repeats": 3}
        for r in raw["results"]
    )
    for index in range(2):
        directory = measured / campaign.job_prefix(campaign.validate_workspace(measured), index)
        timeline = [
            json.loads(line)
            for line in (directory / "compile.timeline.jsonl").read_text().splitlines()
        ]
        commits = [e for e in timeline if e["event"] == "compile_committed"]
        start = json.loads((directory / "r0.verification-start.json").read_text())
        assert len(commits) == 3
        assert max(e["monotonic_ns"] for e in commits) < start["monotonic_ns"]
        for repeat in range(3):
            process = json.loads((directory / f"check-r{repeat}.process.json").read_text())
            assert not process["members_after_cleanup"]
            assert not h._members(process["pid"])
            assert not Path(f"/proc/{process['pid']}").exists()
    with pytest.raises(FileExistsError):
        campaign.finish(measured, raw)
    rerun = subprocess.run(
        [sys.executable, str(measured / "atlas.py"), "retention-run"],
        cwd=measured,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert rerun.returncode != 0 and "FileExistsError" in rerun.stderr
    monkeypatch.setattr(h, "_check_child", lambda *args: pytest.fail("Seal re-ran QCEC"))
    campaign.validate_completed(measured)


@pytest.mark.parametrize(
    "mode,status,saved",
    [
        ("timeout", "verification_incomplete", 3),
        ("returned", "verification_incomplete", 3),
        ("passed", "passed", 3),
        ("unknown", "error", 3),
        ("not_equivalent", "not_equivalent", 3),
        ("mixed", "not_equivalent", 3),
        ("bad_acceptance", "error", 3),
        ("invalid_criterion", "error", 3),
        ("early_reply", "error", 3),
        ("invalid_clock", "error", 3),
        ("crash", "error", 3),
        ("invalid_reply", "error", 3),
        ("late_reply", "verification_incomplete", 3),
        ("compile_partial", "compile_incomplete", 2),
        ("save_failure", "error", 1),
        ("compile_error", "error", 0),
        ("manifest_failure", "error", 0),
    ],
)
def test_terminal_failures_keep_raw_and_can_be_sealed(workspace, monkeypatch, mode, status, saved):
    root, spec = workspace
    report, _ = simulate(root, spec, monkeypatch, mode)
    assert (report.status, report.saved) == (status, saved)
    raw = finish_fixture(root, spec)
    row = raw["results"][0]
    assert row["coverage"]["compiled"] == saved
    assert (row["compile_ms"] is not None) == (saved > 0)
    assert row["status"] == status
    campaign.validate_completed(root)
    if mode == "manifest_failure":
        files = campaign.validate_completed(root)["files"]
        prefix = campaign.job_prefix(spec, 0)
        assert f"{prefix}/r0.qasm" in files and f"{prefix}/r0.qpy" in files
        assert f"{prefix}/r0.compile.json" not in files
        assert any(name.startswith(f"{prefix}/r0.compile.json.pending-") for name in files)
    if mode in {"bad_acceptance", "invalid_criterion", "early_reply", "invalid_clock"}:
        assert all(t["verification"]["reason"] == "invalid_reply" for t in row["trials"])
        assert not any(t["validation"]["accepted"] for t in row["trials"])
    if mode == "mixed":
        assert [t["verification"]["state"] for t in row["trials"]] == [
            "not_equivalent",
            "verification_incomplete",
            "passed",
        ]
        assert row["coverage"]["accepted_repeats"] == 1
    if mode == "unknown":
        assert all(t["verification"]["reason"] == "unknown_criterion" for t in row["trials"])
    if mode == "late_reply":
        assert not any(t["validation"]["accepted"] for t in row["trials"])
        assert (
            f"{campaign.job_prefix(spec, 0)}/r0.reply.json"
            in campaign.validate_completed(root)["files"]
        )


def test_remaining_budget_is_shared_and_zero_does_not_spawn(workspace, monkeypatch):
    root, spec = workspace
    report, spawned = simulate(root, spec, monkeypatch, "remaining")
    assert report.status == "verification_incomplete"
    assert [name for name, _ in spawned] == ["compile", "check-r0"]
    assert spawned[1][1] == 10
    raw = finish_fixture(root, spec)
    row = raw["results"][0]
    assert row["wall_seconds"] == 420
    assert [t["verification"]["reason"] for t in row["trials"]] == [
        "hard_timeout",
        "job_budget",
        "job_budget",
    ]
    assert [t["verification"]["effective_budget_seconds"] for t in row["trials"]] == [10, 0, 0]


@pytest.mark.parametrize("name", ["retention.py", "data/inputs/qft-4q.qasm", "origin/results.json"])
def test_frozen_bytes_cannot_change(workspace, name):
    root, _ = workspace
    with (root / name).open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(ValueError, match="hash"):
        campaign.validate_workspace(root)


@pytest.mark.parametrize(
    "name",
    [
        "r0.qasm",
        "r0.qpy",
        "r0.compile.json",
        "result.json",
        "check-r0.stderr.log",
        "data/results.json",
    ],
)
def test_sealed_evidence_tamper_refused(measured, tmp_path, name):
    root = tmp_path / "seal-copy"
    shutil.copytree(measured, root)
    path = (
        root / name
        if name.startswith("data/")
        else root / campaign.job_prefix(campaign.validate_workspace(root), 0) / name
    )
    with path.open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(ValueError, match="hash"):
        campaign.validate_completed(root)


def test_before_seal_rederive_medians_status_and_qpy_phase(workspace, monkeypatch):
    root, spec = workspace
    simulate(root, spec, monkeypatch)
    path = root / campaign.job_prefix(spec, 0) / "result.json"
    result = json.loads(path.read_text())
    result["status"] = "passed"
    path.write_text(json.dumps(result))
    with pytest.raises(ValueError, match="rollup"):
        campaign.reconstruct(root, spec, 0)
    assert not (root / campaign.MARKER).exists()


def test_incomplete_schedule_and_orphan_inventory(workspace, monkeypatch):
    root, spec = workspace
    started = {
        "created_at": "test",
        "campaign_sha256": legacy.digest(root / "campaign.json"),
        "affinity": spec["planned_affinity"],
        "thread_env": spec["thread_env"],
    }
    h._json(root / "RUN_STARTED", started)
    h._durable(root / "data/run.jsonl", b"")
    with pytest.raises(ValueError, match="Incomplete schedule"):
        campaign.finish(root, campaign._document(spec, [], started))
    assert not (root / campaign.MARKER).exists()
    assert not (root / "data/results.json").exists()
    # A failed save may leave bytes, but they are never promoted to measurements.
    simulate(root, spec, monkeypatch, "compile_error")
    orphan = root / campaign.job_prefix(spec, 0) / "r0.qasm"
    h._durable(orphan, b"uncommitted forensic orphan")
    row = campaign.reconstruct(root, spec, 0)
    assert row["coverage"]["compiled"] == 0
    assert row["metrics"] is None
    assert f"{campaign.job_prefix(spec, 0)}/r0.qasm" in campaign._inventory(root)


def test_exact_filemap_and_portable_native_artifact_links(measured, tmp_path):
    snapshot = campaign.validate_completed(measured)
    root = tmp_path / "published"
    root.mkdir()
    names = set(snapshot["files"]) | {campaign.MARKER, campaign.SNAPSHOT}
    mapping = {}
    for name in names:
        destination = "data/campaigns/test/results.json" if name == "data/results.json" else name
        path = root / destination
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(measured / name, path)
        mapping[name] = destination
    file_map = "data/campaigns/test/file-map.json"
    h._json(root / file_map, mapping)
    h._json(
        root / "publication.json", {"campaign_id": snapshot["campaign_id"], "file_map": file_map}
    )
    raw, path = publication.load(root)
    assert path == "data/campaigns/test/results.json"
    assert raw["kind"] == campaign.KIND
    altered = copy.deepcopy(mapping)
    altered.pop(raw["results"][0]["trials"][0]["qpy_artifact"])
    (root / file_map).write_text(json.dumps(altered))
    with pytest.raises((KeyError, ValueError)):
        publication.load(root)
    altered = {**mapping, "extra": "atlas.py"}
    (root / file_map).write_text(json.dumps(altered))
    with pytest.raises(ValueError, match="exactly"):
        publication.load(root)


def test_seal_refuses_jobs_before_campaign_start(measured, tmp_path):
    root = tmp_path / "invalid-start-copy"
    shutil.copytree(measured, root)
    raw = json.loads((root / "data/results.json").read_text())
    for name in (campaign.MARKER, campaign.SNAPSHOT, "data/results.json"):
        (root / name).unlink()
    spec = campaign.validate_workspace(root)
    first = json.loads((root / campaign.job_prefix(spec, 0) / "spec.json").read_text())
    started_path = root / "RUN_STARTED"
    started = json.loads(started_path.read_text())
    started["monotonic_ns"] = int((first["start_monotonic"] + 1) * 1e9)
    started_path.write_text(json.dumps(started))
    with pytest.raises(ValueError, match="overlap or precede"):
        campaign.finish(root, raw)
    assert not (root / campaign.MARKER).exists()


def test_preview_build_preserves_seal_and_raw(measured, tmp_path):
    before = (measured / "data/results.json").read_bytes()
    destination = campaign.preview(measured, tmp_path / "preview")
    assert (destination / "index.html").exists()
    campaign.validate_completed(destination)
    assert (measured / "data/results.json").read_bytes() == before
    raw = json.loads(before)
    display, _ = build_site.display_data(raw)
    assert display["score_version"] == campaign.SCORE_VERSION
    assert raw["results"] == json.loads(before)["results"]
    with pytest.raises(FileExistsError):
        campaign.preview(measured, destination)


def test_new_source_and_budget_change_execution_identity(workspace):
    _, spec = workspace
    job = h.Job(**spec["schedule"][0])
    before = campaign.identity(spec, job)
    for key in ("source_inventory", "versions", "policy"):
        changed = copy.deepcopy(spec)
        changed[key]["test"] = "changed"
        assert campaign.identity(changed, job) != before


def test_protected_destinations_and_invalid_schedule(workspace, tmp_path):
    with pytest.raises(ValueError, match="Protected"):
        campaign.create(atlas.ROOT / "data")
    with pytest.raises(ValueError, match="duplicate"):
        campaign.create(
            tmp_path / "duplicate", identities=[h.Job("qft-4q", "qiskit-l2", "line", 7)] * 2
        )
    with pytest.raises(ValueError, match="Unknown input"):
        campaign.create(tmp_path / "bad", identities=[h.Job("qft-4q", "qiskit-l2", "invalid", 7)])
    assert os.sched_getaffinity(0)
