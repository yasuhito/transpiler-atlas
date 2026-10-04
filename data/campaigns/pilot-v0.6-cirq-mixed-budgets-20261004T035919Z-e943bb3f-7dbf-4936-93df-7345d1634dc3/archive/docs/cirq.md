# Cirq routing-only configuration

`cirq-routecqc-maponly-v1` uses `cirq-core==1.7.0` and `ply==3.11`.
It is an Atlas routing recipe, not a numerical target optimizer or a claim about
Cirq's best possible compilation. No QMAP optimization-enabled configuration is
added. The existing twelve configurations and their published records are reused.

## Frozen input and native output

The worker reads and hashes the original frozen QASM2 bytes and supplies those
bytes directly to `cirq.contrib.qasm_import.circuit_from_qasm`. It does not
re-export the Qiskit input. Logical wires follow register declaration order,
including unused wires, and are relabeled to `LineQubit(0..n-1)`. Identity gates
retain unused logical wires until native lowering. The final output contains only
`cx,rz,sx,x`, at the original physical width, without added ancillas.

The graph has all physical nodes in fixed order and undirected line or complete
edges corresponding to the shared bidirectional target. Both targets run
`LineInitialMapper` and `RouteCQC.route_circuit`, with `lookahead_radius=8`,
`tag_inserted_swaps=True`, and `TransformerContext(deep=False,tags_to_ignore=())`.
Initial logical-to-physical mapping is I; the final mapping is S composed with I,
where S maps initial physical positions to final positions. Every wire must appear
in both full bijections. Missing entries are never filled with identity.

`QasmOutput` uses all physical qubits, version 2.0 and precision 17. Qiskit imports
with `LEGACY_CUSTOM_INSTRUCTIONS` and runs only
`BasisTranslator(SessionEquivalenceLibrary,['cx','rz','sx','x'])`. There is no
Qiskit layout, routing, cancellation or preset optimization pass. Numerical Cirq
target optimizers and unknown unitary/KAK export fallbacks are rejected.

Frozen QASM2 has zero input scalar phase. For the programmatic circuit interface,
a known input scalar is supplied separately, restored once before lowering, and
translator-created phase is retained. Unknown phase operations are rejected.
Every trial stores the native scalar alongside QASM2, since QASM2 omits scalar
phase. Validation uses the native circuit, not a scalar-losing artifact re-import.

## Repetition, timing and strict checking

`seed_supported=False`. RouteCQC has no mapper seed argument. Slots 7/19/43 are
independent executions of the same unseeded recipe, as with QMAP v1. Each worker
performs three real compilations and three checks; matching outputs are not copied
to fill slots. Nine outputs per case/target are compared by QASM bytes, native
phase and initial/final maps. Agreement is an observation, not a cross-platform
or arbitrary-input determinism guarantee.

Imports, input parsing/relabeling and idle preparation are outside the compile
timer. Graph, mapper, router and translator construction, routing, QASM bridge and
native lowering are inside. Metrics, map checks, final export and QCEC are outside.
The external 420-second worker budget includes imports, parsing, all three trials,
all checks and export. It is not a per-compilation allowance. Workers run
sequentially with affinity and thread settings at one.

QCEC uses the unchanged shared settings: simulation and ZX disabled, one thread,
no parallel checking, a 20-second request and the default 1e-8 threshold. Only
`equivalent` and `equivalent_up_to_global_phase` pass. Failed or unfinished checks
are not approximate acceptance. The outer worker kills and reaps its process
group on timeout. Numerical acceptance is not an unconditional mathematical proof.

## One cohort, three sources

```sh
uv sync --frozen
uv run --frozen python atlas.py campaign --into /tmp/ta-cirq/campaigns --prepare-only
# A prepared workspace may be measured once with the same interpreter:
/path/to/cirq-checkout/.venv/bin/python /path/to/workspace/atlas.py run
/path/to/cirq-checkout/.venv/bin/python /path/to/workspace/build_site.py
```

Only this configuration is scheduled: 12 frozen cases, two targets and three
slots, giving 72 workers and up to 216 output checks. Do not run pytest or another
BQSKit job during measurement. `RUN_STARTED` prevents reruns. Resume, overwrite
and selective retries are refused; an interrupted workspace stays incomplete.

The standalone raw file is `data/cirq-results.json`. The combined suite
`pilot-v0.6-cirq-mixed-budgets` contains 936 records and 13 configurations: unchanged
v0.4 792, unchanged QMAP v1 72, and new Cirq 72. The authenticated old publication
closure is copied as data under `history/pilot-v0.5`; archived Python is never
executed. Artifact aliases retain unchanged record paths and bytes.

The sources retain separate environments and windows. v0.4 has 750 initial
120-second outcomes and 42 timeout-only retries at 600 seconds. QMAP v1 and Cirq
have separate 420-second cohorts. There is no universal combined budget and no
matched-budget claim. Qiskit L2, score equations and acceptance rules are unchanged.
Local site generation does not switch the repository publication selector or
authorize a push. See [publication](publication.md) for future packaging.
