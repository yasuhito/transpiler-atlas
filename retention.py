"""Compile-first storage and single-owner process supervision for standalone v3.

The legacy atlas worker remains the v1/v2 execution path. This protocol calls the
same compile_once and strict checker, but persists native bytes before checks.
Disk facts, not child stdout, are authoritative. No resume or selective retry.
"""

from __future__ import annotations

import ctypes
import hashlib
import importlib.metadata
import io
import json
import math
import os
import signal
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPEATS = 3
JOB_SECONDS = 420
CHECK_SECONDS = 60
# Only for comparing serialized float seconds with integer-nanosecond receipts.
# Live supervision always makes deadline decisions with strict monotonic comparisons.
CLOCK_TOLERANCE_SECONDS = 1e-6
SOURCE_NAMES = (
    "atlas.py",
    "retention.py",
    "retention_campaign.py",
    "uv.lock",
    "pyproject.toml",
    "qmap_adapter.py",
    "cirq_adapter.py",
)
CRITERIA = {
    "equivalent": "passed",
    "equivalent_up_to_global_phase": "passed",
    "not_equivalent": "not_equivalent",
    "no_information": "verification_incomplete",
    "equivalent_up_to_phase": "verification_incomplete",
    "probably_equivalent": "verification_incomplete",
    "probably_not_equivalent": "verification_incomplete",
}


@dataclass(frozen=True)
class Job:
    case_id: str
    configuration_id: str
    target: str
    seed: int


@dataclass(frozen=True)
class Compiled:
    repeat: int
    manifest_path: Path
    compile_ms: float


@dataclass(frozen=True)
class Check:
    state: str
    criterion: str | None
    reason: str | None
    wall_seconds: float


@dataclass(frozen=True)
class MissingTrial:
    repeat: int
    reason: str


@dataclass(frozen=True)
class SavedTrial:
    compile: Compiled
    check: Check


@dataclass(frozen=True)
class Report:
    job: Job
    trials: tuple[SavedTrial | MissingTrial, ...]
    fault: str | None

    @property
    def status(self) -> str:
        if self.fault or any(
            isinstance(t, SavedTrial) and t.check.state == "error" for t in self.trials
        ):
            return "error"
        if any(isinstance(t, MissingTrial) for t in self.trials):
            return "compile_incomplete"
        states = [t.check.state for t in self.trials if isinstance(t, SavedTrial)]
        if "not_equivalent" in states:
            return "not_equivalent"
        return "passed" if states == ["passed"] * REPEATS else "verification_incomplete"

    @property
    def saved(self) -> int:
        return sum(isinstance(t, SavedTrial) for t in self.trials)

    @property
    def accepted(self) -> int:
        return sum(isinstance(t, SavedTrial) and t.check.state == "passed" for t in self.trials)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _durable(path: Path, content: bytes) -> None:
    """Exclusive file publish; manifest caller decides the bundle commit point."""
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError("Unsafe output path")
    if path.exists():
        raise FileExistsError(path)
    pending = path.with_name(path.name + f".pending-{os.getpid()}")
    with pending.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.link(pending, path)
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
        pending.unlink()
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _json(path: Path, value) -> None:
    def encode(item):
        if isinstance(item, Path):
            return str(item)
        raise TypeError(f"Unsupported JSON value: {type(item)}")

    _durable(path, (json.dumps(value, indent=2, allow_nan=False, default=encode) + "\n").encode())


def _event(path: Path, event: str, **fields) -> None:
    # One writer per timeline, not shared between compile child and parent.
    with path.open("a") as stream:
        stream.write(
            json.dumps(
                {
                    "event": event,
                    "wall_ns": time.time_ns(),
                    "monotonic_ns": time.monotonic_ns(),
                    **fields,
                }
            )
            + "\n"
        )
        stream.flush()
        os.fsync(stream.fileno())


def _case(job: Job, root: Path = ROOT):
    import atlas
    from campaign import relative_file

    cases = json.loads(relative_file(root, "data/manifest.json").read_text())
    case = next(c for c in cases if c["id"] == job.case_id)
    source = relative_file(root, case["path"])
    if _digest(source) != case["sha256"]:
        raise ValueError("Frozen input hash mismatch")
    atlas.configuration_for(job.configuration_id)
    atlas.edges_for(case["qubits"], job.target)
    return case, source


