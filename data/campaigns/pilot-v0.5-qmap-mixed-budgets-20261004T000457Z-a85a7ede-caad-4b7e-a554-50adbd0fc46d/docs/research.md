# Quantum transpiler benchmarking: landscape and scope

Research date: 2026-10-02. Facts below are based on public primary sources, not execution tests of every listed tool. Versions/capabilities must be checked again when adapters are implemented. Recommended scope is a proposal, not an existing measured result.

## Existing projects

| Project / primary source | Scope confirmed from the source | Relevance |
| --- | --- | --- |
| [Benchpress](https://github.com/Qiskit/benchpress) | Over 1,000 quantum software tests for construction, manipulation, and hardware compilation; lists Qiskit, TKET, Cirq, BQSKit, Braket, staq, Qiskit IBM transpiler, and pyqpanda3; publishes prior results in a separate branch | Closest large cross-SDK suite. Compilation settings are reusable candidates; construction benchmarks are not compile time |
| [ucc-bench](https://github.com/unitaryfoundation/ucc-bench) | CLI comparison of UCC, Qiskit, Cirq, PyTket, etc.; time, multi-qubit gates, optional ideal/noisy simulation, JSON metadata, latest comparison and historical plots | Existing continuous comparison, primarily focused on UCC rather than an independent results platform |
| [Arline paper](https://arxiv.org/abs/2202.14025), [code](https://github.com/ArlineQ/arline_benchmarks) | Automated compiler comparison including Qiskit, Tket, Cirq, Quilc, PyZX; gate count, depth, hardware cost, runtime, and compilation-stage analysis | Very close prior concept; published in 2022. Current compatibility/maintenance needs separate checking |
| [tket_benchmarking](https://github.com/Quantinuum/tket_benchmarking) | Compiler comparison scripts/circuits/data, active and historical sets | Vendor-published precedent and source of configurations |
| [qiskit-metriq](https://github.com/qiskit-community/qiskit-metriq) | Qiskit compilation across versions; depth/gate count and submissions to old Metriq tasks 25/26/27 | Compilation comparisons did exist on old Metriq. Old task URLs were not confirmed available on the new site |
| [MQT Bench](https://github.com/munich-quantum-toolkit/bench), [app](https://mqt-bench.app/) | Circuit suite with multiple abstraction levels; the older Web UI offered Qiskit/TKET, native gates, and mapping choices | Leading input-generator candidate, not primarily a continuous compiler ranking |
| [QASMBench](https://github.com/pnnl/QASMBench) | OpenQASM 2 circuit corpus across search, optimization, chemistry, arithmetic, ML, QEC, and multiple scales | Fixed input corpus; do not accidentally select already-transpiled files |

Benchpress documents substantial resource requirements for a full suite. A frozen representative subset is more practical initially. [Resource requirements](https://github.com/Qiskit/benchpress#testing-resource-requirements).

### Metriq and novelty

[Current Metriq](https://metriq.info/#view=platforms) describes an integrated workflow involving metriq-gym, metriq-data, and presentation of quantum computer benchmarks. Its FAQ describes moving from literature crowdsourcing to reproducible executable benchmarks.

Here the measured object is a **compiler version/configuration on a fixed target and budget**, not a quantum device.

The research did not confirm a separate independent platform combining continuous vendor-neutral compiler evaluation and rich conditional rankings. This is not proof that none exists. Public compiler comparisons and historical plots already exist, so “first benchmark” or “no existing comparisons” would be misleading. The value proposition is accessible, reproducible, independently operated ongoing comparison.

## Compiler candidates

Priority is a proposed scope. The current pilot measures Qiskit, pytket, and BQSKit; its explicit pipelines and limitations are in the [pilot protocol](pilot.md).

| Priority | Compiler / organization | Explicit comparison pipeline | Caveats and primary source |
| --- | --- | --- | --- |
| Initial | Qiskit / IBM and community | `generate_preset_pass_manager` with an explicit level, initially 2; level 3 a separate entry | Levels 0-3, seed, Target, layout/routing fixed. Higher levels are not presumed universally superior. [Configuration](https://docs.quantum.ibm.com/guides/defaults-and-configuration-options) |
| Initial | TKET / Quantinuum, pytket Python API | Specified Backend `default_compilation_pass` or public optimization/placement/routing/rebase sequence | Record backend/extensions. `FullPeepholeOptimise` alone is not end-to-end. Preserve implicit swaps and maps. [Compilation guide](https://docs.quantinuum.com/tket/user-guide/manual/manual_compiler.html) |
| Initial | Cirq / Google and community | Explicit transformer sequence, `RouteCQC`, `optimize_for_target_gateset`, final basis conversion | No assumed universal default transpile API. Another compiler's optimizer makes a mixed pipeline and must be disclosed. [Transformers](https://quantumai.google/cirq/transform/transformers), [routing](https://quantumai.google/cirq/transform/routing_transformer) |
| Initial | BQSKit / Berkeley Lab and collaborators | `compile` with `MachineModel`, level, precision | Declare synthesis tolerance and workers. Exact/approximate tracks differ. [Official site](https://bqskit.lbl.gov/) |
| Next | staq / softwareQ | Declared OpenQASM optimization/layout/mapping commands | Check target gate set support. [Code](https://github.com/softwareQinc/staq) |
| Next | quilc / Rigetti-origin Quil ecosystem | Quil compilation for a frozen ISA, via CLI or pyQuil | Compiler is quilc, not pyQuil itself; QASM-to-Quil conversion separate. [Code](https://github.com/rigetti/quilc) |
| Next | QASMTrans / PNNL | C++ compilation for frozen device definition | Candidate for large QASM; custom-target support needs testing. [Code](https://github.com/pnnl/qasmtrans) |
| Next | UCC / Unitary Foundation | Declared `ucc.compile` configuration | Collection/composite pipeline; current README describes selected Qiskit passes. Record dependencies and license. [Code](https://github.com/unitaryfoundation/ucc) |
| Separate track | MQT QMAP / Munich Quantum Toolkit | Heuristic mapping; exact mapper for smaller cases | Mainly mapping/routing. Exact optimality is specific to its objective and assumptions. [Mapping](https://mqt.readthedocs.io/projects/qmap/en/stable/mapping.html) |
| Separate track | PyZX / ZX-calculus community | Graph simplification, extraction, declared postprocessing | Optimizer rather than interchangeable full device compiler. Fault-tolerant candidate. [Code](https://github.com/zxcalc/pyzx) |
| Service track | IBM Qiskit Transpiler Service | Declared API options and server/model information | Separate local speed from network/queue time. [Code](https://github.com/Qiskit/qiskit-ibm-transpiler) |
| Service track | Superstaq / Infleqtion | Cirq/Qiskit client compiling for a named service target | Open client and reproducible server are different claims; check auth, fees, terms, versioning. [Code](https://github.com/Infleqtion/client-superstaq) |

Braket SDK, PennyLane, Q#/QDK, and CUDA-Q are future investigation candidates, but SDK access, hybrid execution, and comparable circuit compilation are not synonymous. Identify the precise compilation stage and common-target support before adding them. Benchpress listing a supported SDK does not imply support for every transpilation test.

## Circuit families

[MQT Bench's catalog](https://mqt.readthedocs.io/projects/bench/en/stable/benchmark_selection.html) includes QFT, Grover, QAOA, Shor, QPE, VQE ansatzes, and arithmetic. The concrete variants below are proposals, not claims that all exist unchanged in one corpus.

| Priority | Family | Fixed inputs/variants | What it probes |
| --- | --- | --- | --- |
| Initial | QFT / inverse QFT | Exact output order; approximate QFT separate | Nonlocal interactions, controlled phases, routing |
| Initial | Grover | Oracle, marked state, repetitions, ancilla state | Multi-controlled decomposition, oracle and diffusion |
| Initial | QAOA MaxCut | Fixed 3-regular and other sparse graphs, layers, nontrivial angles | Interaction-aware placement, ZZ optimization |
| Initial | VQE ansatz | RealAmplitudes/EfficientSU2, entanglement, layers, angles | Rotations and repeated entanglers |
| Initial | Hamiltonian simulation | Ising/Heisenberg, evolution time, term order, Trotter steps | Pauli structure and commutativity |
| Initial | Reversible arithmetic | Ripple-carry adder; modular adder/multiplier later | Toffoli, control, dependencies |
| Next | Shor | N, a, phase registers, modular arithmetic, workspace | Combined arithmetic and phase estimation |
| Next | QPE / amplitude estimation | Unitary, controls, precision, repetitions | Controlled/repeated computation |
| Next | Chemistry UCCSD | Molecule, basis, mapping, term order, angles | Chemistry-specific structure |
| Diagnostic | GHZ / graph states / BV | Chain/star and other structures | Basic placement and correctness; avoid padding suite scores with easy circuits |
| Diagnostic/next | Random / Quantum Volume-style | Seed, depth, gate generation/decomposition | Less structure-specific optimization; not a hardware Quantum Volume score |
| Separate track | Clifford+T arithmetic | Precision, workspace, gate representation | T-count/T-depth |
| Separate track | Syndrome/dynamic circuits | Mid-circuit measurements, reset, classical control | Dynamic semantics and scheduling |

Toy Shor N=15 examples can aid validation, but answer-specialized simplified circuits are not representative of general factoring. MQT's `shors_nine_qubit_code` is an error-correcting code, distinct from factoring `shor`. QAOA/VQE fixed-circuit compilation is not optimization convergence or application accuracy.

## Corpus selection and licensing

1. **MQT Bench:** first candidate. Prefer algorithm level before competitor-specific optimization/routing; record generator version and abstraction level. [Levels](https://mqt.readthedocs.io/projects/bench/en/stable/abstraction_levels.html).
2. **QASMBench:** complementary fixed OpenQASM 2. Check each file's provenance, license, and already-applied lowering/optimization.
3. **Benchpress:** workloads/settings for connection to published studies. Prelowered inputs are explicitly a low-level track.
4. **[Feynman](https://github.com/meamy/feynman) and [HamLib](https://portal.nersc.gov/cfs/m888/dcamps/hamlib/):** reversible/arithmetic and Hamiltonian additions.
5. **[SupermarQ](https://github.com/Infleqtion/client-superstaq/tree/main/supermarq):** application diversity/execution-quality reference, not identical to a compiler-speed suite.

OpenQASM is a format, not itself the name of a benchmark suite. QASMBench is a corpus; MQT Bench is a generator/suite.

Check both software and per-circuit/third-party data licenses. UCC's README specifies AGPLv3; do not presume every dependency has the same license. Existing published scores must not be silently reused or combined with newly measured scores.
