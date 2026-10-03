# BQSKit adapter: Pilot v0.4

## Explicit pipeline

BQSKit 1.2.1 and bqskitrs 0.4.1 are locked alongside the unchanged v0.2 compiler dependencies. All 11 SDK/configuration entries are measured on the same 12 frozen inputs in one campaign. v0.3 timings are not merged into v0.4. The campaign retained 750 completed initial outcomes and retried only its 42 initial timeouts at the increased 600-second budget.

The adapter uses BQSKit's public standard `compile` workflow, not a custom optimization sequence:

| Setting | Value |
| --- | --- |
| Input | The same lowered OpenQASM 2 circuit used by Qiskit and pytket |
| Target width | Input width, no workspace |
| MachineModel gates | `RZGate`, `SXGate`, `XGate`, `CNOTGate` |
| Coupling graph | Undirected line or complete graph, corresponding to the shared bidirectional CX target |
| Optimization level | Separate entries for 1, 2, 3, and 4 |
| Maximum synthesis size | 2 qubits |
| Synthesis epsilon | `1e-12` |
| Seed | 7, 19, 43, passed to `compile` |
| Mapping | `with_mapping=True` |
| Local runtime | 1 worker, 1 BLAS thread |
| Internal error threshold | `None`; the shared external QCEC check decides acceptance |

Level numbers are not equivalent optimization budgets across SDKs. All four supported native levels are measured with a fixed two-qubit block cap. Level 0 is not supported by BQSKit. Other block sizes, precisions, worker counts, and customized workflows remain unmeasured; this is not a complete quality/time frontier. This uses numerical synthesis and must not be described as an exact symbolic compiler or as guaranteeing `1e-12` whole-circuit error.

