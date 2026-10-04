"""Measure a Cirq cohort and reuse authenticated v0.4 and QMAP v1 bytes."""

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
    "cirq_adapter.py",
    "publication.py",
    "campaign.py",
    "mixed_sources.py",
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
    for name in ("qiskit", "mqt.qcec", "mqt.qmap", "cirq"):
        importlib.import_module(name)
    if importlib.metadata.version("mqt.qmap") != "3.10.0":
        raise ValueError("This recipe requires QMAP 3.10.0")
    if importlib.metadata.version("cirq-core") != "1.7.0":
        raise ValueError("This recipe requires Cirq 1.7.0")
    return {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()}


def create(into, *, prepare_only=False, inherited_file_map=None):
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
    from publication import load

    selected_map = inherited_file_map
    if selected_map is None:
        selected_map = json.loads(relative_file(source, "publication.json").read_text())["file_map"]
    inherited, _ = load(source, file_map=selected_map)
    owned = {c["id"] for c in inherited["protocol"]["configurations"]}
    if inherited["cases"] != cases:
        raise ValueError("Published frozen inputs changed")
    if owned & {c["id"] for c in atlas.MEASURED_CONFIGURATIONS}:
        raise ValueError(
            "Inherited source already owns the measured configuration; "
            "specify another sealed FileMap"
        )
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
    mapping = json.loads(relative_file(source, selected_map).read_text())
    for name, physical in mapping.items():
        old = relative_file(source, physical)
        destinations = [root / "history/pilot-v0.5" / name]
        # Byte-identical aliases retain old report links, not executable imports.
        if name.startswith("history/pilot-v0.4/"):
            destinations.append(root / name)
        if name.startswith("history/pilot-v0.4/data/attempts/"):
            destinations.append(root / name.removeprefix("history/pilot-v0.4/"))
        for new in destinations:
            new.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(old, new)
    for row in inherited["results"]:
        for trial in row.get("trials", []):
            old = relative_file(source, trial["artifact"])
            new = root / trial["artifact"]
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
        "spec_format_version": 2,
        "inherited_seal_sha256": digest(root / "history/pilot-v0.5/MEASUREMENT_COMPLETE"),
        "campaign_id": identifier,
        "suite": atlas.SUITE,
        "measurement_suite": atlas.MEASUREMENT_SUITE,
        "worker_timeout_seconds": atlas.WORKER_TIMEOUT_SECONDS,
        "configurations": inherited["protocol"]["configurations"] + atlas.MEASURED_CONFIGURATIONS,
        "measurement_configurations": atlas.MEASURED_CONFIGURATIONS,
        "measured_entries": len(cases) * len(atlas.MEASURED_CONFIGURATIONS) * 2 * len(atlas.SEEDS),
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
    predecessor_name = "history/pilot-v0.5/campaign.json"
    predecessor_path = relative_file(root, predecessor_name)
    if digest(predecessor_path) != spec["files"][predecessor_name]:
        raise ValueError("Campaign predecessor specification changed")
    predecessor = json.loads(predecessor_path.read_text())
    if (
        spec.get("spec_format_version") != 2
        or spec["suite"] != atlas.SUITE
        or spec["measurement_suite"] != atlas.MEASUREMENT_SUITE
        or spec["measurement_configurations"] != atlas.MEASURED_CONFIGURATIONS
        or spec["worker_timeout_seconds"] != atlas.WORKER_TIMEOUT_SECONDS
        or spec["configurations"] != predecessor["configurations"] + atlas.MEASURED_CONFIGURATIONS
        or spec["seeds"] != atlas.SEEDS
        or spec["timing_repeats"] != atlas.REPEATS
        or spec["campaign_id"] != root.name
    ):
        raise ValueError("Campaign settings do not match execution source")
    for name, expected in spec["files"].items():
        if (
            not name.startswith(("history/", "data/outputs/"))
            and digest(relative_file(root, name)) != expected
        ):
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
        or configuration not in {c["id"] for c in atlas.MEASURED_CONFIGURATIONS}
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
        if (
            sorted(trial["initial_map"]) != list(range(case["qubits"]))
            or sorted(trial["final_map"]) != list(range(case["qubits"]))
            or not isinstance(trial["global_phase"], (int, float))
        ):
            raise ValueError("Worker map or phase mismatch")
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
        for config in atlas.MEASURED_CONFIGURATIONS
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
        or document["suite"] != spec["measurement_suite"]
        or document["cases"] != spec["cases"]
        or document["protocol"]["configurations"] != spec["measurement_configurations"]
        or document["protocol"]["seeds"] != spec["seeds"]
        or document["protocol"]["timing_repeats"] != spec["timing_repeats"]
    ):
        raise ValueError("Snapshot protocol mismatch")
    cases = {case["id"]: case for case in spec["cases"]}
    for row in document["results"]:
        validate_record(
            root, row, cases[row["case_id"]], row["configuration_id"], row["target"], row["seed"]
        )
    for name, expected_hash in spec["files"].items():
        if digest(relative_file(root, name)) != expected_hash:
            raise ValueError(f"Inherited/source bytes changed: {name}")
    from mixed_sources import combine, validate_combined

    standalone = "data/cirq-results.json"
    exclusive_json(root / standalone, document)
    combined = combine(root, document)
    validate_combined(root, combined)
    # A hard link publishes a complete temp file without replacing an existing snapshot.
    temporary = root / "data/results.pending"
    exclusive_json(temporary, combined)
    os.link(temporary, root / "data/results.json")
    temporary.unlink()
    files = {
        **spec["files"],
        "campaign.json": digest(root / "campaign.json"),
        "RUN_STARTED": digest(root / "RUN_STARTED"),
        "data/results.json": digest(root / "data/results.json"),
        standalone: digest(root / standalone),
        "data/run.jsonl": digest(root / "data/run.jsonl"),
    }
    for row in document["results"]:
        for trial in row.get("trials", []):
            files[trial["artifact"]] = trial["artifact_sha256"]
    snapshot = {
        "seal_format_version": 2,
        "kind": "cirq-mixed",
        "campaign_id": spec["campaign_id"],
        "suite": atlas.SUITE,
        "measurement_suite": atlas.MEASUREMENT_SUITE,
        "measured_entries": len(document["results"]),
        "reused_entries": combined["protocol"]["reused_entries"],
        "worker_timeout_seconds": atlas.WORKER_TIMEOUT_SECONDS,
        "files": files,
    }
    exclusive_json(root / "snapshot-manifest.json", snapshot)
    with (root / "MEASUREMENT_COMPLETE").open("x") as stream:
        stream.write(digest(root / "snapshot-manifest.json") + "\n")


