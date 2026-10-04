# Standalone compile-retention protocol v1

This is a new measurement protocol, not a retry or replacement of the published
v0.4/QMAP/Cirq records. QCEC remains 3.10.1 and the dependency lock is unchanged.
The historical mixed-source report remains authoritative for its own campaigns.

## Workspace and ordered schedule

```sh
uv run atlas.py retention-campaign --into /tmp/ta-hardto/campaigns --prepare-only
# Inspect campaign.json, including its ordered schedule, before running.
# With the same locked Python environment, run the copied workspace once:
/path/to/locked/python /path/to/new/workspace/atlas.py retention-run
```

The default campaign extracts exactly 18 published timeout identities:
QASMBench Ising n10, BQSKit L2/L3/L4, line/all-to-all, seeds 7/19/43.
A canonical schedule is shuffled with seed 20261004 and stored before execution.
There are 54 scheduled repeats. No resume, selective retry or favorable-results
reuse is allowed. Jobs and checks run sequentially, without overlapping tests or
other agent-controlled heavy work. On a shared host the timings are diagnostic,
not matched-host performance comparisons.

## Target and pipelines

The existing `atlas.compile_once` recipes, input-width targets and timer boundaries
are unchanged. The whole job, including startup, import, export, saving and checks,
has one monotonic 420-second deadline. All three compilations precede verification.
Each fresh QCEC child gets the lesser of 60 seconds and remaining job time;
QCEC's cooperative timeout remains 20 seconds. An exhausted budget starts no child.
Cleanup/admin time is recorded separately; it does not extend the result deadline.

QASM and actual native QPY are saved create-only with compile time, raw metrics,
logical-to-physical initial/final maps in input declaration order, scalar phase,
input/source hashes and artifact hashes. File and directory fsync precede the
last-published compile manifest, the bundle's commit marker. An uncommitted orphan
is forensic evidence, not a measured repeat. QCEC reloads native QPY, never a QASM
re-import that might change scalar phase or numerical representation.

The parent owns one child process group at a time. Normal exit, timeout, exceptions
and cancellation kill the group, wait for the direct child, reap adopted descendants
through a Linux subreaper and confirm group disappearance before proceeding.
Uninterruptible OS I/O, a descendant escaping with `setsid`, supervisor SIGKILL
and host failure are outside this guarantee. A hard deadline is a kill-decision
bound, not a mathematical completion-time guarantee.

## Classification and scoring

Primary precedence is `error > compile_incomplete > not_equivalent >
verification_incomplete > passed`. Individual mixed facts are retained.
Only QCEC `not_equivalent` is an explicit mismatch. `equivalent` and
`equivalent_up_to_global_phase` are strictly accepted. `no_information`,
`equivalent_up_to_phase`, `probably_equivalent` and `probably_not_equivalent`
are unfinished verification, not demonstrated mismatch. A hard timeout or no
remaining budget is also unfinished. Crashes, malformed replies, export/I/O
failures and unknown criteria are errors. Passing requires three committed
compiles and three strict accepts.

Output rules (basis, coupling, width, maps, phase) are independent of equivalence.
Raw medians use available committed repeats and show n/3 coverage. Unfinished
verification remains in the scheduled seed-slot denominator and contributes zero
to the pass numerator. It does not itself make a score N/A. Quality and Speed each
require their necessary raw and reference measurements; missing required cases
are not silently excluded. Partial-repeat scoring is separately named
`qcec-adjusted-partial-v2`; historical `qcec-adjusted-v1` values are unchanged.
The 18-job diagnostic has no reference rows, so normalized scores are N/A and only
raw measurements/coverage are informative. This is not an approximation track.

## Seal and publication

Standalone `kind=compile-retention` uses spec, result schema and seal version 3.
The seal freezes source commit and byte inventory, lock and resolved versions,
inputs and corpus license, recipe and checker settings, deadlines, transport and
ordering policy, schedule, host/affinity/thread settings and UTC/monotonic facts.
Execution identities include recipe, input, verifier/environment, source and policy.
The same display configuration ID does not imply the same execution identity.

Before sealing, the maintained reader re-derives native metrics, map/phase/output
rules, hashes, check classifications, job precedence, medians and raw rows from
all scheduled terminal facts without re-running QCEC. Every referenced file and
forensic log/orphan is in the exact snapshot inventory. `MEASUREMENT_COMPLETE`
authenticates the create-only snapshot and is published last. A complete schedule
of unsuccessful checks can be sealed; a cancelled/incomplete schedule, corrupt
bundle or tampered file cannot. A seal means complete evidence, not all passed.

A FileMap must cover exactly every sealed file plus marker and snapshot. It cannot
backfill old rows or merge these identities into the existing mixed-source campaign.
A separately approved publication would add a standalone campaign archive, QASM,
QPY, manifests, logs, raw data, exact FileMap and a new standalone report/selector.
Existing historical bytes and scores stay unchanged. Local sealing or previewing
is not authorization to push, change the current selector or publish.

[Raw data](../data/results.json) and the [input manifest](../data/manifest.json)
are separate from the display-only configuration notes.
