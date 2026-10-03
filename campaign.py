"""Create-only, self-contained campaign workspaces. Never reuse historical records."""

import hashlib
import importlib
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

SOURCE_FILES = (
    "atlas.py",
    "qmap_adapter.py",
    "campaign.py",
    "build_site.py",
    "pyproject.toml",
    "uv.lock",
    "package.json",
    "package-lock.json",
)
THREAD_NAMES = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "RAYON_NUM_THREADS",
    "QISKIT_NUM_PROCS",
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_file(root, name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts or "\\" in name or str(path) != name:
        raise ValueError("Unsafe relative path")
    candidate = root / name
    if any(part.is_symlink() for part in [candidate, *candidate.parents] if part != root.parent):
        raise ValueError("Symlink is not allowed")
    if not candidate.resolve().is_relative_to(root.resolve()) or not candidate.is_file():
        raise ValueError("Missing or escaping file")
    return candidate


def exclusive_json(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def input_cases(root):
    cases = json.loads(relative_file(root, "data/manifest.json").read_text())
    if len(cases) != 12 or len({case["id"] for case in cases}) != 12:
        raise ValueError("Expected twelve frozen inputs")
    for case in cases:
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", case["id"]) or case["qubits"] < 1:
            raise ValueError("Invalid case identity")
        if case["path"] != f"data/inputs/{case['id']}.qasm":
            raise ValueError("Unexpected input location")
        if digest(relative_file(root, case["path"])) != case["sha256"]:
            raise ValueError("Frozen input hash mismatch")
        for field, hash_field in [("source_path", "source_sha256")]:
            provenance = case.get("provenance", {})
            if (
                field in provenance
                and digest(relative_file(root, provenance[field])) != provenance[hash_field]
            ):
                raise ValueError("Corpus provenance mismatch")
        if "license_path" in case.get("provenance", {}):
            relative_file(root, case["provenance"]["license_path"])
    return cases


def preflight():
    for name in ("qiskit", "pytket", "bqskit", "mqt.qcec", "mqt.qmap"):
        importlib.import_module(name)
    if importlib.metadata.version("mqt.qmap") != "3.10.0":
        raise ValueError("This recipe requires QMAP 3.10.0")
    return {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()}


def create(into, *, prepare_only=False):
    import atlas

    source = atlas.ROOT.resolve()
    into = Path(into).absolute()
    if into.is_symlink() or any(parent.is_symlink() for parent in into.parents):
        raise ValueError("Symlink destination is not allowed")
    resolved = into.resolve()
    protected = source.with_name("transpiler-atlas")
    if resolved.is_relative_to(protected) or any(
        resolved.is_relative_to(source / name)
        for name in ("data", "releases", "web", "docs", ".venv")
    ):
        raise ValueError("Protected destination")
    cases = input_cases(source)
    versions = preflight()
    into.mkdir(parents=True, exist_ok=True)
    identifier = f"{atlas.SUITE}-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4()}"
    root = into / identifier
    root.mkdir()
    for name in SOURCE_FILES:
        shutil.copyfile(relative_file(source, name), root / name)
    for name in ("web", "docs", "corpora"):
        for file in sorted((source / name).rglob("*")):
            if file.is_file() and (name != "docs" or file.suffix == ".md"):
                old = relative_file(source, str(file.relative_to(source)))
                new = root / file.relative_to(source)
                new.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(old, new)
    (root / "data/inputs").mkdir(parents=True)
    shutil.copyfile(source / "data/manifest.json", root / "data/manifest.json")
    for case in cases:
        shutil.copyfile(source / case["path"], root / case["path"])
    # Historical documentation remains truthful without linking old text to new measurements.
    history = root / "history/pilot-v0.4/data"
    for file in sorted((source / "data").rglob("*")):
        if file.is_file():
            old = relative_file(source, str(file.relative_to(source)))
            new = history / file.relative_to(source / "data")
            new.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(old, new)
    for name in ("pilot.md", "bqskit.md"):
        path = root / "docs" / name
        path.write_text(path.read_text().replace("(../data/", "(../history/pilot-v0.4/data/"))
    files = {
        str(file.relative_to(root)): digest(file)
        for file in sorted(root.rglob("*"))
        if file.is_file()
    }
    commit = subprocess.check_output(
        ["git", "--no-optional-locks", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    spec = {
        "campaign_id": identifier,
        "suite": atlas.SUITE,
        "worker_timeout_seconds": atlas.WORKER_TIMEOUT_SECONDS,
        "configurations": atlas.CONFIGURATIONS,
        "seeds": atlas.SEEDS,
        "timing_repeats": atlas.REPEATS,
        "cases": cases,
        "versions": versions,
        "source_commit": commit,
        "files": files,
        "source_inventory": {name: digest(source / name) for name in SOURCE_FILES},
    }
    exclusive_json(root / "campaign.json", spec)
    if not prepare_only:
        command = [sys.executable, str(root / "atlas.py"), "run"]
        with subprocess.Popen(command, cwd=root) as execution:
            try:
                code = execution.wait()
            except BaseException:
                execution.terminate()  # copied runner relays cancellation to its worker group
                try:
                    execution.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    execution.kill()
                    execution.wait()
                raise
        if code:
            raise subprocess.CalledProcessError(code, command)
    return root


def validate_workspace(root):
    import atlas

    root = Path(root).resolve()
    spec = json.loads(relative_file(root, "campaign.json").read_text())
    if (
        spec["suite"] != atlas.SUITE
        or spec["worker_timeout_seconds"] != atlas.WORKER_TIMEOUT_SECONDS
        or spec["configurations"] != atlas.CONFIGURATIONS
        or spec["seeds"] != atlas.SEEDS
        or spec["timing_repeats"] != atlas.REPEATS
        or spec["campaign_id"] != root.name
    ):
        raise ValueError("Campaign settings do not match execution source")
    for name, expected in spec["files"].items():
        if not name.startswith("history/") and digest(relative_file(root, name)) != expected:
            raise ValueError(f"Campaign source/input hash mismatch: {name}")
    if spec["cases"] != input_cases(root):
        raise ValueError("Campaign input manifest changed")
    for package, version in spec["versions"].items():
        if importlib.metadata.version(package) != version:
            raise ValueError("Campaign dependency version changed")
    return spec


def validate_worker(root, case, configuration, target, seed):
    import atlas

    spec = validate_workspace(root)
    if not (root / "RUN_STARTED").is_file() or (root / "MEASUREMENT_COMPLETE").exists():
        raise ValueError("Campaign is not accepting workers")
    if (
        case not in spec["cases"]
        or configuration not in {c["id"] for c in atlas.CONFIGURATIONS}
        or target not in {"line", "all-to-all"}
        or seed not in atlas.SEEDS
    ):
        raise ValueError("Worker is outside the fixed schedule")


def validate_record(root, row, case, configuration, target, seed):
    import atlas

    identity = (case["id"], configuration, target, seed)
    if (
        tuple(row[k] for k in ("case_id", "configuration_id", "target", "seed")) != identity
        or row["worker_timeout_seconds"] != atlas.WORKER_TIMEOUT_SECONDS
    ):
        raise ValueError("Worker record identity/budget mismatch")
    configuration_spec = atlas.configuration_for(configuration)
    if (
        row["compiler"] != configuration_spec["compiler"]
        or row["seed_supported"] != configuration_spec["seed_supported"]
        or row["qubits"] != case["qubits"]
        or row["family"] != case["family"]
    ):
        raise ValueError("Worker metadata mismatch")
    if row["status"] in {"timeout", "error"}:
        if row.get("trials"):
            raise ValueError("Incomplete worker must not invent completed trials")
        return
    if (
        row["status"] not in {"passed", "verification_failed"}
        or len(row["trials"]) != atlas.REPEATS
    ):
        raise ValueError("Incomplete worker output")
    accepted = all(trial["validation"]["accepted"] for trial in row["trials"])
    if row["status"] != ("passed" if accepted else "verification_failed"):
        raise ValueError("Worker acceptance status mismatch")
    for repeat, trial in enumerate(row["trials"]):
        validation = trial["validation"]
        if validation["accepted"] != (
            validation["criterion"] in {"equivalent", "equivalent_up_to_global_phase"}
        ):
            raise ValueError("Worker strict acceptance mismatch")
        expected = f"data/outputs/{case['id']}-{target}-{configuration}-s{seed}-r{repeat}.qasm"
        if (
            trial["artifact"] != expected
            or digest(relative_file(root, expected)) != trial["artifact_sha256"]
        ):
            raise ValueError("Worker artifact mismatch")


def finish(root, document):
    import atlas

    if (root / "data/results.json").exists() or (root / "MEASUREMENT_COMPLETE").exists():
        raise FileExistsError("Campaign snapshots are create-only")
    spec = validate_workspace(root)
    expected = {
        (case["id"], config["id"], target, seed)
        for case in spec["cases"]
        for config in atlas.CONFIGURATIONS
        for target in ("line", "all-to-all")
        for seed in atlas.SEEDS
    }
    actual = [
        (r["case_id"], r["configuration_id"], r["target"], r["seed"]) for r in document["results"]
    ]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("Campaign schedule is incomplete or duplicated")
    if (
        document["protocol"]["worker_timeout_seconds"] != spec["worker_timeout_seconds"]
        or document["campaign_id"] != spec["campaign_id"]
        or document["suite"] != spec["suite"]
        or document["cases"] != spec["cases"]
        or document["protocol"]["configurations"] != spec["configurations"]
        or document["protocol"]["seeds"] != spec["seeds"]
        or document["protocol"]["timing_repeats"] != spec["timing_repeats"]
    ):
        raise ValueError("Snapshot protocol mismatch")
    cases = {case["id"]: case for case in spec["cases"]}
    for row in document["results"]:
        validate_record(
            root, row, cases[row["case_id"]], row["configuration_id"], row["target"], row["seed"]
        )
    # A hard link publishes a complete temp file without replacing an existing snapshot.
    temporary = root / "data/results.pending"
    exclusive_json(temporary, document)
    os.link(temporary, root / "data/results.json")
    temporary.unlink()
    files = {
        **spec["files"],
        "campaign.json": digest(root / "campaign.json"),
        "RUN_STARTED": digest(root / "RUN_STARTED"),
        "data/results.json": digest(root / "data/results.json"),
        "data/run.jsonl": digest(root / "data/run.jsonl"),
    }
    for row in document["results"]:
        for trial in row.get("trials", []):
            files[trial["artifact"]] = trial["artifact_sha256"]
    snapshot = {
        "campaign_id": spec["campaign_id"],
        "suite": atlas.SUITE,
        "worker_timeout_seconds": atlas.WORKER_TIMEOUT_SECONDS,
        "files": files,
    }
    exclusive_json(root / "snapshot-manifest.json", snapshot)
    with (root / "MEASUREMENT_COMPLETE").open("x") as stream:
        stream.write(digest(root / "snapshot-manifest.json") + "\n")


def validate_completed(root):
    root = Path(root)
    marker = relative_file(root, "MEASUREMENT_COMPLETE").read_text().strip()
    if marker != digest(relative_file(root, "snapshot-manifest.json")):
        raise ValueError("Measurement seal mismatch")
    snapshot = json.loads((root / "snapshot-manifest.json").read_text())
    for name, expected in snapshot["files"].items():
        if digest(relative_file(root, name)) != expected:
            raise ValueError(f"Snapshot hash mismatch: {name}")
    raw = json.loads((root / "data/results.json").read_text())
    spec = json.loads((root / "campaign.json").read_text())
    if not (
        raw["campaign_id"] == snapshot["campaign_id"] == spec["campaign_id"]
        and raw["suite"] == snapshot["suite"] == spec["suite"]
        and raw["protocol"]["worker_timeout_seconds"]
        == snapshot["worker_timeout_seconds"]
        == spec["worker_timeout_seconds"]
    ):
        raise ValueError("Snapshot provenance mismatch")
    return snapshot