def _spec(directory: Path, resolve=None):
    path = directory / "spec.json"
    return json.loads((resolve(path) if resolve else path).read_text())


def _maps_phase(record, qubits: int):
    for name in ("initial_map", "final_map"):
        values = record[name]
        if any(type(x) is not int for x in values) or sorted(values) != list(range(qubits)):
            raise ValueError("Invalid bijective map")
    for name in ("compile_ms", "global_phase"):
        value = record[name]
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("Invalid scalar")
    if record["compile_ms"] < 0:
        raise ValueError("Negative compile time")


def _read_compile(directory: Path, repeat: int, resolve=None) -> Compiled | None:
    manifest = directory / f"r{repeat}.compile.json"
    if resolve:
        try:
            manifest = resolve(manifest)
        except (ValueError, KeyError, FileNotFoundError):
            return None
    if not manifest.exists():
        return None
    if manifest.is_symlink():
        raise ValueError("Symlink compile manifest")
    record = json.loads(manifest.read_text())
    spec = _spec(directory, resolve)
    spec_path = directory / "spec.json"
    if resolve:
        spec_path = resolve(spec_path)
    if (
        record["job"] != spec["job"]
        or type(record["repeat"]) is not int
        or record["repeat"] != repeat
        or record["spec_sha256"] != _digest(spec_path)
        or record["input_sha256"] != spec["input_sha256"]
    ):
        raise ValueError("Compile identity mismatch")
    _maps_phase(record, spec["qubits"])
    for kind in ("qasm", "qpy"):
        expected = f"r{repeat}.{kind}"
        if record[kind]["path"] != expected:
            raise ValueError("Unsafe artifact reference")
        path = directory / expected
        if resolve:
            path = resolve(path)
        if path.is_symlink() or not path.is_file() or _digest(path) != record[kind]["sha256"]:
            raise ValueError("Artifact integrity mismatch")
    return Compiled(repeat, manifest, record["compile_ms"])


def _native(directory: Path, repeat: int, resolve=None):
    from qiskit import qasm2, qpy

    import atlas

    compiled = _read_compile(directory, repeat, resolve)
    if compiled is None:
        raise ValueError("No committed compile")
    record = json.loads(compiled.manifest_path.read_text())
    qpy_path = directory / record["qpy"]["path"]
    qasm_path = directory / record["qasm"]["path"]
    if resolve:
        qpy_path, qasm_path = resolve(qpy_path), resolve(qasm_path)
    with qpy_path.open("rb") as stream:
        circuits = qpy.load(stream)
    if len(circuits) != 1:
        raise ValueError("Unexpected QPY circuit count")
    native = circuits[0]
    if (
        native.num_qubits != _spec(directory, resolve)["qubits"]
        or native.num_clbits
        or native.ancillas
        or float(native.global_phase) != record["global_phase"]
    ):
        raise ValueError("Native shape/phase mismatch")
    job = Job(**record["job"])
    for item in native.data:
        if any(not math.isfinite(float(p)) for p in item.operation.params):
            raise ValueError("Nonfinite native gate parameter")
    measured = atlas.metrics(native, atlas.edges_for(native.num_qubits, job.target))
    if measured != record["metrics"]:
        raise ValueError("Metric mismatch")
    if (qasm2.dumps(native) + "\n").encode() != qasm_path.read_bytes():
        raise ValueError("QASM/QPY export mismatch")
    return native, record


