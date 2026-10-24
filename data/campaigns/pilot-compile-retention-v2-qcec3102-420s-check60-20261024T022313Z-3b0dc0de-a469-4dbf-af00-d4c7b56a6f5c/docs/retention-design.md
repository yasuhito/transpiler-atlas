# Retention v2 design rationale

## Problem

QCEC 3.10.2 adds a supported hard-timeout worker, but its timer excludes caller-side
serialization and its cleanup does not own descendants. The new verifier needs a
new identity without changing sealed v1 evidence or the 13-configuration ranking.

## Usage (caller's view)

```sh
uv run atlas.py retention-campaign --into /tmp/ta-qcec3102/campaigns --prepare-only
/path/to/worktree/.venv/bin/python /path/to/frozen/workspace/atlas.py retention-run
uv run build_site.py
```

Creation selects v2 only. `publication.load(root, file_map=historical_map)` still
reads v1 without executing its archived Python or invoking QCEC. A different
FileMap and diagnostic selector select v2; neither replaces the root publication.

## Shape

The immutable closed `retention.Suite` values bind suite name, protocol revision,
verifier version and policy. `retention_campaign.frozen_suite(spec) -> Suite`
validates that boundary. `retention.run_job(job, directory, ...) -> Report` remains
the single runtime operation. `atlas.strict_pair(...)` and
`atlas.STRICT_CHECKER_OPTIONS` preserve one strict preparation/options definition.
The retained child calls `verify_with_hard_timeout` on native-QPY circuit objects.

The parent owns one process group, the absolute check deadline and all cleanup.
The child owns its entered/reply receipts, not process-tree supervision. The
compiler owns native bundles, manifest last. All three compile commits precede
checks. New timeout receipts are validated separately from historical verdicts;
`decode_check_reply(...)` derives the same five outcome categories. The reader
independently traverses native bytes and terminal facts before comparing rollups.
No new runtime source module, inventory lists, plugin interface or archive API is
needed. This hides version and transport details without a larger caller API.

Implementation review found two pre-existing boundary races. Completion is now
classified using the observation after the exit probe, so scheduler delay cannot
accept a late result. V2 no-start receipts record the actual observation and cutoff,
allowing start-receipt fsync to exhaust a check budget without preventing sealing.
The reader validates those clocks and keeps v1's original no-start schema intact.
These are local deadline corrections, not a new supervision or ownership model.

## Synthesis decision

Three independent designs compared a small functional integration, a protocol
object and a separate checker module. A separate cross-judge and the parent both
selected the functional design. We retained its closed suite table in existing
files and exact v1 policy. We incorporated the other designs' single-clock budget,
read-only historical gate, duplicate package-name rejection and save/cleanup barrier
tests, plus the judge's shared strict options/preparation and direct one-off archive.

We rejected the object/module alternatives because they require historical source
inventory variants and extra ownership/import seams. We rejected a new archive
API because this is one approved operation. Unlike the judge's no-reserve option,
we retained a fixed 1-second receipt reserve inside the cap: genuine upstream
expiry would otherwise necessarily lose to the outer cutoff. This permits an
explicit authenticated API timeout path without extra time or retries. Ordinary
worker exceptions retain the existing nonzero-exit error path and sealed stderr.

An independent implementation review found two pre-existing deadline races, both
reproduced before correction. V2 no-start facts now record the actual supervisor
observation and cutoff, so receipt fsync that exhausts a window is a sealable
incomplete check rather than a reader error. Completion is classified from the
post-wait observation, so scheduler preemption cannot admit a late result. This
is a narrow deviation from leaving supervision untouched, not a second owner or
a new deadline policy; v1's stored no-start schema remains readable.

## Tradeoffs accepted

- We accept at most one second less inner worker time for a durable timeout reply.
  Scheduling/serialization may still consume it; the outer cutoff remains final.
- We accept a separate v2 reply decoder for exact historical v1 semantics.
- We accept regenerated display-only v1 HTML for correct per-campaign prose,
  without changing any sealed v1 byte or its selector.
- We accept separately recorded teardown beyond the cutoff for descendant cleanup,
  not for additional eligible verification time.

## Alternatives considered

A no-reserve API call has a smaller receipt surface, but cannot record genuine
worker expiry before the authoritative outer cutoff. A new protocol module hides
identity behind an object but exposes inventory and storage seams to its callers.
Duplicating whole runners would create two owners of persistence and deadlines.

## Open questions and risks

Can shared-host scheduling consume the receipt reserve? The backstop handles that
without retry. Can a descendant escape its group or block in uninterruptible I/O?
The existing Linux/supervisor/host-failure limitations remain, not a stronger
process-tree guarantee from QCEC.

## Next implementation step

The implementation gate exercises exact suite/version binding, the actual sealed
v1 reader, real API dict/timeout/exception behavior, QPY phase/maps, descendants,
serialization, remaining budgets and receipt tampering. Only committed clean
source may begin the single fresh sequential 18-job measurement. Sealing and the
existing reader authenticate the direct archive and exact FileMap before building
the separate diagnostic page. No push or PR is part of this operation.
