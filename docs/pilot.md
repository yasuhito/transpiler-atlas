# Pilot protocol and preserved measurements

## Cirq addition: pilot-v0.6-cirq-mixed-budgets

Only `cirq-routecqc-maponly-v1` is newly measured, with `cirq-core==1.7.0`.
It uses the original frozen QASM2, RouteCQC and translation-only native lowering.
No QMAP optimization-enabled configuration is added. See [Cirq recipe](cirq.md).

The standalone `pilot-cirq-routecqc-v1-420s` cohort has 72 entries, three real
compilations per entry, and a 420-second full-worker budget. Slots 7/19/43 repeat
an unseeded pipeline (`seed_supported=False`), not a fictitious mapper RNG seed.
The combined dataset has 936 entries and 13 configurations from three sources:
792 unchanged v0.4 records, 72 unchanged QMAP v1 records, and 72 new Cirq records.
Source budgets, environments and windows remain separate. v0.4 retains 750
initial 120-second outcomes and 42 timeout-only 600-second retries; QMAP v1 and
Cirq each retain their own 420-second window. This is not a matched-budget rerun.
No historical raw file, attempt, artifact, snapshot or publication selector is
replaced. Scores and the reused Qiskit L2 reference are unchanged.

```sh
uv sync --frozen
uv run --frozen python atlas.py campaign --into /tmp/ta-cirq/campaigns
```

Do not run tests or other BQSKit work concurrently with measurement. Each fresh
workspace admits Cirq only and measures once. Interrupted workspaces cannot resume
or selectively retry. A completed local report can be built without publication.

## Preserved mixed-source suite: pilot-v0.5-qmap-mixed-budgets

The approved decision replaces the proposed 864-worker rerun with a **QMAP-only
campaign of 72 entries**: 12 frozen inputs × 2 targets × 3 seed slots, each with
three repetitions. Only `qmap-sc-heuristic-maponly-v1` is measured anew, using the
420-second full-worker budget from `atlas.WORKER_TIMEOUT_SECONDS`.

The combined suite is named **`pilot-v0.5-qmap-mixed-budgets`** instead of
`pilot-v0.5-qmap-420s`, because a single 420-second suffix would imply equal
admission budgets for all configurations. Its 864 records consist of 72 new
QMAP records plus **792 unchanged v0.4 records** for the existing 11 configurations.
The standalone measurement suite is `pilot-qmap-v1-420s`.

### Provenance and interpretation

v0.4 was measured initially with **120-second workers**. Only the **42 initial
timeouts** were retried at **600 seconds**; 750 initial completed outcomes were
retained. This is not a uniformly 600-second campaign. The original protocol is
retained under `protocol.measurement_sources['v0.4'].protocol`, including
`initial_worker_timeout_seconds=120`, `worker_timeout_seconds=600`,
`timeout_retry_entries=42`, and
`initial_attempt_snapshot=data/attempts/pilot-v0.4-120s.json`.

`protocol.configuration_sources` associates every configuration with its source.
Every reused record, including `previous_attempts` and any explicit
`worker_timeout_seconds`, is unchanged. An initial record without a per-record
budget uses its source's initial 120-second budget, not the retry budget.
The QMAP source records 420 seconds for each new worker. The combined protocol
has **no universal worker_timeout_seconds**. Source environments, timestamps,
raw files and digests remain separate. A visible page note and per-configuration
labels explain the mixed budgets and different measurement windows.

The Qiskit L2 reference is reused unchanged from v0.4. The scoring equations,
nested medians, QCEC pass-rate penalty, required slots, missing/reference N/A
rules, strict checker tolerances, frozen inputs, basis, bidirectional targets,
equal width and no-added-ancilla rule are unchanged. This authorized reuse does
not make the comparison a matched-budget experiment. Timing and pass rates can
be affected by different admission budgets, host load and measurement windows.
Ranks may change when adding QMAP; the old configurations' scores and raw values
do not change.