def validate_completed(root, resolve=None):
    root = Path(root)
    resolve = resolve or (lambda name: relative_file(root, name))
    marker = resolve("MEASUREMENT_COMPLETE").read_text().strip()
    if marker != digest(resolve("snapshot-manifest.json")):
        raise ValueError("Measurement seal mismatch")
    snapshot = json.loads(resolve("snapshot-manifest.json").read_text())
    version = snapshot.get("seal_format_version", 1)
    if version not in {1, 2} or (version == 2 and snapshot.get("kind") != "cirq-mixed"):
        raise ValueError("Unknown seal format")
    for name, expected in snapshot["files"].items():
        if digest(resolve(name)) != expected:
            raise ValueError(f"Snapshot hash mismatch: {name}")
    from mixed_sources import validate_combined

    raw = json.loads(resolve("data/results.json").read_text())
    qmap = validate_combined(root, raw, resolve)
    spec = json.loads(resolve("campaign.json").read_text())
    if spec.get("spec_format_version", 1) != version:
        raise ValueError("Spec/seal format mismatch")
    budget_key = "worker_timeout_seconds" if version == 2 else "qmap_worker_timeout_seconds"
    if not (
        raw["campaign_id"] == snapshot["campaign_id"] == spec["campaign_id"]
        and raw["suite"] == snapshot["suite"] == spec["suite"]
        and qmap["protocol"]["worker_timeout_seconds"]
        == snapshot[budget_key]
        == spec["worker_timeout_seconds"]
        and qmap["suite"] == snapshot["measurement_suite"] == spec["measurement_suite"]
        and len(qmap["results"]) == snapshot["measured_entries"] == spec["measured_entries"]
    ):
        raise ValueError("Snapshot provenance mismatch")
    return snapshot
