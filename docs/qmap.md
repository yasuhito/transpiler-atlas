# MQT QMAP mapping-only configuration

## Identity and scope

`qmap-sc-heuristic-maponly-v1` is the first QMAP configuration. It uses PyPI `mqt.qmap==3.10.0`, directly calls `mqt.qmap.sc.map_`, selects heuristic mapping and dynamic placement, and disables QMAP pre/post optimizations. It is not the Qiskit wrapper, a transpiler stage plugin, or a Qiskit optimization hybrid. Exact search and optimized recipes require different configuration IDs.

The immutable `qmap_adapter.SETTINGS` descriptor explicitly defines all 30 public Configuration properties. The runtime materializes every field, checks read-back values, and records the full descriptor in the registry and `protocol.qmap_pipeline`. QMAP's own configuration JSON omits fields and is not the sole recipe provenance.

| Property | Value |
|---|---|
| method / heuristic | heuristic / gate_count_max_distance |
| initial_layout / layering | dynamic / individual_gates |
| iterative_bidirectional_routing / passes | false / 0 |
| automatic_layer_splits / node_limit | true / 5000 |
| early_termination / limit | none / 0 |
| lookahead_heuristic / lookaheads | gate_count_max_distance / 15 |
| first_lookahead_factor / lookahead_factor | 0.75 / 0.5 |
| pre_mapping_optimizations / post_mapping_optimizations | false / false |
| add_measurements_to_mapped_circuit / add_barriers_between_layers | false / false |
| use_subsets / subgraph | false / empty set |
| encoding / commander_grouping | commander / fixed3 |
| swap_reduction / swap_limit / enable_limits | coupling_limit / 0 / true |
| timeout | 3600000 ms, an exact-search setting, not the worker wall cap |
| verbose / debug / include_wcnf / data_logging_path | false / false / false / empty string |

## Input, mapping, phase, and native lowering

The shared frozen input basis is `h,x,rx,ry,rz,cx`. Physical width equals the entire input width. `Architecture(n,set(edges_for(n,target)))` uses bidirectional line edges or all directed pairs. No workspace or ancillas are added, and all-to-all still calls the mapper.

Raw `initial_layout` and `output_permutation` map physical to logical indices. Each is independently inverted to Atlas logical-to-physical maps. The adapter validates bijections and never uses the wrapper's `final_index_layout()`.

Additional edge-case testing found two pinned-version behaviors not covered by the initial smoke test:

- QMAP compacts idle logical wires and exports only active output entries. The adapter makes active-first input relabeling explicit without adding gates or reducing device width. It restores original declaration order, tracks idle states through the emitted routing SWAPs, and checks every active raw output entry against that tracking. It does not fill a missing map with identity. Full raw maps remain independently inverted. Original SWAPs are not accepted in the common low-level input track, so routing SWAP tracking is unambiguous.
- QMAP drops an input scalar global phase. The adapter maps a phase-zero copy and restores the saved scalar plus mapped phase exactly once. `mqt_to_qiskit(mapped,set_layout=False)` is followed only by `BasisTranslator(SessionEquivalenceLibrary,['cx','rz','sx','x'])`. Basis lowering can introduce phase, which is not overwritten afterward. Each trial stores final `global_phase` alongside its QASM2 artifact, since QASM2 omits it.

SDK import and input conversion/relabeling are outside the compile timer. Architecture, fresh Configuration, pass manager construction, mapping, required MQT-to-Qiskit conversion, phase restoration, and native lowering are inside. Map/width/arity/coupling validation, metrics, QCEC, and export are outside. No Qiskit optimization, layout, routing, approximation, or cancellation pass is added.

## Seeds and strict acceptance

`seed_supported=False`. QMAP's public SC API has no seed option. Slots 7/19/43 are independent repetitions of the unseeded pipeline, not mapper RNG seeds. Every slot still runs three compilations; outputs are never replicated to fill slots. Small-case reproducibility does not guarantee determinism on every input or platform.

The unchanged shared QCEC checker disables simulation and ZX, uses one thread without parallel checking, requests 20 seconds, and keeps the default `1e-8` trace/identity threshold. Only `equivalent` and `equivalent_up_to_global_phase` are accepted. Approximate acceptance and `probably_equivalent` are not used. Diagnostic tests may isolate QCEC with an external 60-second kill; a killed check is incomplete, not a returned non-equivalence verdict.

QMAP internal timeout is an error with `error_kind=qmap_internal_timeout`, checked before conversion. The external worker deadline is a timeout. Invalid maps, basis, coupling, or width are errors. Completed outputs with non-accepted QCEC are `verification_failed` and retain their measurements. The scoring and acceptance rules are unchanged.

## New campaign, not a historical rewrite

The next suite is `pilot-v0.5-qmap-420s`: twelve frozen inputs, twelve configurations, two targets and three seed slots, totaling **864 entries**, with up to 2,592 output checks. All configurations must be measured anew. The single execution definition is `atlas.WORKER_TIMEOUT_SECONDS`; protocol, every record, campaign spec and snapshot derive the same **420-second full-worker budget**. It includes imports, parsing, three compilations/checks, export and runtime startup/shutdown, not 420 seconds per compilation.

Run from an approved source checkout with Python 3.12:

```sh
uv sync --frozen
# Optional preparation only: creates a new fixed workspace without measuring.
uv run --frozen python atlas.py campaign --into /tmp/ta-qmap/campaigns --prepare-only
# Actual full measurement, only after separate execution approval:
uv run --frozen python atlas.py campaign --into /tmp/ta-qmap/campaigns
```

`--into` is a parent directory, not an existing results file. Each invocation reserves a new UTC/UUID leaf with source/assets, frozen inputs, licenses, source commit and byte hashes, dependencies and budget. The actual worker runs the copied `atlas.py` with that workspace as cwd. No input regeneration or old-result reuse occurs. Historical documentation links use a separate byte-identical `history/pilot-v0.4/` namespace and never contribute entries or scores.

A prepared workspace can be measured once with the same venv interpreter:

```sh
/path/to/source/.venv/bin/python /path/to/new-workspace/atlas.py run
```

`RUN_STARTED` prevents rerun. Resume, retry and overwrite are refused. An interrupted workspace remains incomplete; create a different ID and measure the whole matrix again. Parent-owned JSONL retains completed outcomes. Workers exclusively create their own QASM artifacts. The parent validates identity, budget and artifact hashes, publishes new results without replacement, hashes the measurement snapshot, then creates `MEASUREMENT_COMPLETE` last.

Build the site only from a completed workspace:

```sh
/path/to/source/.venv/bin/python /path/to/new-workspace/build_site.py
```

The builder verifies the measurement seal, raw/spec/manifest identity and hashes, and same-workspace links before publishing derived HTML and the display-only sidecar. Rebuilding derived files is allowed; changing measurements is not. The raw download, embedded data and sidecar refer to the same campaign. No fake new-suite results are generated for the current historical site.

The old `data/results.json`, `data/attempts`, releases and their 120/600-second provenance remain unchanged. Quality and Speed remain `qcec-adjusted-v1` with the same run's Qiskit L2 reference, nested medians, coverage and pass-rate rules. Mapping-only and stock preset optimization are different recipes, not equal SDK effort.
