"""Explicitly synthetic process receipts for budget/seal tests, never measurements.

Native bundles use the real Qiskit compile/save path; only process/check outcomes
and elapsed wall clock are simulated. Separate E2E tests exercise real children.
"""

import json
import os
import time
from datetime import UTC, datetime

import retention as h
import retention_campaign as campaign


class CompileCutoff(Exception):
    pass


def simulate(root, spec, monkeypatch, mode="timeout"):
    job = h.Job(**spec["schedule"][0])
    directory = root / campaign.job_prefix(spec, 0)
    clock = [time.monotonic()]
    spawned = []
    real_event = h._event
    real_fsync = os.fsync

    def fsync(descriptor):
        if mode == "manifest_failure" and "r0.compile.json.pending-" in os.readlink(
            f"/proc/self/fd/{descriptor}"
        ):
            raise OSError("Synthetic fsync failure before manifest publish")
        real_fsync(descriptor)

    def event(path, name, **fields):
        real_event(path, name, **fields)
        if mode == "compile_partial" and name == "compile_start" and fields["repeat"] == 2:
            raise CompileCutoff()
        if mode == "save_failure" and name == "compile_committed" and fields["repeat"] == 0:
            raise OSError("Synthetic failure after first commit")

    def supervise(command, directory, name, deadline, env=None):
        before = clock[0]
        if before >= deadline:
            result = {"state": "not_started", "wall_seconds": 0, "reason": "job_budget"}
            h._json(directory / f"{name}.process.json", result)
            return result
        spawned.append((name, deadline - before))
        h._durable(directory / f"{name}.stdout.log", b"Synthetic unmeasured process fixture\n")
        h._durable(directory / f"{name}.stderr.log", b"")
        state, code = "completed", 0
        if name == "compile":
            try:
                if mode == "compile_error":
                    raise OSError("Synthetic import/export failure")
                h._compile_child(directory)
                clock[0] += 410 if mode == "remaining" else 0.5
            except CompileCutoff:
                clock[0], state, code = deadline, "timeout", -9
            except OSError:
                clock[0] += 0.5
                code = 1
        else:
            repeat = int(name.removeprefix("check-r"))
            if mode == "crash":
                clock[0] += 1
                code = 1
            elif mode == "invalid_reply":
                clock[0] += 1
                h._durable(directory / f"r{repeat}.reply.json", b"invalid JSON\n")
            else:
                criteria = {
                    "passed": "equivalent",
                    "late_reply": "equivalent",
                    "returned": "no_information",
                    "unknown": "future_enum",
                    "not_equivalent": "not_equivalent",
                    "bad_acceptance": "equivalent",
                    "invalid_criterion": None,
                    "early_reply": "equivalent",
                    "invalid_clock": "equivalent",
                    "mixed": ["not_equivalent", "no_information", "equivalent"][repeat],
                }
                criterion = criteria.get(mode)
                if mode in criteria:
                    clock[0] += 1
                    h._json(
                        directory / f"r{repeat}.reply.json",
                        {
                            "compile_manifest_sha256": h._digest(
                                directory / f"r{repeat}.compile.json"
                            ),
                            "validation": {
                                "accepted": criterion == "equivalent" and mode != "bad_acceptance",
                                "criterion": criterion,
                            },
                            "returned_wall_ns": time.time_ns(),
                            "returned_monotonic_ns": False
                            if mode == "invalid_clock"
                            else int((clock[0] - 2 if mode == "early_reply" else clock[0]) * 1e9),
                        },
                    )
                if mode in {
                    "timeout",
                    "remaining",
                    "compile_partial",
                    "save_failure",
                    "late_reply",
                }:
                    clock[0], state, code = deadline, "timeout", -9
        result = {
            "state": state,
            "pid": 999999,
            "returncode": code,
            "wall_seconds": clock[0] - before,
            "cleanup_seconds": 0,
            "deadline_monotonic": deadline,
            "observed_monotonic": clock[0],
            "members_before_cleanup": [],
            "adopted_reaped": [],
            "members_after_cleanup": [],
        }
        h._json(directory / f"{name}.process.json", result)
        return result

    with monkeypatch.context() as patch:
        patch.setattr(h.time, "monotonic", lambda: clock[0])
        patch.setattr(h.time, "monotonic_ns", lambda: int(clock[0] * 1e9))
        patch.setattr(h.os, "sched_getaffinity", lambda _pid: set(spec["planned_affinity"]))
        patch.setattr(h, "_supervise", supervise)
        patch.setattr(h, "_event", event)
        patch.setattr(h.os, "fsync", fsync)
        report = h.run_job(
            job,
            directory,
            root=root,
            env={**os.environ, **spec["thread_env"]},
            campaign_sha256=h._digest(root / "campaign.json"),
            execution_identity=spec["execution_identities"][0],
        )
    return report, spawned


def finish_fixture(root, spec):
    first = json.loads((root / campaign.job_prefix(spec, 0) / "spec.json").read_text())
    started = {
        "created_at": datetime.fromtimestamp(
            (first["created_wall_ns"] - 1_000_000_000) / 1e9, UTC
        ).isoformat(),
        "monotonic_ns": int((first["start_monotonic"] - 1) * 1e9),
        "campaign_sha256": h._digest(root / "campaign.json"),
        "loadavg": list(os.getloadavg()),
        "affinity": spec["planned_affinity"],
        "thread_env": spec["thread_env"],
    }
    h._json(root / "RUN_STARTED", started)
    rows = [campaign.reconstruct(root, spec, i) for i in range(len(spec["schedule"]))]
    h._durable(
        root / "data/run.jsonl",
        "".join(
            json.dumps(
                {
                    "completed": i + 1,
                    "scheduled": len(rows),
                    "result": row,
                }
            )
            + "\n"
            for i, row in enumerate(rows)
        ).encode(),
    )
    document = campaign._document(spec, rows, started)
    campaign.finish(root, document)
    return document
