# BQSKit adapter: Pilot v0.3

## Explicit pipeline

BQSKit 1.2.1 and bqskitrs 0.4.1 are locked alongside the unchanged v0.2 compiler dependencies. All three compilers are remeasured in one shuffled run on the same 12 frozen inputs; old timings are not merged into the new report.

The adapter uses BQSKit's public standard `compile` workflow, not a custom optimization sequence:

| Setting | Value |
| --- | --- |
| Input | The same lowered OpenQASM 2 circuit used by Qiskit and pytket |
| Target width | Input width, no workspace |
| MachineModel gates | `RZGate`, `SXGate`, `XGate`, `CNOTGate` |
| Coupling graph | Undirected line or complete graph, corresponding to the shared bidirectional CX target |
| Optimization level | 1 |
| Maximum synthesis size | 2 qubits |
| Synthesis epsilon | `1e-12` |
| Seed | 7, 19, 43, passed to `compile` |
| Mapping | `with_mapping=True` |
| Local runtime | 1 worker, 1 BLAS thread |
| Internal error threshold | `None`; the shared external QCEC check decides acceptance |

Level numbers are not equivalent optimization budgets across SDKs. Level 1 and two-qubit blocks provide a bounded first BQSKit pipeline, not a survey of its quality/time frontier. This uses numerical synthesis and must not be described as an exact symbolic compiler or as guaranteeing `1e-12` whole-circuit error.

Primary sources: the [versioned standard compile implementation and parameter documentation](https://github.com/BQSKit/bqskit/blob/1.2.1/bqskit/compiler/compile.py), [Compiler runtime documentation](https://bqskit.readthedocs.io/en/latest/source/autogen/bqskit.compiler.Compiler.html), [MachineModel documentation](https://bqskit.readthedocs.io/en/latest/source/autogen/bqskit.compiler.MachineModel.html), and [versioned Qiskit conversion adapter](https://github.com/BQSKit/bqskit/blob/1.2.1/bqskit/ext/qiskit/translate.py).

## Timing boundary and process lifecycle

Input conversion and local runtime startup/shutdown are outside the compile timer. A fresh local runtime is created for every repetition. The measured interval includes MachineModel construction, standard workflow construction, submission, execution, and result retrieval. Output conversion, export, metrics, and QCEC are outside the timer.

BQSKit's local runtime communicates between processes; this is not a remote cluster, paid service, or hardware job. The 120-second worker budget includes runtime startup/shutdown, all three repetitions, and validation. If a worker times out, the runner terminates its entire process group, including local runtime descendants. Runtime initialization cost is not reflected in the displayed compile time; the numbers do not estimate application end-to-end latency.

## Recorded completion

| Compiler / target | Passed entries | Verification-failed entries | Timeouts / errors |
| --- | --- | --- | --- |
| Qiskit, both targets | 72 | 0 | 0 |
| pytket, both targets | 72 | 0 | 0 |
| BQSKit, all-to-all | 36 | 0 | 0 |
| BQSKit, line | 19 | 17 | 0 |

All 648 output trials are retained; 597 passed the strict checker. BQSKit has all required seed slots accepted for 12/12 all-to-all cases, but only 4/12 line cases. The line aggregate is therefore N/A. These are acceptance results for this specific numerical pipeline, not a general SDK correctness or superiority ranking.

## Maps and strict validation

BQSKit documents `initial_mapping[i] = j` as logical input wire i beginning on physical wire j, with the analogous meaning for the final map. The adapter uses those returned maps directly. Parsing/export preserves input declaration order, including the multi-register CDKM inputs; no guessed map or inferred measurement ordering is substituted. The output is converted without optimization, then checked for gate set, coupling, arity, and bijective maps by the shared metric/validation code.

The same QCEC decision-diagram acceptance rule applies to all three compilers. In the pinned checker, the default decision-diagram identity/trace threshold is `1e-8`; it is not loosened for BQSKit. Every recorded trial retains its returned criterion. Verification failures are shown as unverified with N/A metrics/scores, and do not contribute to the plot. Raw timings, metrics, maps, QASM, and validation details remain available. Any failed required seed slot makes that selected aggregate N/A.

During adapter validation, the 6-qubit CDKM adder passed the all-to-all pipeline but failed strict verification on the line target. A compile-free conversion roundtrip passed, as did a reversed-name multi-register conversion example. Inverting the returned maps did not resolve the failure. For diagnosis only, changing QCEC's threshold from `1e-8` to `1e-6` accepted that same output. Tightening BQSKit's synthesis epsilon to `1e-16` did not make the strict check pass. This is evidence of numerical sensitivity, not a claim that the compiler has a logical routing bug or that every failure has the same cause. Neither diagnostic setting is used for published acceptance.

Regression tests exercise the actual BQSKit pipeline with a mapped QAOA input and both adder targets, including rejection of the numerically sensitive line result under the unchanged gate. Future approximate-error tracks must be separately defined and labeled rather than silently relaxing this pilot's checker.