def _compile_child(directory: Path) -> None:
    from qiskit import qasm2, qpy

    import atlas

    spec = _spec(directory)
    job = Job(**spec["job"])
    _, source = _case(job)
    frozen = source.read_bytes()
    original = qasm2.loads(frozen.decode())
    timeline = directory / "compile.timeline.jsonl"
    for repeat in range(REPEATS):
        _event(timeline, "compile_start", repeat=repeat)
        native, elapsed, initial, final = atlas.compile_once(
            original, job.configuration_id, job.target, job.seed, frozen_qasm=frozen
        )
        if any(not math.isfinite(float(p)) for item in native.data for p in item.operation.params):
            raise ValueError("Nonfinite native gate parameter")
        record = {
            "job": asdict(job),
            "repeat": repeat,
            "spec_sha256": _digest(directory / "spec.json"),
            "input_sha256": _digest(source),
            "compile_ms": elapsed,
            "initial_map": initial,
            "final_map": final,
            "global_phase": float(native.global_phase),
            "metrics": atlas.metrics(native, atlas.edges_for(native.num_qubits, job.target)),
            "layout_semantics": "input declaration order logical-to-physical",
            "qiskit_version": importlib.metadata.version("qiskit"),
            "compiled_return_wall_ns": time.time_ns(),
            "output_rules": "valid",
        }
        _maps_phase(record, original.num_qubits)
        if native.num_qubits != original.num_qubits or native.num_clbits or native.ancillas:
            raise ValueError("Native output width/classical/ancilla mismatch")
        qpy_bytes = io.BytesIO()
        qpy.dump(native, qpy_bytes)
        for kind, data in [
            ("qasm", (qasm2.dumps(native) + "\n").encode()),
            ("qpy", qpy_bytes.getvalue()),
        ]:
            path = directory / f"r{repeat}.{kind}"
            _durable(path, data)
            record[kind] = {
                "path": path.name,
                "sha256": _digest(path),
                "mtime_ns": path.stat().st_mtime_ns,
            }
        record["qpy_format_header_hex"] = qpy_bytes.getvalue()[:12].hex()
        _json(directory / f"r{repeat}.compile.json", record)
        _event(
            timeline,
            "compile_committed",
            repeat=repeat,
            manifest_mtime_ns=(directory / f"r{repeat}.compile.json").stat().st_mtime_ns,
        )
        del native


def _check_child(directory: Path, repeat: int) -> None:
    from qiskit import qasm2

    import atlas

    native, record = _native(directory, repeat)
    _, source = _case(Job(**record["job"]))
    original = qasm2.loads(source.read_text())
    _json(
        directory / f"r{repeat}.check-entered.json",
        {
            "wall_ns": time.time_ns(),
            "monotonic_ns": time.monotonic_ns(),
            "compile_manifest_sha256": _digest(directory / f"r{repeat}.compile.json"),
        },
    )
    result = atlas.check_equivalence(original, native, record["initial_map"], record["final_map"])
    _json(
        directory / f"r{repeat}.reply.json",
        {
            "compile_manifest_sha256": _digest(directory / f"r{repeat}.compile.json"),
            "validation": result,
            "returned_wall_ns": time.time_ns(),
            "returned_monotonic_ns": time.monotonic_ns(),
        },
    )


def _members(group: int) -> list[dict]:
    members = []
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        try:
            stat = (path / "stat").read_text()
            fields = stat[stat.rfind(")") + 2 :].split()
            if int(fields[2]) == group:
                members.append({"pid": int(path.name), "ppid": int(fields[1]), "state": fields[0]})
        except (OSError, ValueError, IndexError):
            continue
    return members


def _subreaper() -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0):
        raise OSError(ctypes.get_errno(), "PR_SET_CHILD_SUBREAPER")


class Cancelled(Exception):
    pass


def _cleanup(process: subprocess.Popen) -> dict:
    started = time.monotonic()
    members = _members(process.pid)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    returncode = process.wait(timeout=5)
    reaped = []
    cleanup_deadline = time.monotonic() + 5
    while True:
        while True:
            try:
                pid, child_status = os.waitpid(-process.pid, os.WNOHANG)
            except ChildProcessError:
                break
            if pid == 0:
                break
            reaped.append({"pid": pid, "status": child_status})
        remaining = _members(process.pid)
        if not remaining:
            break
        if time.monotonic() >= cleanup_deadline:
            raise RuntimeError(f"Cleanup incomplete: {remaining}")
        time.sleep(0.02)
    return {
        "returncode": returncode,
        "cleanup_seconds": time.monotonic() - started,
        "members_before_cleanup": members,
        "adopted_reaped": reaped,
        "members_after_cleanup": remaining,
    }


