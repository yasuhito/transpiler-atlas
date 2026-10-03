# Corpus inputs: Pilot v0.2

## Source and license

The pilot imports six original, non-`_transpiled` files from [PNNL QASMBench](https://github.com/pnnl/QASMBench/tree/357b942396d5c2b7cbc1c229c585a6ef5ccaebac/small), fixed at revision `357b942396d5c2b7cbc1c229c585a6ef5ccaebac`. These complement the six Atlas-generated cases, so every one of the six families has at least one existing-corpus input. This is a mixed small pilot, not the full QASMBench suite.

The [upstream license](https://github.com/pnnl/QASMBench/blob/357b942396d5c2b7cbc1c229c585a6ef5ccaebac/LICENSE) permits use, modification, and redistribution subject to retaining its copyright, conditions, and disclaimers. It is preserved verbatim at [corpora/qasmbench/LICENSE](../corpora/qasmbench/LICENSE). Original source files are retained without byte changes in `corpora/qasmbench/`. This license covers the imported material, not all Atlas code; Atlas still has no chosen project license.

| Family | Upstream file under `small/` | Width |
| --- | --- | --- |
| QFT | `qft_n4/qft_n4.qasm` | 4 |
| QAOA | `qaoa_n3/qaoa_n3.qasm` | 3 |
| Adder | `adder_n4/adder_n4.qasm` | 4 |
| Grover | `grover_n2/grover_n2.qasm` | 2 |
| VQE | `vqe_n4/vqe_n4.qasm` | 4 |
| Hamiltonian | `ising_n10/ising_n10.qasm` | 10 |

Per-file immutable upstream links and SHA-256 hashes are in the [input manifest](../data/manifest.json) and the per-circuit view's Input details. Names and family assignments follow the supplied circuit identities; no inference of physical algorithm success is made.

## Transformations and validation boundary

`atlas.py:corpus_unitary` parses OpenQASM 2 with Qiskit's legacy standard-gate extensions, needed for the supplied `sx` instructions. It removes barriers, measurements that are terminal on their individual quantum wires, and classical registers. It retains all state preparation and fixed-angle gates. It rejects reset, classical-dependent operations, and any operation on a wire after that wire was measured. QAOA has readout interleaved with later gates on other wires, which is allowed because those gates do not touch the measured wires.

The retained unitary is lowered by the same Qiskit level-0 rule as the original pilot, with no optimization or mapping. Both compilers receive identical lowered QASM. Source bytes, source revision, removal counts, and lowered bytes are independently identifiable. Offline reproduction needs no corpus download or corpus package dependency.

QCEC checks compiled outputs against the **transformed unitary input**, not the original measurement-bearing program. This benchmark does not compare classical-output distributions, variational training, VQE energies, or hardware execution. Input preparation is retained even though full-unitary equivalence is checked rather than equivalence for one prepared state. The QASMBench QFT is not the same variant as the original Atlas QFT with reversal; these are separate case IDs, not duplicate workloads.

## Selection limits

Only six small, fixed-parameter inputs were selected to exercise the existing pipelines and verifier. Grover is only two qubits; VQE and Hamiltonian have one instance each. The selection is not statistically representative of a corpus or of algorithm families. Scores now weight six families equally, so they must not be compared directly with the three-family v0.1 aggregate.

MQT Bench was considered in the earlier [landscape research](research.md), but no MQT Bench material or dependency is added in this increment. One fixed corpus with original-file provenance is a smaller, directly reproducible step. More widths, parameter sets, and compiler adapters remain future work.