### Run and build

```sh
uv sync --frozen
# Creates a new workspace without measuring:
uv run --frozen python atlas.py campaign --into /tmp/ta-qmap/campaigns --prepare-only
# Measures only the 72 QMAP entries, one worker at a time:
uv run --frozen python atlas.py campaign --into /tmp/ta-qmap/campaigns
```

Do not run pytest or another BQSKit job during the QMAP campaign. See
[QMAP recipe and workspace lifecycle](qmap.md) for source/artifact ownership,
standalone versus combined data, budget records, seals and local site generation.
The repository's historical data is never overwritten. Resume and overwrite
remain refused. `retry-timeouts` is removed: v0.4's retry has already happened
and is provenance, not an operation to repeat. A QMAP timeout remains in its
source cohort; selective retries would change the measurement window. A new
QMAP cohort would require a new workspace and explicit execution approval.

## Preserved v0.4 protocol

The remainder documents the historical v0.4 dataset, including its original
commands and budget. Those commands refer to the preserved v0.4 source, not the
new runner, which refuses to overwrite historical results.

This is an end-to-end feasibility experiment, not the formal suite v1 proposed in the methodology. It tests compilation, output constraints, and equivalence with input/output wire maps taken into account.

## Historical reproduction

```bash
uv sync --frozen
uv run python atlas.py run --overwrite  # fresh full matrix, 600-second workers
uv run python build_site.py
uv run pytest -q
uv run ruff check .
npm ci
npm test
```

The runner requires Linux CPU affinity and Python 3.12. Dependencies are locked in `uv.lock`. No cloud authentication, paid API, or quantum hardware is used. IBM client packages are installed as dependencies of pytket-qiskit, but no service is called.

Open `index.html` directly in a browser. The benchmark data is embedded, and local CSS/JavaScript, documentation, and output artifacts work with `file://`. Publish the entire site tree, not only the HTML file. Alternatively:

```bash
python -m http.server 8765 --directory . --bind 127.0.0.1
```

Then open `http://localhost:8765/`. Results and HTML are generated artifacts and should not be edited by hand.

## Inputs

| Family | Instances | Definition |
| --- | --- | --- |
| QFT | 4 and 6 qubits | Exact QFT including final bit reversal |
| QAOA | 4 and 6 qubits | MaxCut-style ring graph with one chord, p=2, fixed nontrivial angles |
| Adder | 6 and 8 total qubits | CDKM full ripple-carry adder with 2/3-bit registers and carry-in/out |
| QFT (QASMBench) | 4 qubits | `qft_n4`, including its preparation gates, no added reversal |
| QAOA (QASMBench) | 3 qubits | `qaoa_n3`, fixed p=1 cost-function instance and angles |
| Adder (QASMBench) | 4 qubits | `adder_n4`, published fixed circuit including preparation |
| Grover (QASMBench) | 2 qubits | `grover_n2`, published fixed oracle/diffusion circuit |
| VQE (QASMBench) | 4 qubits | `vqe_n4`, published fixed ansatz angles, no energy/optimizer evaluation |
| Hamiltonian (QASMBench) | 10 qubits | `ising_n10`, published fixed Ising circuit |

The six original inputs are generated with Qiskit; six additional inputs are imported from QASMBench. All are lowered, without optimization or topology constraints, to `h,x,rx,ry,rz,cx` using level 0. All three compilers receive the same frozen OpenQASM 2 input. The input manifest and hashes are unchanged from v0.2.

This is a **common low-level input track**, not a generator-independent high-level comparison. The chosen generator and lowering rules can influence results and remove useful algorithmic structure. No claim is made that this input track evaluates every compiler's high-level capabilities fairly.