Primary sources: the [versioned standard compile implementation and parameter documentation](https://github.com/BQSKit/bqskit/blob/1.2.1/bqskit/compiler/compile.py), [Compiler runtime documentation](https://bqskit.readthedocs.io/en/latest/source/autogen/bqskit.compiler.Compiler.html), [MachineModel documentation](https://bqskit.readthedocs.io/en/latest/source/autogen/bqskit.compiler.MachineModel.html), and [versioned Qiskit conversion adapter](https://github.com/BQSKit/bqskit/blob/1.2.1/bqskit/ext/qiskit/translate.py).

## Numerical approximation and unfinished checks

| Config | Target | Seed | Operator-norm distance | CX | 2Q depth |
| --- | --- | ---: | ---: | ---: | ---: |
| bqskit-l2 | all-to-all | 7 | 8.437908e-08 | 90 | 20 |
| bqskit-l2 | all-to-all | 19 | 5.957263e-08 | 90 | 20 |
| bqskit-l2 | all-to-all | 43 | 5.821035e-08 | 90 | 20 |
| bqskit-l2 | line | 7 | 8.437924e-08 | 90 | 20 |
| bqskit-l2 | line | 19 | 5.957263e-08 | 90 | 20 |
| bqskit-l2 | line | 43 | 5.821035e-08 | 90 | 20 |
| bqskit-l3 | all-to-all | 7 | 4.794312e-08 | 90 | 20 |
| bqskit-l3 | all-to-all | 19 | 5.863893e-08 | 90 | 20 |
| bqskit-l3 | all-to-all | 43 | 2.420374e-08 | 90 | 20 |
| bqskit-l3 | line | 7 | 4.794275e-08 | 90 | 20 |
| bqskit-l3 | line | 19 | 5.863893e-08 | 90 | 20 |
| bqskit-l3 | line | 43 | 2.420374e-08 | 90 | 20 |
| bqskit-l4 | all-to-all | 7 | 1.140336e-07 | 90 | 20 |
| bqskit-l4 | all-to-all | 19 | 1.145717e-07 | 90 | 20 |
| bqskit-l4 | all-to-all | 43 | 8.513146e-08 | 90 | 20 |
| bqskit-l4 | line | 7 | 1.140336e-07 | 90 | 20 |
| bqskit-l4 | line | 19 | 1.145717e-07 | 90 | 20 |
| bqskit-l4 | line | 43 | 8.513146e-08 | 90 | 20 |

L4 all-to-all seed 19 ran while a BQSKit runtime port collision ("Address already in use") was logged, so its CPU pinning and compile time are not guaranteed; the distance, computed from the saved output, is valid.

Distances are global-phase-aligned operator norms comparing the saved outputs, with wire maps accounted for, against the original input's 1024x1024 unitary; no QCEC was run for these diagnostics, and no angles were rounded or snapped.

These are independent diagnostics on one circuit, ising_n10, at seeds 7, 19, and 43. They are not campaign measurements, QCEC verdicts, corpus-wide error bounds, or evidence of the stopping path of the campaign's timeouts. The earlier all-to-all seed-7 reference distances were 2.96e-14 for Qiskit level 2 and 1.59e-14 for BQSKit level 1; they do not guarantee that level 1 is exact. Levels 2, 3, and 4 are labeled approx.; level 1 is not labeled. Absence of the label does not guarantee exact equivalence.

Stock level 2 ends with gate-deletion optimization. In BQSKit 1.2.1, ScanningGateRemovalPass removes a candidate gate, re-instantiates the remaining parameters, and accepts the candidate when its scalar cost is below success_threshold. Atlas sets this threshold through synthesis_epsilon=1e-12. The acceptance branch does not independently check a unitary-difference norm. In the investigated sample, the first accepted removal had cost 0.0 but operator-norm distance 1.516e-8; the final output distance was 8.44e-8. The internal threshold therefore must not be interpreted as a 1e-12 whole-circuit distance guarantee.

Levels 3 and 4 use the same deletion pass with iterative numerical resynthesis; level 4 also uses permutation-aware synthesis and mapping. Their observed residuals are not attributed to a single deletion step: no pass-level bisect was performed for those levels.

The unchanged QCEC alternating checker did not finish on the investigated level-2 output within the bounded diagnostic runs. Its configured 20-second timeout was not a strict wall-clock cap. The recorded campaign has 18 worker timeouts on ising_n10 across levels 2, 3, and 4. Those workers retained no completed measurements and remain not verified, with N/A metrics. They are not recorded not_equivalent verdicts. The identical stopping path has not been established for all 18 workers.

The approx. label explains a property of the stock numerical configuration, not a verifier change. Strict QCEC acceptance is not guaranteed. The strict QCEC trace/identity threshold remains 1e-8. The operator-norm distances above are a different diagnostic quantity and do not themselves constitute QCEC verdicts or mathematical proofs. Completed verification-failed outputs retain their original criteria, measurements, and pass-rate penalties. These diagnostics do not establish the cause of the 111 completed BQSKit verification failures. The annotation changes no score or rank. [Configuration notes (display metadata)](../data/configuration-notes.json) are a generated optional sidecar, not a replacement for raw results.

Versioned sources: [scan acceptance branch](https://github.com/BQSKit/bqskit/blob/1.2.1/bqskit/passes/processing/scan.py#L128-L135), [deletion and resynthesis builders](https://github.com/BQSKit/bqskit/blob/1.2.1/bqskit/compiler/compile.py#L1344-L1415), [level-2 workflow](https://github.com/BQSKit/bqskit/blob/1.2.1/bqskit/compiler/compile.py#L1462-L1512), [level-3 workflow](https://github.com/BQSKit/bqskit/blob/1.2.1/bqskit/compiler/compile.py#L1515-L1575), and [level-4 workflow](https://github.com/BQSKit/bqskit/blob/1.2.1/bqskit/compiler/compile.py#L1578-L1639).

## Timing boundary and process lifecycle

Input conversion and local runtime startup/shutdown are outside the compile timer. A fresh local runtime is created for every repetition. The measured interval includes MachineModel construction, standard workflow construction, submission, execution, and result retrieval. Output conversion, export, metrics, and QCEC are outside the timer.

BQSKit's local runtime communicates between processes; this is not a remote cluster, paid service, or hardware job. The 600-second worker budget includes runtime startup/shutdown, all three repetitions, and validation. If a worker times out, the runner terminates its entire process group, including local runtime descendants. Runtime initialization cost is not reflected in the displayed compile time; the numbers do not estimate application end-to-end latency.

## Recorded completion

Each configuration schedules 72 entries across both targets.

| Configuration | Passed | Verification failed | Timed out at 600 s |
| --- | --- | --- | --- |
| Qiskit levels 0/1/2/3, each | 72 | 0 | 0 |
| pytket Basic/Peephole, each | 72 | 0 | 0 |
| pytket Pauli + peephole | 42 | 30 | 0 |
| BQSKit level 1 | 55 | 17 | 0 |
| BQSKit level 2 | 39 | 27 | 6 |
| BQSKit level 3 | 41 | 25 | 6 |
| BQSKit level 4 | 24 | 42 | 6 |

No worker errors were recorded. The 18 remaining timeouts are the 10-qubit Hamiltonian case for levels 2/3/4, both targets and all seeds. All-circuit Quality/Speed scores for those configurations are N/A because a required circuit has no measurements; selecting a measured family/width permits score comparison. **QCEC failure alone does not cause N/A** when raw metrics exist.

The initial 120-second campaign timed out 8/12/22 entries for levels 2/3/4 respectively. At 600 seconds, 2/6/16 additional entries completed, all failing the unchanged strict verification check. Initial outcomes, retry histories, and completed timings are preserved. The longer worker budget changes completion eligibility, not synthesis precision or QCEC tolerance.

Across the 11 configurations, 2,322 outputs were recorded and 1,899 passed strict QCEC. Level 1 still has 36/36 accepted all-to-all slots and 19/36 line slots; its line score uses the 19/36 factor with an asterisk. Fully verified circuit coverage differs from seed-slot acceptance. These results characterize this specific pipeline and budget, not general SDK correctness or superiority.

## Maps and strict validation

BQSKit documents `initial_mapping[i] = j` as logical input wire i beginning on physical wire j, with the analogous meaning for the final map. The adapter uses those returned maps directly. Parsing/export preserves input declaration order, including the multi-register CDKM inputs; no guessed map or inferred measurement ordering is substituted. The output is converted without optimization, then checked for gate set, coupling, arity, and bijective maps by the shared metric/validation code.

The same QCEC decision-diagram acceptance rule applies to all three compilers. In the pinned checker, the default decision-diagram identity/trace threshold is `1e-8`; it is not loosened for BQSKit. Every recorded trial retains its returned criterion. Verification-failed outputs retain visible raw timings, counts, and depths, alongside an explicit strict-check failure label. They appear as hollow points in the plot. The output-rule check is displayed separately and is satisfied for all recorded outputs, including those with a failed strict equivalence check. Maps, QASM, and validation details remain available. Failed or missing required seed slots reduce both Quality and Speed through the pass-rate factor, with an asterisk, tinted cell, and before-penalty Details. They do not hide measured scores or raw metrics. These adjusted ranks are not claims of full verification. N/A means required raw measurements or reference values are unavailable; it does not mean QFT is unsupported. The penalty is a declared benchmark rule, not measured approximation error.

During the original level-1 adapter validation, the 6-qubit CDKM adder passed the all-to-all pipeline but failed strict verification on the line target. A compile-free conversion roundtrip passed, as did a reversed-name multi-register conversion example. Inverting the returned maps did not resolve the failure. For diagnosis only, changing QCEC's threshold from `1e-8` to `1e-6` accepted that same output. Tightening BQSKit's synthesis epsilon to `1e-16` did not make the strict check pass. This is evidence of numerical sensitivity, not a claim that the compiler has a logical routing bug or that every failure has the same cause. Neither diagnostic setting is used for published acceptance.

Regression tests exercise all four native levels on a mapped QAOA input and the original level-1 adder targets, including rejection of the numerically sensitive line result under the unchanged gate. Future approximate-error tracks must be separately defined and labeled rather than silently relaxing this pilot's checker.
