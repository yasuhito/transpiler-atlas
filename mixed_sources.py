"""Preserve v0.4 records verbatim while joining a separately measured QMAP cohort."""

import copy
import hashlib
import json
from pathlib import Path

LEGACY_SOURCE = "v0.4"
QMAP_SOURCE = "qmap420"
LEGACY_RESULTS = "history/pilot-v0.4/data/results.json"


def load_legacy(root, resolve=None):
    from atlas import CONFIGURATIONS, REPEATS, SEEDS
    from campaign import relative_file

    resolve = resolve or (lambda name: relative_file(Path(root), name))
    legacy = json.loads(resolve(LEGACY_RESULTS).read_text())
    configs = [c for c in CONFIGURATIONS if c["compiler"] != "qmap"]
    protocol = legacy["protocol"]
    if (
        legacy["suite"] != "pilot-v0.4"
        or protocol["configurations"] != configs
        or protocol["seeds"] != SEEDS
        or protocol["timing_repeats"] != REPEATS
    ):
        raise ValueError("Legacy configuration/input protocol mismatch")
    expected = {
        (case["id"], c["id"], target, seed)
        for case in legacy["cases"]
        for c in configs
        for target in ("line", "all-to-all")
        for seed in SEEDS
    }
    actual = [
        (r["case_id"], r["configuration_id"], r["target"], r["seed"]) for r in legacy["results"]
    ]
    if len(actual) != 792 or len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("Legacy schedule is incomplete or duplicated")
    retried = [r for r in legacy["results"] if r.get("previous_attempts")]
    if len(retried) != protocol["timeout_retry_entries"]:
        raise ValueError("Legacy retry count mismatch")
    initial = protocol["initial_worker_timeout_seconds"]
    retry = protocol["worker_timeout_seconds"]
    for row in legacy["results"]:
        if row.get("worker_timeout_seconds", initial) != (
            retry if row.get("previous_attempts") else initial
        ):
            raise ValueError("Legacy record budget mismatch")
        if any(
            previous.get("worker_timeout_seconds", initial) != initial
            for previous in row.get("previous_attempts", [])
        ):
            raise ValueError("Legacy previous-attempt budget mismatch")
    resolve("history/pilot-v0.4/" + protocol["initial_attempt_snapshot"])
    return legacy


def record_budget_seconds(document, row):
    """Do not infer that a retained initial record used the retry admission budget."""
    sources = document["protocol"]["measurement_sources"]
    source = sources[document["protocol"]["configuration_sources"][row["configuration_id"]]]
    protocol = source["protocol"]
    return row.get(
        "worker_timeout_seconds",
        protocol.get("initial_worker_timeout_seconds", protocol["worker_timeout_seconds"]),
    )


def combine(root, qmap, resolve=None):
    import atlas
    from campaign import digest, relative_file

    root = Path(root)
    resolve = resolve or (lambda name: relative_file(root, name))
    legacy = load_legacy(root, resolve)
    if legacy["cases"] != qmap["cases"]:
        raise ValueError("Cannot combine different frozen inputs")
    for key in (
        "seeds",
        "timing_repeats",
        "basis",
        "physical_qubits",
        "input_track",
        "validation",
        "reference_configuration",
    ):
        if legacy["protocol"][key] != qmap["protocol"][key]:
            raise ValueError(f"Cannot combine different shared rules: {key}")
    data = copy.deepcopy(legacy)
    data.update(
        suite=atlas.SUITE,
        campaign_id=qmap["campaign_id"],
        source_commit=qmap["source_commit"],
        created_at=qmap["created_at"],
        results=copy.deepcopy(legacy["results"]) + copy.deepcopy(qmap["results"]),
    )
    data.pop("updated_at", None)
    protocol = data["protocol"]
    for key in (
        "worker_timeout_seconds",
        "initial_worker_timeout_seconds",
        "timeout_retry_entries",
        "initial_attempt_snapshot",
        "resumed_entries",
        "resume_log_sha256",
    ):
        protocol.pop(key, None)
    protocol.update(
        configurations=copy.deepcopy(atlas.CONFIGURATIONS),
        compilers=atlas.COMPILERS,
        sdk_packages=atlas.SDK_PACKAGES,
        qmap_pipeline=qmap["protocol"]["qmap_pipeline"],
        qmap_seed_note=qmap["protocol"]["qmap_seed_note"],
        measured_entries=len(qmap["results"]),
        reused_entries=len(legacy["results"]),
        comparison="Mixed budgets and measurement windows; not a matched-budget rerun",
    )
    protocol["measurement_sources"] = {
        LEGACY_SOURCE: {
            "suite": legacy["suite"],
            "kind": "reused",
            "records": len(legacy["results"]),
            "results_path": LEGACY_RESULTS,
            "results_sha256": digest(resolve(LEGACY_RESULTS)),
            "created_at": legacy["created_at"],
            "updated_at": legacy.get("updated_at"),
            "protocol": copy.deepcopy(legacy["protocol"]),
            "environment": copy.deepcopy(legacy["environment"]),
        },
        QMAP_SOURCE: {
            "suite": qmap["suite"],
            "kind": "new",
            "records": len(qmap["results"]),
            "results_path": "data/qmap-results.json",
            "results_sha256": digest(resolve("data/qmap-results.json")),
            "created_at": qmap["created_at"],
            "protocol": copy.deepcopy(qmap["protocol"]),
            "environment": copy.deepcopy(qmap["environment"]),
        },
    }
    protocol["configuration_sources"] = {
        c["id"]: QMAP_SOURCE if c["compiler"] == "qmap" else LEGACY_SOURCE
        for c in atlas.CONFIGURATIONS
    }
    versions = {
        **legacy["environment"]["versions"],
        "mqt.qmap": qmap["environment"]["versions"]["mqt.qmap"],
    }
    data["environment"] = {
        "cpu": "Mixed sources; see source environments",
        "cpu_affinity": [],
        "platform": "Mixed measurement windows",
        "python": None,
        "versions": versions,
        "exclusive_machine": False,
        "memory_limit_enforced": False,
    }
    return data


def validate_combined(root, combined, resolve=None):
    from campaign import digest, relative_file

    root = Path(root)
    resolve = resolve or (lambda name: relative_file(root, name))
    qmap = json.loads(resolve("data/qmap-results.json").read_text())
    if combined != combine(root, qmap, resolve):
        raise ValueError("Combined records or provenance changed")
    for source in combined["protocol"]["measurement_sources"].values():
        if digest(resolve(source["results_path"])) != source["results_sha256"]:
            raise ValueError("Measurement source digest mismatch")
    return qmap


def canonical_record_digest(rows):
    return hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