[manifest.json](../data/manifest.json) records the input SHA-256 hashes, parameters, and widths. The original six circuits use public Qiskit APIs and explicitly described algorithms. The new six are redistributed QASMBench files with their upstream license retained. [Corpus provenance and license review](corpora.md) describes the fixed revision, transformations, and limits. Original files, upstream URLs, source hashes, removed-instruction counts, and lowered-input hashes are recorded for each imported case. The unitary checker checks the whole input circuit, including the adder's carry wires, rather than testing only a chosen basis input.

## Release preservation

Earlier published measurement snapshots and their source/dependency trees are retained in the repository under `releases/`, but are not linked from the current site. Current results are a new measurement of all 12 cases, not a merge of old and new timings. Cross-release absolute timing comparisons are not controlled comparisons.

The runner refuses a suite change without a matching archived results file. Repeating v0.4 requires `--overwrite`; preserve another snapshot first if the rerun must remain available. v0.3 is retained as a standalone snapshot, without an active site link. Tests generate inputs in temporary directories rather than changing published inputs.

For a long fresh batch, redirect stdout to a JSON-lines log. `atlas.py run --resume-log <log>` can continue a saved contiguous schedule prefix after interruption, provided inputs, code/settings, dependencies, and host conditions are unchanged. Resume checks the scheduled job identities and artifact availability, not arbitrary changes to compilation settings. The published campaign resumed after 619 entries; completed outputs were retained rather than remeasured.

## Target and pipelines

The physical width equals the input's total width. Targets are fully connected or linear, with bidirectional CX, the native basis `rz,sx,x,cx`, and no added workspace. These are Atlas-designed synthetic test conditions, not a named hardware device, a QASMBench requirement, or an adopted standard benchmark specification. All-to-all isolates compilation without connectivity restrictions; a line exercises placement and routing when only neighboring wires can interact. The source of this choice is the Atlas methodology proposal, not the input corpus. This differs from the proposed 32-physical-qubit suite v1 targets.

Each ranking entry is one **SDK/configuration pair**, not one SDK. The 11 configurations are recorded in `protocol.configurations`; each result carries both `compiler` (SDK) and `configuration_id`. Schema version 2 uses `(case_id, configuration_id, target, seed)` as the unique entry key. Artifact filenames include the configuration ID.

| SDK | Separate entries | Shared settings |
| --- | --- | --- |
| Qiskit | Native preset levels **0, 1, 2, 3** | `approximation_degree=1.0`, shared native basis/coupling, seeds 7/19/43 |
| pytket | **Basic synthesis**, **Peephole**, **Pauli + peephole** | Explicit recipes followed by the same mapping/rebase suffix |
| BQSKit | Native compile levels **1, 2, 3, 4** | `max_synthesis_size=2`, `synthesis_epsilon=1e-12`, shared MachineModel, returned maps, one worker/BLAS thread, seeds 7/19/43 |

Qiskit level 0 is available; BQSKit level 0 is not. Levels are native SDK choices, **not equal effort units across SDKs**, and a higher number is not a guarantee of better measured output. BQSKit's two-qubit synthesis-block cap does not change the full input circuit width. [BQSKit settings and limitations](bqskit.md).