def _supervise(
    command: list[str], directory: Path, name: str, deadline: float, env: dict | None = None
) -> dict:
    """One direct group, no pipe transport; keep root unreaped until group kill."""
    started = time.monotonic()
    if started >= deadline:
        result = {"state": "not_started", "wall_seconds": 0, "reason": "job_budget"}
        _json(directory / f"{name}.process.json", result)
        return result
    _subreaper()
    cancelled = False

    def request_cancel(_signal, _frame):
        nonlocal cancelled
        cancelled = True

    old_handlers = {s: signal.signal(s, request_cancel) for s in (signal.SIGINT, signal.SIGTERM)}
    process = None
    cleaned = False
    try:
        with (
            (directory / f"{name}.stdout.log").open("x") as stdout,
            (directory / f"{name}.stderr.log").open("x") as stderr,
        ):
            blocked = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
            try:
                process = subprocess.Popen(
                    command,
                    cwd=ROOT,
                    env=env,
                    stdout=stdout,
                    stderr=stderr,
                    start_new_session=True,
                )
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK, blocked)
            while True:
                now = time.monotonic()
                if cancelled:
                    state = "cancelled"
                    break
                if now >= deadline:
                    state = "timeout"
                    break
                # WNOWAIT retains root PID, closing the PGID reuse window before kill.
                status = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                if status is not None:
                    state = "completed"
                    break
                time.sleep(min(0.02, max(0, deadline - now)))
            observed = time.monotonic()
            cleanup = _cleanup(process)
            cleaned = True
            result = {
                "state": state,
                "pid": process.pid,
                "wall_seconds": observed - started,
                "deadline_monotonic": deadline,
                "observed_monotonic": observed,
                **cleanup,
            }
            _json(directory / f"{name}.process.json", result)
            if cancelled:
                raise Cancelled("Incomplete diagnostic retained")
            return result
    finally:
        if process is not None and not cleaned:
            _cleanup(process)
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)


def _classification(criterion: str) -> str:
    return CRITERIA.get(criterion, "error")


def _decode_reply(reply, manifest_sha, start_ns, observed):
    """Validate the returned receipt; malformed declarations never become facts."""
    for name in ("returned_wall_ns", "returned_monotonic_ns"):
        if type(reply[name]) is not int or reply[name] <= 0:
            raise ValueError("Invalid reply clock schema")
    if (
        reply["compile_manifest_sha256"] != manifest_sha
        or reply["returned_monotonic_ns"] < start_ns
        or reply["returned_monotonic_ns"] / 1e9 > observed + CLOCK_TOLERANCE_SECONDS
    ):
        raise ValueError("Reply bound to wrong compile or outside observed execution")
    validation = reply["validation"]
    criterion = validation["criterion"]
    if type(criterion) is not str:
        raise ValueError("Invalid criterion schema")
    state = _classification(criterion)
    if type(validation["accepted"]) is not bool or validation["accepted"] != (state == "passed"):
        raise ValueError("Strict acceptance mismatch")
    reason = {
        "verification_incomplete": "nonconclusive_criterion",
        "error": "unknown_criterion",
    }.get(state)
    return state, criterion, reason, validation


