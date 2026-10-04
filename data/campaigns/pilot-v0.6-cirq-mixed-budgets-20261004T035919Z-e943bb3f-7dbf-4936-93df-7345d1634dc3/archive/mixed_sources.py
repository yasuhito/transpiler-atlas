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
    configs = [c for c in CONFIGURATIONS if c["compiler"] not in {"qmap", "cirq"}]
    try:
        sealed = json.loads(resolve("campaign.json").read_text())
    except (FileNotFoundError, KeyError):
        sealed = None
    if sealed is not None:
        configs = [c for c in sealed["configurations"] if c["compiler"] not in {"qmap", "cirq"}]
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
    if "worker_timeout_seconds" in row:
        return row["worker_timeout_seconds"]
    if "initial_worker_timeout_seconds" in protocol:
        return protocol["initial_worker_timeout_seconds"]
    return protocol["worker_timeout_seconds"]


def combine(root, qmap, resolve=None):
    import atlas
    from campaign import digest, relative_file

    root = Path(root)
    resolve = resolve or (lambda name: relative_file(root, name))
    spec = json.loads(resolve("campaign.json").read_text())
    if spec.get("spec_format_version", 1) not in {1, 2}:
        raise ValueError("Unknown spec format")
    if spec.get("spec_format_version") == 2:
        return combine_cirq(root, qmap, resolve)
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
        suite=spec["suite"],
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
        configurations=copy.deepcopy(spec["configurations"]),
        compilers=list(dict.fromkeys(c["compiler"] for c in spec["configurations"])),
        sdk_packages={k: v for k, v in atlas.SDK_PACKAGES.items() if k != "cirq"},
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
        for c in spec["configurations"]
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
    spec = json.loads(resolve("campaign.json").read_text())
    name = (
        "data/cirq-results.json"
        if spec.get("spec_format_version") == 2
        else "data/qmap-results.json"
    )
    qmap = json.loads(resolve(name).read_text())
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


def combine_cirq(root, cirq, resolve):
    """Recompose three authenticated sources without modifying any original row."""
    from campaign import digest, validate_completed

    spec = json.loads(resolve("campaign.json").read_text())

    def inherited(name):
        return resolve("history/pilot-v0.5/" + name)

    validate_completed(root, inherited)
    previous = json.loads(inherited("data/results.json").read_text())
    if digest(inherited("MEASUREMENT_COMPLETE")) != spec["inherited_seal_sha256"]:
        raise ValueError("Inherited seal changed")
    if previous["cases"] != cirq["cases"]:
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
        if previous["protocol"][key] != cirq["protocol"][key]:
            raise ValueError(f"Cannot combine different shared rules: {key}")
    owners = previous["protocol"]["configurations"] + cirq["protocol"]["configurations"]
    if owners != spec["configurations"] or len({c["id"] for c in owners}) != len(owners):
        raise ValueError("Source configuration ownership mismatch")
    data = copy.deepcopy(previous)
    data.update(
        suite=spec["suite"],
        campaign_id=cirq["campaign_id"],
        source_commit=cirq["source_commit"],
        created_at=cirq["created_at"],
        results=copy.deepcopy(previous["results"]) + copy.deepcopy(cirq["results"]),
    )
    protocol = data["protocol"]
    protocol.update(
        configurations=copy.deepcopy(owners),
        compilers=list(dict.fromkeys(c["compiler"] for c in owners)),
        sdk_packages={**protocol["sdk_packages"], **cirq["protocol"]["sdk_packages"]},
        cirq_pipeline=cirq["protocol"]["cirq_pipeline"],
        cirq_seed_note=cirq["protocol"]["cirq_seed_note"],
        measured_entries=len(cirq["results"]),
        reused_entries=len(previous["results"]),
    )
    for source in protocol["measurement_sources"].values():
        source["kind"] = "reused"
        source["results_path"] = "history/pilot-v0.5/" + source["results_path"]
    protocol["measurement_sources"]["cirq420"] = {
        "suite": cirq["suite"],
        "kind": "new",
        "records": len(cirq["results"]),
        "results_path": "data/cirq-results.json",
        "results_sha256": digest(resolve("data/cirq-results.json")),
        "created_at": cirq["created_at"],
        "protocol": copy.deepcopy(cirq["protocol"]),
        "environment": copy.deepcopy(cirq["environment"]),
    }
    protocol["source_set_format_version"] = 2
    protocol["configuration_sources"].update(
        {c["id"]: "cirq420" for c in cirq["protocol"]["configurations"]}
    )
    expected = {
        (case["id"], c["id"], target, seed)
        for case in data["cases"]
        for c in owners
        for target in ("line", "all-to-all")
        for seed in protocol["seeds"]
    }
    actual = [
        (r["case_id"], r["configuration_id"], r["target"], r["seed"]) for r in data["results"]
    ]
    if len(actual) != len(expected) or set(actual) != expected or len(actual) != 936:
        raise ValueError("Combined schedule is incomplete or duplicated")
    data["environment"] = {
        "cpu": "Mixed sources; see source environments",
        "cpu_affinity": [],
        "platform": "Mixed measurement windows",
        "python": None,
        "versions": {},
        "exclusive_machine": False,
        "memory_limit_enforced": False,
    }
    return data