The approx. label is explanatory configuration metadata for stock BQSKit levels 2, 3, and 4, whose workflows use numerical re-instantiation and can leave residual unitary differences. Strict QCEC acceptance is not guaranteed. The synthesis epsilon of 1e-12 is an internal cost threshold, not a whole-circuit operator-norm guarantee. The label neither defines a separate approximate-acceptance track nor changes the stock pipeline or configuration ID. Unmarked configurations, including level 1, are not guaranteed exact. [Numerical approximation and unfinished checks](bqskit.md#numerical-approximation-and-unfinished-checks) describes the investigated one-circuit, seed-7 samples and their limits.

The pytket entries are Atlas recipes, not official universal optimization levels:

- Basic: `SynthesiseTket()`.
- Peephole: `FullPeepholeOptimise(allow_swaps=False)`.
- Pauli + peephole: `GreedyPauliSimp(seed=slot, thread_timeout=5, trials=1, only_reduce=True)` then `FullPeepholeOptimise(allow_swaps=False)`.
- Every recipe then applies `DefaultMappingPass(Architecture(edges))` using GraphPlacement, `SynthesiseTket()`, and `AutoRebase(rz,sx,x,cx,allow_swaps=False)`.

Basic and Peephole are unseeded: their three seed slots repeat the same pipeline. Pauli uses the scheduled seed for candidate selection. Its internal five-second search timeout is an algorithm setting, distinct from the worker's 600-second wall budget. GreedyPauliSimp does not preserve global phase; the unchanged verifier accepts equivalence up to global phase. These recipes are not claimed to be the recommended backend defaults.

## Timing and environment

12 circuits in six families × 2 targets × **11 configurations** × 3 seed slots = **792 scheduled entries**, each with three repetitions (2,376 potential output checks). After the 600-second timeout retry, 633 entries passed, 141 completed with failed strict verification, and 18 remained timed out; there were no worker errors. The 774 completed entries contain 2,322 output trials, of which 1,899 passed QCEC.

All four Qiskit levels and pytket Basic/Peephole passed 72/72 entries each. pytket Pauli passed 42/72. BQSKit levels 1/2/3/4 passed 55/39/41/24 of 72 entries respectively. BQSKit levels 2/3/4 each have six remaining timeouts, all on the 10-qubit Hamiltonian input across both targets. This is a limit of the recorded campaign, not a claim that the SDK cannot compile that circuit.

Verification-failed outputs retain counts, depths, and times. Their scores use the unchanged pass-rate penalty and asterisk. Entirely unmeasured cases remain N/A. A timed-out worker with no saved measurements is not verified and has no completed measurement. It is not a returned equivalence failure. Diagnostic compilation times and distances do not replace missing campaign records. Grover, VQE, and Hamiltonian each have only one instance; family balancing does not make this a representative corpus-wide evaluation.

The machine is shared. The runner pins affinity to the first permitted CPU and sets thread environment variables to one. CPU frequency, sibling hardware threads, and other jobs are not controlled. It is not an exclusive-machine measurement. Full metadata is in [results.json](../data/results.json).

Timing includes pipeline construction and compilation. SDK import, parsing, export, conversion for validation, equivalence checking, and BQSKit local runtime startup/shutdown are excluded. BQSKit model construction and workflow execution are timed. A new BQSKit runtime is created for every repetition, with one worker and one BLAS thread. The first repetition can include first-use costs; this is not a rigorously warm-only measurement.

Each circuit/configuration/target/seed entry runs in a new worker containing three repetitions. The **600-second worker wall budget** includes SDK imports, parsing, pipeline construction, all three compilations, QCEC checks, export, and runtime startup/shutdown. It is not 600 seconds per compilation. QCEC's individual verification timeout is configured as 20 seconds. In the investigated stock BQSKit level-2 Hamiltonian output, the alternating checker did not finish within the bounded diagnostic run, and this setting was not enforced as a strict wall-clock cap. The campaign's external 600-second worker limit remained in force. The same checker path has not been confirmed for every remaining timeout. No memory cap is enforced. Timed-out workers and their descendants are terminated as one process group. The initial full schedule is shuffled with a fixed seed.

The campaign initially used 120-second workers. Of 792 entries, 750 completed and 42 timed out. Only those 42 were retried with 600 seconds; **all 750 completed outcomes were retained exactly**, including strict verification failures. The retry completed 24 more entries, all verification-failed, leaving 18 timeouts. Completed initial jobs already satisfied the new 600-second admission budget. Timing variability across the two measurement windows is not controlled.

The initial results are preserved in [the 120-second attempt snapshot](../data/attempts/pilot-v0.4-120s.json). Retried records retain their complete initial result under `previous_attempts` and record `worker_timeout_seconds=600`; the protocol identifies retained initial outcomes and the initial budget. `atlas.py retry-timeouts` retries only timeouts recorded below the current budget, validates input hashes/dependency versions and restores affinity/thread settings, and saves after every retry. It does not retry verification failures or repeat already attempted 600-second timeouts. The published results retain both the original and updated timestamps.

The UI reports the median of the three timing repetitions within each seed slot, then the median across available measured slots, including slots whose strict equivalence check failed. Gate counts and depths use the same two-stage aggregation. Missing measurements are omitted rather than filled with zero or invented. Partial coverage is explicitly labeled; a median over two available slots is not a complete three-slot comparison. Every repetition is retained in the raw data. Timing tooltips show the recorded sample range.

## Output validation

Every recorded output is checked against a shared definition of the gate set, directed coupling edges, and gate arity. Maps enforce equal input/output width with no added workspace. Counts are taken from the final native output without reoptimization. The per-circuit view separates these output rules from QCEC equivalence. A verification-failed entry still passed output rules in this runner; a failed strict equivalence check is not a violation of the line topology.

2Q depth is the longest weighted path through the full qubit-dependency DAG: 2Q gates have weight one and 1Q gates have weight zero. Total depth gives every gate weight one. SDK-specific moment counts are not compared directly.

Initial and final maps come from Qiskit's layout, pytket's CompilationUnit, and BQSKit's `with_mapping=True` result. A validation copy restores input wire labeling and adds terminal measurements according to the final logical output order. These measurements are not present in the published native output or counted metrics.

QCEC's decision-diagram checkers run with simulation and ZX checking disabled, one thread, and a 20-second verification timeout. Only `equivalent` and `equivalent_up_to_global_phase` are accepted. The checker's default `1e-8` trace/identity threshold is unchanged for every compiler; no approximate or relaxed-verification track is mixed into the scores. `probably_equivalent` is not accepted. Floating-point angles and the checker's tolerances/assumptions still apply; this is not represented as an unconditional mathematical proof. Checker details are retained per trial.

Strict acceptance remains a numerical decision under the unchanged 1e-8 trace/identity threshold. Independent operator-norm distances are diagnostic evidence, not that threshold's definition and not a substitute QCEC result. The investigated output was not accepted within the worker budget, but a timeout does not establish a returned not_equivalent verdict. The diagnostics do not attribute the 111 completed BQSKit verification failures to this cause.

During development, the adder exposed a mapping bug in the measurement code: Qiskit preserves register declaration order while pytket sorts register names. Maps now use the input declaration order, with an actual-pipeline regression test. Tests also deliberately corrupt a gate and a final map to ensure the checker rejects them.

## Scores and UI views

The current score version is **`qcec-adjusted-v1`**, shown in the report and embedded JSON. This is an exploratory benchmark rule, not the earlier all-or-nothing verified score, and not the proposed formal suite score. Earlier scores must not be compared directly with this version. v0.4 introduces freshly measured configuration entries; v0.3 remains preserved separately. The score formula, frozen input hashes, and QCEC acceptance settings are unchanged.

First compute unpenalized performance for each circuit from every available measured seed slot, including verification-failed outputs:

```text
Quality before penalty = 100 × sqrt((G_ref + 1)/(G + 1) × (D_ref + 1)/(D + 1))
Speed before penalty   = 100 × max(T_ref, 1 ms)/max(T, 1 ms)
```

G is median 2Q count, D is median 2Q depth, and T is nested median compile time. The reference is the same run's measured Qiskit level 2 configuration. Its unpenalized performance is anchored at 100; its displayed adjusted score would be lower if its own QCEC checks failed. `+1` smoothing and the 1 ms floor are benchmark choices, not a physical cost model.

For a family or complete selected set, combine unpenalized per-circuit performance by geometric mean within each family, then geometric mean across families. Families receive equal weight **for performance**. Then apply one pass-rate factor for exactly that selected set:

```text
QCEC pass rate = passed required seed slots / all required seed slots
Quality = Quality before penalty × QCEC pass rate
Speed   = Speed before penalty × QCEC pass rate
```

Each required seed slot receives equal weight in this factor. A slot passes only if the worker status is passed and all three recorded output repetitions are accepted by QCEC. Failed, missing, timed-out, or ambiguous duplicate seed slots do not count as passed; the denominator remains the predefined number of selected circuits × three seeds. The factor is not the percentage of fully verified circuits, and not a percentage of hardware shots. Geometrically averaging already-penalized circuit scores is deliberately avoided: one zero does not automatically zero an entire family that has other passing slots.

Examples: QFT for BQSKit level 1 on the line target has 4/9 passed slots, so its family score is its unpenalized performance × 4/9. BQSKit level 1's full line selection has 19/36 passed slots, so its aggregate uses 19/36. For the 4-qubit Atlas QFT alone, the factor is 1/3. If no slot passes but measurements are available, Quality and Speed are zero, not N/A.

Scores with a pass rate below 100% carry **`*`** and a tinted cell. Hover text and the marked cell's keyboard/mobile-accessible Details control show performance before penalty, passed/required slots, and pass rate. Quality scores use one decimal; positive Speed scores below 1 use three decimals so small values remain visible. The footnote explains that the reduction includes failed or missing checks. This makes incomplete acceptance visible, not equivalent to fully verified output. Output-rule checks remain separate from QCEC.

The approx. tag is separate from *. It describes a configuration's numerical synthesis and adds no penalty. Individual QCEC outcomes still determine the pass-rate factor. The tag may appear on a circuit whose checks passed or whose measurements are unavailable. [Configuration notes (display metadata)](../data/configuration-notes.json) are generated as an optional sidecar joined by configuration ID, not a complete measurement dataset. The builder overlays the notes on a displayed protocol copy; the original results bytes, execution registry, attempt snapshot, and release snapshots remain unchanged.

N/A means a required raw metric or Qiskit reference is unavailable. Partial measured slots can provide a provisional performance median and score; their missing checks remain in the penalty denominator, and partial coverage is labeled. If any selected circuit lacks the metric needed for an aggregate score, that aggregate is N/A rather than silently dropping the circuit. Raw count/depth/time medians remain available over recorded values. No measurement or score is invented for a wholly unmeasured circuit.

The linear penalty is a declared policy choice. It treats each unaccepted slot equally, regardless of how near it was to QCEC's numerical tolerance. It does not measure approximation error, distinguish a tiny numerical difference from a large logical mismatch, or estimate quantum hardware success. Both Quality and Speed use the same penalty; raw compile time remains an unpenalized timing measurement. Future continuous-error or alternative penalty rules require another named score version.

- **Leaderboard:** adjusted Quality/Speed ranks, raw metric medians, family-adjusted Quality columns, measured-circuit coverage, and QCEC slot counts. Raw medians are neither normalized nor family-balanced. Sorting by raw metrics still ranks only fully verified outputs.
- **Per circuit:** adjusted scores, raw medians, timing ranges, separate output-rule and equivalence results, slot coverage, and QASM links.
- **Matrix:** adjusted scores include the penalty, asterisk, tint, and Details. Best-value shading compares adjusted scores; for raw metrics it only compares fully verified outputs. Verification labels remain visible even with detailed columns off.
- **Trade-off:** every available raw time/count or depth pair is plotted. Filled points passed all required checks; hollow points are unverified or partial. The plot is not a score ranking.

Compiler filtering retains the Qiskit reference and does not change the selected circuit set. The SDK filter shows all its configurations; the independent effort/configuration filter selects a single entry without removing the level-2 reference. Target, family, and width filters change the circuit set, its pass-rate denominator, and its scores. The plot uses SDK colors and identifies each configuration in point descriptions. Values from different selections or score versions are not directly comparable. URL fragments preserve view/filter state.

The small suite does not establish general SDK superiority, quantum hardware success probability, or performance on unmeasured algorithms such as Shor.
