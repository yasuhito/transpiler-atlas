# Pilot v0.3: protocol and limitations

This is an end-to-end feasibility experiment, not the formal suite v1 proposed in the methodology. It tests compilation, output constraints, and equivalence with input/output wire maps taken into account.

## Reproduction

```bash
uv sync --frozen
uv run python atlas.py run --overwrite
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

The runner refuses a suite change without a matching archived results file. Repeating v0.3 requires `--overwrite`; preserve another snapshot first if the rerun must remain available. Tests generate inputs in temporary directories rather than changing published inputs.

## Target and pipelines

The physical width equals the input's total width. Targets are fully connected or linear, with bidirectional CX, the native basis `rz,sx,x,cx`, and no added workspace. These are Atlas-designed synthetic test conditions, not a named hardware device, a QASMBench requirement, or an adopted standard benchmark specification. All-to-all isolates compilation without connectivity restrictions; a line exercises placement and routing when only neighboring wires can interact. The source of this choice is the Atlas methodology proposal, not the input corpus. This differs from the proposed 32-physical-qubit suite v1 targets.

- **Qiskit:** preset level 2, `approximation_degree=1.0`, seeds 7/19/43.
- **pytket:** `FullPeepholeOptimise(allow_swaps=False)` → `DefaultMappingPass` using GraphPlacement → `SynthesiseTket` → `AutoRebase(rz,sx,x,cx,allow_swaps=False)`.
- **BQSKit:** standard level 1 `compile`, two-qubit maximum synthesis size, `synthesis_epsilon=1e-12`, explicit MachineModel for the shared target/basis, `with_mapping=True`, seeds 7/19/43, one local worker and one BLAS thread. [Adapter settings and numerical limitations](bqskit.md).

The pytket pipeline is explicit and specific to this experiment, not a claim about the default recommended pipeline for all backends. No seed is passed to this pipeline. Its three seed slots are repeated measurements, not three independently seeded configurations.

## Timing and environment

12 circuits in six families × 2 targets × 3 compilers × 3 seed slots = 216 scheduled entries, each with three compilation repetitions (648 potential output checks). All 216 entries completed without timeout or worker error. Of 648 recorded outputs, 597 passed the strict check; the other 51 are from 17 BQSKit line-target entries. Qiskit and pytket each passed all 72 entries; BQSKit passed 55 of 72. BQSKit verification failures retain their raw measurements in every UI view. Their Quality and Speed scores include a pass-rate penalty and an asterisk, rather than being hidden. The three newly added families each have only one instance; family-balanced weighting does not make this a representative corpus-wide evaluation.

The machine is shared. The runner pins affinity to the first permitted CPU and sets thread environment variables to one. CPU frequency, sibling hardware threads, and other jobs are not controlled. It is not an exclusive-machine measurement. Full metadata is in [results.json](../data/results.json).

Timing includes pipeline construction and compilation. SDK import, parsing, export, conversion for validation, equivalence checking, and BQSKit local runtime startup/shutdown are excluded. BQSKit model construction and workflow execution are timed. A new BQSKit runtime is created for every repetition, with one worker and one BLAS thread. The first repetition can include first-use costs; this is not a rigorously warm-only measurement.

Each entry runs in a new worker, with its three repetitions in the same process. A 120-second worker timeout includes all repetitions and checking. It is not a 60-second limit on one compilation. No memory cap is enforced. Timed-out workers and their local runtime descendants are terminated as one process group. Worker order is shuffled with a fixed seed.

The UI reports the median of the three timing repetitions within each seed slot, then the median across available measured slots, including slots whose strict equivalence check failed. Gate counts and depths use the same two-stage aggregation. Missing measurements are omitted rather than filled with zero or invented. Partial coverage is explicitly labeled; a median over two available slots is not a complete three-slot comparison. Every repetition is retained in the raw data. Timing tooltips show the recorded sample range.

## Output validation

Every recorded output is checked against a shared definition of the gate set, directed coupling edges, and gate arity. Maps enforce equal input/output width with no added workspace. Counts are taken from the final native output without reoptimization. The per-circuit view separates these output rules from QCEC equivalence. A verification-failed entry still passed output rules in this runner; a failed strict equivalence check is not a violation of the line topology.

2Q depth is the longest weighted path through the full qubit-dependency DAG: 2Q gates have weight one and 1Q gates have weight zero. Total depth gives every gate weight one. SDK-specific moment counts are not compared directly.

Initial and final maps come from Qiskit's layout, pytket's CompilationUnit, and BQSKit's `with_mapping=True` result. A validation copy restores input wire labeling and adds terminal measurements according to the final logical output order. These measurements are not present in the published native output or counted metrics.

QCEC's decision-diagram checkers run with simulation and ZX checking disabled, one thread, and a 20-second verification timeout. Only `equivalent` and `equivalent_up_to_global_phase` are accepted. The checker's default `1e-8` trace/identity threshold is unchanged for every compiler; no approximate or relaxed-verification track is mixed into the scores. `probably_equivalent` is not accepted. Floating-point angles and the checker's tolerances/assumptions still apply; this is not represented as an unconditional mathematical proof. Checker details are retained per trial.

During development, the adder exposed a mapping bug in the measurement code: Qiskit preserves register declaration order while pytket sorts register names. Maps now use the input declaration order, with an actual-pipeline regression test. Tests also deliberately corrupt a gate and a final map to ensure the checker rejects them.

## Scores and UI views

The current score version is **`qcec-adjusted-v1`**, shown in the report and embedded JSON. This is an exploratory benchmark rule, not the earlier all-or-nothing verified score, and not the proposed formal suite score. Earlier scores must not be compared directly with this version. The v0.3 measurement bytes, input hashes, compiler pipelines, and QCEC acceptance settings are unchanged; only presentation and scoring change.

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

Examples: QFT on the BQSKit line target has 4/9 passed slots, so its family score is its unpenalized performance × 4/9. BQSKit's full line selection has 19/36 passed slots, so its aggregate uses 19/36. For the 4-qubit Atlas QFT alone, the factor is 1/3. If no slot passes but measurements are available, Quality and Speed are zero, not N/A.

Scores with a pass rate below 100% carry **`*`** and a tinted cell. Hover text and the marked cell's keyboard/mobile-accessible Details control show performance before penalty, passed/required slots, and pass rate. Quality scores use one decimal; positive Speed scores below 1 use three decimals so small values remain visible. The footnote explains that the reduction includes failed or missing checks. This makes incomplete acceptance visible, not equivalent to fully verified output. Output-rule checks remain separate from QCEC.

N/A means a required raw metric or Qiskit reference is unavailable. Partial measured slots can provide a provisional performance median and score; their missing checks remain in the penalty denominator, and partial coverage is labeled. If any selected circuit lacks the metric needed for an aggregate score, that aggregate is N/A rather than silently dropping the circuit. Raw count/depth/time medians remain available over recorded values. No measurement or score is invented for a wholly unmeasured circuit.

The linear penalty is a declared policy choice. It treats each unaccepted slot equally, regardless of how near it was to QCEC's numerical tolerance. It does not measure approximation error, distinguish a tiny numerical difference from a large logical mismatch, or estimate quantum hardware success. Both Quality and Speed use the same penalty; raw compile time remains an unpenalized timing measurement. Future continuous-error or alternative penalty rules require another named score version.

- **Leaderboard:** adjusted Quality/Speed ranks, raw metric medians, family-adjusted Quality columns, measured-circuit coverage, and QCEC slot counts. Raw medians are neither normalized nor family-balanced. Sorting by raw metrics still ranks only fully verified outputs.
- **Per circuit:** adjusted scores, raw medians, timing ranges, separate output-rule and equivalence results, slot coverage, and QASM links.
- **Matrix:** adjusted scores include the penalty, asterisk, tint, and Details. Best-value shading compares adjusted scores; for raw metrics it only compares fully verified outputs. Verification labels remain visible even with detailed columns off.
- **Trade-off:** every available raw time/count or depth pair is plotted. Filled points passed all required checks; hollow points are unverified or partial. The plot is not a score ranking.

Compiler filtering retains the Qiskit reference and does not change the selected circuit set. Target, family, and width filters change that set, its pass-rate denominator, and its scores. Values from different selections or score versions are not directly comparable. URL fragments preserve view/filter state.

The small suite does not establish general SDK superiority, quantum hardware success probability, or performance on unmeasured algorithms such as Shor.
