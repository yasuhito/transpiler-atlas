"""Create, measure and authenticate standalone compile-retention campaigns (v3).

No old rows are imported into results, no retry/resume and no archived code is
executed by the reader. A complete record of unsuccessful jobs can be sealed;
a missing scheduled terminal fact, corrupt native bundle or ambiguous fact cannot.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
import platform
import random
import re
import shutil
import signal
import statistics
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import retention as h
from campaign import SOURCE_FILES, THREAD_NAMES, digest, input_cases, relative_file

KIND = "compile-retention"
SUITE = "pilot-compile-retention-v1-420s-check60"
SHUFFLE_SEED = 20261004
SCORE_VERSION = "qcec-adjusted-partial-v2"
SOURCES = (*SOURCE_FILES, "retention.py", "retention_campaign.py")
MARKER = "MEASUREMENT_COMPLETE"
SNAPSHOT = "snapshot-manifest.json"
DERIVED = {"index.html", "data/configuration-notes.json"}


def json_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def versions():
    return {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()}


def policy():
    return {
        "repeats": h.REPEATS,
        "whole_job_seconds": h.JOB_SECONDS,
        "check_hard_seconds": h.CHECK_SECONDS,
        "qcec_cooperative_seconds": 20,
        "order": "compile-all-then-verify",
        "deadline_policy": "observed-exit-before-cutoff",
        "transport": "native-QPY",
        "kind": KIND,
        "protocol_version": 1,
    }


def identity(spec, job):
    configuration = next(c for c in spec["configurations"] if c["id"] == job.configuration_id)
    case = next(c for c in spec["cases"] if c["id"] == job.case_id)
    return json_hash(
        {
            "recipe": configuration,
            "job": asdict(job),
            "input_sha256": case["sha256"],
            "source_inventory": spec["source_inventory"],
            "versions": spec["versions"],
            "policy": spec["policy"],
            "checker_options": spec["protocol"]["checker_options"],
        }
    )


def timeout_identities(data):
    jobs = [
        h.Job(r["case_id"], r["configuration_id"], r["target"], r["seed"])
        for r in data["results"]
        if r["status"] == "timeout"
    ]
    expected = {
        h.Job("qasmbench-ising_n10", f"bqskit-l{level}", target, seed)
        for level in (2, 3, 4)
        for target in ("all-to-all", "line")
        for seed in (7, 19, 43)
    }
    if len(jobs) != 18 or set(jobs) != expected:
        raise ValueError("Published timeout identities differ from the approved 18 jobs")
    return sorted(jobs, key=lambda j: (j.case_id, j.configuration_id, j.target, j.seed))


def job_prefix(spec, ordinal):
    return f"data/jobs/{spec['campaign_id']}/{ordinal:04d}"


def _protocol(configurations, jobs):
    import atlas

    return {
        "kind": KIND,
        "protocol_version": 1,
        "score_version": SCORE_VERSION,
        "configurations": configurations,
        "compilers": sorted({c["compiler"] for c in configurations}),
        "sdk_packages": {c["compiler"]: atlas.SDK_PACKAGES[c["compiler"]] for c in configurations},
        "seeds": sorted({j.seed for j in jobs}),
        "ordered_schedule": [asdict(j) for j in jobs],
        "timing_repeats": 3,
        "reference_configuration": atlas.REFERENCE_CONFIGURATION,
        "worker_timeout_seconds": 420,
        "verification_hard_timeout_seconds": 60,
        "checker_options": {
            "run_simulation_checker": False,
            "run_zx_checker": False,
            "parallel": False,
            "nthreads": 1,
            "timeout": 20,
        },
        "basis": sorted(atlas.BASIS),
        "physical_qubits": "equal to input width",
        "timer": (
            "unchanged atlas.compile_once; excludes parse, export, checks "
            "and runtime setup/teardown"
        ),
        "qiskit_pipeline": "preset levels 0/1/2/3, approximation_degree=1.0",
        "bqskit_pipeline": {
            "optimization_levels": [1, 2, 3, 4],
            "max_synthesis_size": 2,
            "synthesis_epsilon": atlas.BQSKIT_EPSILON,
            "num_workers": 1,
            "num_blas_threads": 1,
            "with_mapping": True,
            "error_threshold": None,
        },
        "validation": (
            "strict native QPY with logical-to-physical maps and scalar phase; QCEC 3.10.1"
        ),
        "output_commit": "create-only QASM + QPY + manifest last, file and directory fsync",
        "cleanup": (
            "single parent-owned group, SIGKILL + direct wait + subreaper waitpid + group absence"
        ),
        "partial_raw": (
            "median of committed repeats, then seed medians, "
            "with coverage; no missing-case exclusion"
        ),
        "normalization": (
            "only where necessary raw and reference exist; unfinished verification alone is not N/A"
        ),
        "cold_worker": True,
    }


def _inventory(root):
    files = {}
    for file in sorted(root.rglob("*")):
        if file.is_symlink():
            raise ValueError("Symlink in campaign inventory")
        name = file.relative_to(root).as_posix()
        if (
            file.is_file()
            and name not in DERIVED | {MARKER, SNAPSHOT}
            and not (name.startswith("docs/") and file.suffix == ".html")
        ):
            if file.relative_to(root).parts[0] == "__pycache__" and file.suffix == ".pyc":
                continue  # interpreter cache, never measurement evidence
            files[name] = digest(relative_file(root, name))
    return files


def _copy(source, root, name, destination=None):
    new = root / (destination or name)
    new.parent.mkdir(parents=True, exist_ok=True)
    h._durable(new, relative_file(source, name).read_bytes())


def create(into, *, prepare_only=False, identities=None):
    """Freeze an explicit ordered schedule before running any measurement."""
    import atlas
    from publication import load

    source = atlas.ROOT.resolve()
    into = Path(into).absolute()
    if into.is_symlink() or any(p.is_symlink() for p in into.parents):
        raise ValueError("Symlink destination")
    if into.resolve().is_relative_to(source) or into.resolve().is_relative_to(
        source.with_name("transpiler-atlas")
    ):
        raise ValueError("Protected destination")
    data, raw_path = load(source)
    historical_jobs = timeout_identities(data)
    jobs = list(historical_jobs if identities is None else identities)
    if not jobs or len(jobs) != len(set(jobs)):
        raise ValueError("Empty or duplicate schedule")
    all_cases = input_cases(source)
    if data["cases"] != all_cases:
        raise ValueError("Published frozen inputs changed")
    case_by_id = {c["id"]: c for c in all_cases}
    configurations = [
        atlas.configuration_for(name) for name in sorted({j.configuration_id for j in jobs})
    ]
    for job in jobs:
        if (
            job.case_id not in case_by_id
            or type(job.seed) is not int
            or job.target not in {"line", "all-to-all"}
        ):
            raise ValueError("Unknown input or invalid seed")
        atlas.edges_for(case_by_id[job.case_id]["qubits"], job.target)
    if importlib.metadata.version("mqt.qcec") != "3.10.1":
        raise ValueError("This protocol requires locked QCEC 3.10.1")
    jobs.sort(key=lambda j: (j.case_id, j.configuration_id, j.target, j.seed))
    random.Random(SHUFFLE_SEED).shuffle(jobs)
    allowed = sorted(os.sched_getaffinity(0))
    campaign_id = f"{SUITE}-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4()}"
    root = into / campaign_id
    root.mkdir(parents=True, exist_ok=False)
    for name in SOURCES:
        _copy(source, root, name)
    for directory in ("web", "corpora", "docs"):
        for file in sorted((source / directory).rglob("*")):
            if file.is_file() and (directory != "docs" or file.suffix == ".md"):
                _copy(source, root, file.relative_to(source).as_posix())
    # Standalone protocol page has no links into an inherited campaign closure.
    (root / "docs/pilot.md").unlink()
    _copy(source, root, "docs/retention.md", "docs/pilot.md")
    (root / "data/inputs").mkdir(parents=True)
    (root / "data/jobs" / campaign_id).mkdir(parents=True)
    _copy(source, root, "data/manifest.json")
    for case in all_cases:
        _copy(source, root, case["path"])
    selector = json.loads((source / "publication.json").read_text())
    mapping = json.loads(relative_file(source, selector["file_map"]).read_text())
    for logical, physical in {
        "publication.json": "publication.json",
        "file-map.json": selector["file_map"],
        "results.json": raw_path,
        "legacy-results.json": "data/results.json",
        MARKER: mapping[MARKER],
        SNAPSHOT: mapping[SNAPSHOT],
    }.items():
        _copy(source, root, physical, "origin/" + logical)
    source_commit = subprocess.check_output(
        ["git", "--no-optional-locks", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    spec = {
        "spec_format_version": 3,
        "kind": KIND,
        "campaign_id": campaign_id,
        "suite": SUITE,
        "source_commit": source_commit,
        "source_clean": not bool(
            subprocess.check_output(
                ["git", "--no-optional-locks", "-C", str(source), "status", "--porcelain"],
                text=True,
            ).strip()
        ),
        "created_at": datetime.now(UTC).isoformat(),
        "policy": policy(),
        "shuffle_seed": SHUFFLE_SEED,
        "schedule": [asdict(j) for j in jobs],
        "cases": [case_by_id[name] for name in sorted({j.case_id for j in jobs})],
        "configurations": configurations,
        "protocol": _protocol(configurations, jobs),
        "versions": versions(),
        "planned_affinity": [allowed[0]],
        "thread_env": dict.fromkeys(THREAD_NAMES, "1"),
        "host": {
            "cpu": next(
                (
                    line.split(":", 1)[1].strip()
                    for line in Path("/proc/cpuinfo").read_text().splitlines()
                    if line.startswith("model name")
                ),
                "unknown",
            ),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "exclusive_machine": False,
            "memory_limit_enforced": False,
        },
        "origin": {
            "purpose": "historical-timeout-diagnostic"
            if identities is None
            else "explicit-standalone",
            "selector_path": "publication.json",
            "file_map_path": selector["file_map"],
            "raw_path": raw_path,
            "timeout_identities": [asdict(j) for j in historical_jobs],
        },
        "source_inventory": {name: digest(root / name) for name in SOURCES},
        "files": _inventory(root),
    }
    spec["execution_identities"] = [identity(spec, j) for j in jobs]
    # Persist all newly created directory links before publishing the fixed spec.
    for directory in [root.parent, root, *sorted(p for p in root.rglob("*") if p.is_dir())]:
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    h._json(root / "campaign.json", spec)
    validate_workspace(root)
    if not prepare_only:
        with subprocess.Popen(
            [sys.executable, str(root / "atlas.py"), "retention-run"], cwd=root
        ) as child:
            try:
                code = child.wait()
            except BaseException:
                child.terminate()
                child.wait()  # runner owns and cleans the active group before exiting
                raise
        if code:
            raise RuntimeError(
                f"Standalone run failed ({code}); unsealed evidence retained: {root}"
            )
    return root


def _read(resolve, name):
    return json.loads(resolve(name).read_text())


def validate_workspace(root, resolve=None):
    root = Path(root)
    resolve = resolve or (lambda name: relative_file(root, name))
    spec = _read(resolve, "campaign.json")
    if (
        spec["spec_format_version"] != 3
        or spec["kind"] != KIND
        or spec["suite"] != SUITE
        or spec["policy"] != policy()
        or spec["protocol"]["kind"] != KIND
    ):
        raise ValueError("Unknown or changed standalone protocol")
    if (
        not re.fullmatch(r"[a-zA-Z0-9_-]+", spec["campaign_id"])
        or not spec["campaign_id"].startswith(SUITE + "-")
        or not re.fullmatch(r"[0-9a-f]{40}", spec["source_commit"])
    ):
        raise ValueError("Invalid campaign/source identity")
    if spec["shuffle_seed"] != SHUFFLE_SEED:
        raise ValueError("Shuffle seed changed")
    if (
        spec["protocol"]["configurations"] != spec["configurations"]
        or spec["protocol"]["timing_repeats"] != 3
        or spec["protocol"]["worker_timeout_seconds"] != 420
        or spec["protocol"]["verification_hard_timeout_seconds"] != 60
        or spec["protocol"]["score_version"] != SCORE_VERSION
        or spec["protocol"]["checker_options"]
        != {
            "run_simulation_checker": False,
            "run_zx_checker": False,
            "parallel": False,
            "nthreads": 1,
            "timeout": 20,
        }
    ):
        raise ValueError("Standalone protocol budget/checker mismatch")
    if set(spec["source_inventory"]) != set(SOURCES):
        raise ValueError("Source inventory coverage mismatch")
    for name, sha in spec["files"].items():
        if digest(resolve(name)) != sha:
            raise ValueError(f"Frozen file hash mismatch: {name}")
    if any(spec["files"].get(name) != sha for name, sha in spec["source_inventory"].items()):
        raise ValueError("Source hash mismatch")
    qcec_versions = [
        v
        for k, v in spec["versions"].items()
        if k.lower().replace("-", ".").replace("_", ".") == "mqt.qcec"
    ]
    if qcec_versions != ["3.10.1"]:
        raise ValueError("QCEC verifier identity mismatch")
    jobs = [h.Job(**j) for j in spec["schedule"]]
    if not jobs or len(set(jobs)) != len(jobs):
        raise ValueError("Duplicate or missing scheduled jobs")
    canonical = sorted(jobs, key=lambda j: (j.case_id, j.configuration_id, j.target, j.seed))
    random.Random(SHUFFLE_SEED).shuffle(canonical)
    if (
        jobs != canonical
        or spec["protocol"]["ordered_schedule"] != spec["schedule"]
        or spec["execution_identities"] != [identity(spec, j) for j in jobs]
    ):
        raise ValueError("Schedule or execution identity mismatch")
    cases = _read(resolve, "data/manifest.json")
    case_by_id = {c["id"]: c for c in cases}
    if spec["cases"] != [case_by_id[name] for name in sorted({j.case_id for j in jobs})]:
        raise ValueError("Scheduled input identity mismatch")
    for case in cases:
        if digest(resolve(case["path"])) != case["sha256"]:
            raise ValueError("Input hash mismatch")
        p = case.get("provenance", {})
        if p and (
            digest(resolve(p["source_path"])) != p["source_sha256"]
            or not resolve(p["license_path"]).is_file()
        ):
            raise ValueError("Input provenance/license mismatch")
    origin_raw = _read(resolve, "origin/results.json")
    if origin_raw["cases"] != cases:
        raise ValueError("Origin frozen input manifest mismatch")
    historical = timeout_identities(origin_raw)
    if spec["origin"]["timeout_identities"] != [asdict(j) for j in historical]:
        raise ValueError("Origin identity mismatch")
    if spec["origin"]["purpose"] == "historical-timeout-diagnostic" and set(jobs) != set(
        historical
    ):
        raise ValueError("Historical timeout schedule mismatch")
    marker = resolve("origin/" + MARKER).read_text().strip()
    if marker != digest(resolve("origin/" + SNAPSHOT)):
        raise ValueError("Origin completion marker mismatch")
    origin_snapshot = _read(resolve, "origin/" + SNAPSHOT)
    origin_selector = _read(resolve, "origin/publication.json")
    origin_map = _read(resolve, "origin/file-map.json")
    if (
        origin_snapshot["files"]["data/results.json"] != digest(resolve("origin/results.json"))
        or origin_selector["file_map"] != spec["origin"]["file_map_path"]
        or origin_map["data/results.json"] != spec["origin"]["raw_path"]
    ):
        raise ValueError("Origin raw/selector/FileMap binding mismatch")
    return spec


def _finite(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(f"Invalid {name}")


def _process(fact, deadline):
    if fact["state"] == "not_started":
        if fact != {"state": "not_started", "wall_seconds": 0, "reason": "job_budget"}:
            raise ValueError("Invalid unstarted process fact")
        return
    if fact["state"] not in {"completed", "timeout"}:
        raise ValueError("Nonterminal/cancelled process fact")
    for name in ("wall_seconds", "cleanup_seconds", "observed_monotonic", "deadline_monotonic"):
        _finite(fact[name], name)
    if fact["deadline_monotonic"] > deadline or fact["members_after_cleanup"]:
        raise ValueError("Budget or group cleanup mismatch")
    if type(fact["pid"]) is not int or type(fact["returncode"]) is not int:
        raise ValueError("Invalid process identity/exit")
    if (fact["state"] == "completed") != (fact["observed_monotonic"] < fact["deadline_monotonic"]):
        raise ValueError("Late result classification mismatch")


def _expected_check(repeat, read, previous_end, deadline):
    verify = read(f"r{repeat}.verification.json")
    process = read(f"check-r{repeat}.process.json")
    start = read(f"r{repeat}.verification-start.json")
    manifest_sha = digest(read.path(f"r{repeat}.compile.json"))
    if (
        verify["process"] != process
        or verify["compile_manifest_sha256"] != manifest_sha
        or start["compile_manifest_sha256"] != manifest_sha
        or verify["effective_budget_seconds"] != start["effective_budget_seconds"]
    ):
        raise ValueError("Verification binding mismatch")
    _process(process, deadline)
    effective = start["effective_budget_seconds"]
    _finite(effective, "effective check budget")
    if effective > 60 or (
        process["state"] != "not_started"
        and process["deadline_monotonic"] - start["monotonic_ns"] / 1e9
        > 60 + h.CLOCK_TOLERANCE_SECONDS
    ):
        raise ValueError("Per-check budget exceeded")
    if start["monotonic_ns"] / 1e9 + h.CLOCK_TOLERANCE_SECONDS < previous_end:
        raise ValueError("Check started before prior group cleanup")
    if process["state"] == "not_started" and (
        effective != 0 or start["monotonic_ns"] / 1e9 + h.CLOCK_TOLERANCE_SECONDS < deadline
    ):
        raise ValueError("Unstarted check with remaining budget")
    criterion = None
    validation = None
    if process["state"] in {"timeout", "not_started"}:
        state, reason = (
            "verification_incomplete",
            "hard_timeout" if process["state"] == "timeout" else "job_budget",
        )
    elif process["returncode"] != 0:
        state, reason = "error", "check_child_failure"
    else:
        try:
            reply = read(f"r{repeat}.reply.json")
            state, criterion, reason, validation = h._decode_reply(
                reply, manifest_sha, start["monotonic_ns"], process["observed_monotonic"]
            )
        except (OSError, ValueError, KeyError, TypeError):
            state, reason = "error", "invalid_reply"
            validation, criterion = None, None
    check = h.Check(state, criterion, reason, process["wall_seconds"])
    if verify["check"] != asdict(check) or verify["validation"] != validation:
        raise ValueError("Verification classification mismatch")
    return check, verify


def reconstruct(root, spec, ordinal, resolve=None):
    """Re-derive row from stored native bytes and terminal facts, without QCEC."""
    root = Path(root)
    resolve = resolve or (lambda name: relative_file(root, name))
    prefix = job_prefix(spec, ordinal)
    directory = root / prefix

    def local(path):
        return resolve(path.relative_to(root).as_posix())

    def read(name):
        return _read(resolve, f"{prefix}/{name}")

    read.path = lambda name: resolve(f"{prefix}/{name}")
    job = h.Job(**spec["schedule"][ordinal])
    job_spec = read("spec.json")
    if job.target not in {"line", "all-to-all"} or type(job.seed) is not int:
        raise ValueError("Invalid job target/seed")
    case = next(c for c in spec["cases"] if c["id"] == job.case_id)
    config = next(c for c in spec["configurations"] if c["id"] == job.configuration_id)
    if (
        job_spec["job"] != asdict(job)
        or job_spec["protocol"] != spec["policy"]
        or job_spec["campaign_sha256"] != digest(resolve("campaign.json"))
        or job_spec["execution_identity"] != spec["execution_identities"][ordinal]
        or job_spec["input_sha256"] != case["sha256"]
        or job_spec["qubits"] != case["qubits"]
        or job_spec["versions"] != spec["versions"]
        or job_spec["affinity"] != spec["planned_affinity"]
        or job_spec["thread_env"] != spec["thread_env"]
        or job_spec["source_inventory"]
        != {name: spec["source_inventory"][name] for name in h.SOURCE_NAMES}
    ):
        raise ValueError("Job provenance mismatch")
    deadline = job_spec["deadline_monotonic"]
    if not math.isclose(deadline - job_spec["start_monotonic"], 420, abs_tol=1e-8):
        raise ValueError("Whole-job budget mismatch")
    compiler = read("compile.process.json")
    _process(compiler, deadline)
    if compiler["state"] != "not_started" and compiler["deadline_monotonic"] != deadline:
        raise ValueError("Compile deadline mismatch")
    fault = (
        "compile_child_failure"
        if compiler["state"] == "completed" and compiler["returncode"] != 0
        else None
    )
    facts, trials = [], []
    previous_end = (
        compiler["observed_monotonic"] + compiler["cleanup_seconds"]
        if compiler["state"] != "not_started"
        else deadline
    )
    for repeat in range(3):
        compiled = h._read_compile(directory, repeat, local)
        if compiled is None:
            facts.append(
                h.MissingTrial(
                    repeat, "job_budget" if compiler["state"] == "timeout" else "not_committed"
                )
            )
            continue
        _, manifest = h._native(directory, repeat, local)
        if (
            manifest["output_rules"] != "valid"
            or manifest["layout_semantics"] != "input declaration order logical-to-physical"
            or manifest["qiskit_version"] != spec["versions"]["qiskit"]
            or manifest["qpy_format_header_hex"]
            != read.path(f"r{repeat}.qpy").read_bytes()[:12].hex()
        ):
            raise ValueError("Native output rules/format identity mismatch")
        check, verify = _expected_check(repeat, read, previous_end, deadline)
        process = verify["process"]
        if process["state"] != "not_started":
            previous_end = process["observed_monotonic"] + process["cleanup_seconds"]
        facts.append(h.SavedTrial(compiled, check))
        trials.append(
            {
                "repeat": repeat,
                "compile_ms": manifest["compile_ms"],
                "metrics": manifest["metrics"],
                "initial_map": manifest["initial_map"],
                "final_map": manifest["final_map"],
                "global_phase": manifest["global_phase"],
                "output_rules": manifest["output_rules"],
                "artifact": f"{prefix}/r{repeat}.qasm",
                "artifact_sha256": manifest["qasm"]["sha256"],
                "qpy_artifact": f"{prefix}/r{repeat}.qpy",
                "qpy_sha256": manifest["qpy"]["sha256"],
                "compile_manifest": f"{prefix}/r{repeat}.compile.json",
                "compile_manifest_sha256": digest(read.path(f"r{repeat}.compile.json")),
                "validation": verify["validation"] or {"accepted": False, "criterion": None},
                "verification": {
                    **asdict(check),
                    "effective_budget_seconds": verify["effective_budget_seconds"],
                },
            }
        )
    report = h.Report(job, tuple(facts), fault)
    saved_times = [t["compile_ms"] for t in trials]
    result = read("result.json")
    expected_facts = [
        (
            {
                **asdict(t),
                "compile": {**asdict(t.compile), "manifest_path": t.compile.manifest_path.name},
            }
            if isinstance(t, h.SavedTrial)
            else asdict(t)
        )
        for t in facts
    ]
    if (
        result["job"] != asdict(job)
        or result["status"] != report.status
        or result["saved"] != report.saved
        or result["accepted"] != report.accepted
        or result["fault"] != fault
        or result["trials"] != expected_facts
        or result["compile_process"] != compiler
        or result["repeats_required"] != 3
        or result["timing_samples_ms"] != saved_times
        or result["compile_ms"] != (statistics.median(saved_times) if saved_times else None)
    ):
        raise ValueError("Terminal job rollup/median mismatch")
    _finite(result["wall_seconds"], "job wall time")
    if result["wall_seconds"] + 1e-6 < previous_end - job_spec["start_monotonic"]:
        raise ValueError("Job wall time excludes child or cleanup")
    row = {
        **asdict(job),
        "family": case["family"],
        "qubits": case["qubits"],
        "compiler": config["compiler"],
        "seed_supported": config["seed_supported"],
        "execution_identity": job_spec["execution_identity"],
        "worker_timeout_seconds": 420,
        "status": report.status,
        "fault": fault,
        "coverage": {
            "compiled": report.saved,
            "required_repeats": 3,
            "accepted_repeats": report.accepted,
        },
        "timing_samples_ms": saved_times,
        "compile_ms": result["compile_ms"],
        "metrics": {
            key: statistics.median(t["metrics"][key] for t in trials)
            for key in ("two_qubit_count", "two_qubit_depth", "one_qubit_count", "total_depth")
        }
        if trials
        else None,
        "trials": trials,
        "missing_trials": [asdict(t) for t in facts if isinstance(t, h.MissingTrial)],
        "wall_seconds": result["wall_seconds"],
        "compile_process": compiler,
        "terminal_facts": f"{prefix}/result.json",
    }
    return row


def _document(spec, rows, started):
    return {
        "schema_version": 3,
        "kind": KIND,
        "suite": SUITE,
        "campaign_id": spec["campaign_id"],
        "source_commit": spec["source_commit"],
        "created_at": started["created_at"],
        "formal_ranking": False,
        "score_version": SCORE_VERSION,
        "environment": {
            **spec["host"],
            "cpu_affinity": spec["planned_affinity"],
            "thread_env": spec["thread_env"],
            "versions": spec["versions"],
            "distributions": spec["versions"],
            "start": started,
        },
        "protocol": spec["protocol"],
        "cases": spec["cases"],
        "results": rows,
    }


def execute_job(root, case, configuration, target, seed, env):
    """The atlas.execute_job v3 branch owns compile/check groups directly."""
    root = Path(root)
    spec = validate_workspace(root)
    if not (root / "RUN_STARTED").is_file() or (root / MARKER).exists():
        raise ValueError("Standalone campaign is not accepting jobs")
    job = h.Job(case["id"], configuration, target, seed)
    ordinal = spec["schedule"].index(asdict(job))
    if case not in spec["cases"]:
        raise ValueError("Scheduled case metadata mismatch")
    h.run_job(
        job,
        root / job_prefix(spec, ordinal),
        root=root,
        env=env,
        campaign_sha256=digest(root / "campaign.json"),
        execution_identity=spec["execution_identities"][ordinal],
    )
    return reconstruct(root, spec, ordinal)


def run(root):
    root = Path(root)
    if any(
        (root / name).exists() for name in ("RUN_STARTED", "data/results.json", SNAPSHOT, MARKER)
    ):
        raise FileExistsError("Cannot rerun or recover an existing campaign")
    spec = validate_workspace(root)
    if versions() != spec["versions"]:
        raise ValueError("Resolved environment changed")
    if not set(spec["planned_affinity"]).issubset(os.sched_getaffinity(0)):
        raise ValueError("Planned CPU affinity unavailable")
    os.sched_setaffinity(0, set(spec["planned_affinity"]))
    env = {**os.environ, **spec["thread_env"], "PYTHONDONTWRITEBYTECODE": "1"}
    started = {
        "created_at": datetime.now(UTC).isoformat(),
        "monotonic_ns": time.monotonic_ns(),
        "campaign_sha256": digest(root / "campaign.json"),
        "loadavg": list(os.getloadavg()),
        "affinity": sorted(os.sched_getaffinity(0)),
        "thread_env": spec["thread_env"],
    }
    h._json(root / "RUN_STARTED", started)
    rows = []
    with (root / "data/run.jsonl").open("x") as log:
        for ordinal, raw_job in enumerate(spec["schedule"]):
            job = h.Job(**raw_job)
            row = execute_job(
                root,
                next(c for c in spec["cases"] if c["id"] == job.case_id),
                job.configuration_id,
                job.target,
                job.seed,
                env,
            )
            rows.append(row)
            entry = json.dumps(
                {"completed": ordinal + 1, "scheduled": len(spec["schedule"]), "result": row},
                allow_nan=False,
            )
            log.write(entry + "\n")
            log.flush()
            os.fsync(log.fileno())
            print(entry, flush=True)
    finish(root, _document(spec, rows, started))


def _verify_document(root, spec, document, resolve):
    if len(document["results"]) != len(spec["schedule"]):
        raise ValueError("Incomplete schedule")
    started = _read(resolve, "RUN_STARTED")
    if (
        started["campaign_sha256"] != digest(resolve("campaign.json"))
        or started["affinity"] != spec["planned_affinity"]
        or started["thread_env"] != spec["thread_env"]
    ):
        raise ValueError("Campaign start provenance mismatch")
    rows = [reconstruct(root, spec, i, resolve) for i in range(len(spec["schedule"]))]
    previous_end = started["monotonic_ns"] / 1e9
    for ordinal, row in enumerate(rows):
        job_spec = _read(resolve, job_prefix(spec, ordinal) + "/spec.json")
        if job_spec["start_monotonic"] + h.CLOCK_TOLERANCE_SECONDS < previous_end:
            raise ValueError("Scheduled jobs overlap or precede campaign start")
        previous_end = job_spec["start_monotonic"] + row["wall_seconds"]
    expected = _document(spec, rows, started)
    if document != expected:
        raise ValueError("Results are not derived from sealed facts")
    entries = [json.loads(line) for line in resolve("data/run.jsonl").read_text().splitlines()]
    if entries != [
        {"completed": i + 1, "scheduled": len(rows), "result": row} for i, row in enumerate(rows)
    ]:
        raise ValueError("Run log schedule/terminal mismatch")
    return rows


def finish(root, document):
    root = Path(root)
    if any((root / name).exists() for name in ("data/results.json", SNAPSHOT, MARKER)):
        raise FileExistsError("Cannot overwrite, reseal or recover a campaign")
    spec = validate_workspace(root)

    def resolve(name):
        return relative_file(root, name)

    _verify_document(root, spec, document, resolve)
    h._json(root / "data/results.json", document)
    files = _inventory(root)
    snapshot = {
        "seal_format_version": 3,
        "kind": KIND,
        "campaign_id": spec["campaign_id"],
        "suite": SUITE,
        "spec_sha256": digest(root / "campaign.json"),
        "source_commit": spec["source_commit"],
        "scheduled_entries": len(spec["schedule"]),
        "potential_trials": len(spec["schedule"]) * 3,
        "files": files,
    }
    h._json(root / SNAPSHOT, snapshot)
    h._durable(root / MARKER, (digest(root / SNAPSHOT) + "\n").encode())
    validate_completed(root)


def validate_completed(root, resolve=None):
    root = Path(root)
    native = resolve is None
    resolve = resolve or (lambda name: relative_file(root, name))
    snapshot = _read(resolve, SNAPSHOT)
    if snapshot["seal_format_version"] != 3 or snapshot["kind"] != KIND:
        raise ValueError("Unknown standalone seal")
    if resolve(MARKER).read_text().strip() != digest(resolve(SNAPSHOT)):
        raise ValueError("Completion marker hash mismatch")
    for name, sha in snapshot["files"].items():
        if digest(resolve(name)) != sha:
            raise ValueError(f"Sealed file hash mismatch: {name}")
    if native and _inventory(root) != snapshot["files"]:
        raise ValueError("Forensic inventory exact coverage mismatch")
    spec = validate_workspace(root, resolve)
    if (
        snapshot["spec_sha256"] != digest(resolve("campaign.json"))
        or snapshot["campaign_id"] != spec["campaign_id"]
        or snapshot["suite"] != spec["suite"]
        or snapshot["source_commit"] != spec["source_commit"]
        or snapshot["scheduled_entries"] != len(spec["schedule"])
        or snapshot["potential_trials"] != len(spec["schedule"]) * 3
        or not set(spec["files"]).issubset(snapshot["files"])
    ):
        raise ValueError("Seal identity/coverage mismatch")
    _verify_document(root, spec, _read(resolve, "data/results.json"), resolve)
    return snapshot


def preview(root, destination):
    """Copy a seal to a new display-only directory; never mutate measurement bytes."""
    import build_site

    validate_completed(root)
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError("Preview must be fresh")
    shutil.copytree(root, destination, ignore=shutil.ignore_patterns("__pycache__"))
    old = build_site.ROOT
    try:
        build_site.ROOT = destination
        build_site.build()
    finally:
        build_site.ROOT = old
    return destination


def _cancel(_signum, _frame):
    raise KeyboardInterrupt("Incomplete standalone campaign retained")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _cancel)
    run(Path(__file__).resolve().parent)