def run_job(
    job: Job,
    directory: Path,
    *,
    root: Path = ROOT,
    env: dict | None = None,
    campaign_sha256: str | None = None,
    execution_identity: str | None = None,
) -> Report:
    """One public operation, fixed policy; exclusive directory, no resume/retry."""
    start = time.monotonic()
    deadline = start + JOB_SECONDS
    if directory.is_symlink() or any(p.is_symlink() for p in directory.parents):
        raise ValueError("Unsafe job directory")
    case, source = _case(job, root)
    directory.mkdir(parents=True, exist_ok=False)
    descriptor = os.open(directory.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    protocol = {
        "repeats": REPEATS,
        "whole_job_seconds": JOB_SECONDS,
        "check_hard_seconds": CHECK_SECONDS,
        "qcec_cooperative_seconds": 20,
        "order": "compile-all-then-verify",
        "deadline_policy": "observed-exit-before-cutoff",
        "transport": "native-QPY",
        "kind": "compile-retention",
        "protocol_version": 1,
    }
    inventory = {name: _digest(root / name) for name in SOURCE_NAMES}
    _json(
        directory / "spec.json",
        {
            "job": asdict(job),
            "campaign_sha256": campaign_sha256,
            "execution_identity": execution_identity,
            "input_sha256": _digest(source),
            "qubits": case["qubits"],
            "protocol": protocol,
            "source_inventory": inventory,
            "versions": {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()},
            "affinity": sorted(os.sched_getaffinity(0)),
            "thread_env": {
                n: (env if env is not None else os.environ).get(n)
                for n in (
                    "OMP_NUM_THREADS",
                    "OPENBLAS_NUM_THREADS",
                    "MKL_NUM_THREADS",
                    "RAYON_NUM_THREADS",
                    "QISKIT_NUM_PROCS",
                )
            },
            "host_loadavg": os.getloadavg(),
            "created_wall_ns": time.time_ns(),
            "start_monotonic": start,
            "deadline_monotonic": deadline,
        },
    )
    _event(directory / "parent.timeline.jsonl", "job_start")
    compiler = _supervise(
        [sys.executable, str(root / "retention.py"), "compile", str(directory)],
        directory,
        "compile",
        deadline,
        env,
    )
    fault = None
    if compiler["state"] == "completed" and compiler["returncode"] != 0:
        fault = "compile_child_failure"
    trials = []
    for repeat in range(REPEATS):
        compiled = _read_compile(directory, repeat)
        if compiled is None:
            trials.append(
                MissingTrial(
                    repeat, "job_budget" if compiler["state"] == "timeout" else "not_committed"
                )
            )
            continue
        check_deadline = min(deadline, time.monotonic() + CHECK_SECONDS)
        effective = min(CHECK_SECONDS, max(0, check_deadline - time.monotonic()))
        _json(
            directory / f"r{repeat}.verification-start.json",
            {
                "wall_ns": time.time_ns(),
                "monotonic_ns": time.monotonic_ns(),
                "effective_budget_seconds": effective,
                "compile_manifest_sha256": _digest(compiled.manifest_path),
                "manifest_mtime_ns": compiled.manifest_path.stat().st_mtime_ns,
            },
        )
        _event(
            directory / "parent.timeline.jsonl",
            "verification_start",
            repeat=repeat,
            effective_budget_seconds=effective,
        )
        process = _supervise(
            [sys.executable, str(root / "retention.py"), "check", str(directory), str(repeat)],
            directory,
            f"check-r{repeat}",
            check_deadline,
            env,
        )
        criterion = None
        reason = None
        validation = None
        if process["state"] in {"timeout", "not_started"}:
            state = "verification_incomplete"
            reason = "hard_timeout" if process["state"] == "timeout" else "job_budget"
        elif process["returncode"] != 0:
            state, reason = "error", "check_child_failure"
        else:
            try:
                reply = json.loads((directory / f"r{repeat}.reply.json").read_text())
                start_receipt = json.loads(
                    (directory / f"r{repeat}.verification-start.json").read_text()
                )
                state, criterion, reason, validation = _decode_reply(
                    reply,
                    _digest(compiled.manifest_path),
                    start_receipt["monotonic_ns"],
                    process["observed_monotonic"],
                )
            except (OSError, ValueError, KeyError, TypeError):
                state, reason = "error", "invalid_reply"
                validation, criterion = None, None
        check = Check(state, criterion, reason, process["wall_seconds"])
        _json(
            directory / f"r{repeat}.verification.json",
            {
                "compile_manifest_sha256": _digest(compiled.manifest_path),
                "check": asdict(check),
                "process": process,
                "effective_budget_seconds": effective,
                "validation": validation,
            },
        )
        trials.append(SavedTrial(compiled, check))
    report = Report(job, tuple(trials), fault)
    saved_times = [t.compile.compile_ms for t in trials if isinstance(t, SavedTrial)]
    _json(
        directory / "result.json",
        {
            "job": asdict(job),
            "status": report.status,
            "saved": report.saved,
            "accepted": report.accepted,
            "fault": report.fault,
            "repeats_required": REPEATS,
            "timing_samples_ms": saved_times,
            "compile_ms": statistics.median(saved_times) if saved_times else None,
            "quality": None,
            "speed": None,
            "score_na_reason": "standalone_raw_diagnostic",
            "compile_process": compiler,
            "wall_seconds": time.monotonic() - start,
            "trials": [
                {
                    **asdict(t),
                    "compile": {**asdict(t.compile), "manifest_path": t.compile.manifest_path.name},
                }
                if isinstance(t, SavedTrial)
                else asdict(t)
                for t in trials
            ],
        },
    )
    return report


def _main():
    action, directory, *rest = sys.argv[1:]
    path = Path(directory)
    if action == "compile":
        _compile_child(path)
    elif action == "check":
        _check_child(path, int(rest[0]))
    else:
        raise ValueError(action)


if __name__ == "__main__":
    _main()
