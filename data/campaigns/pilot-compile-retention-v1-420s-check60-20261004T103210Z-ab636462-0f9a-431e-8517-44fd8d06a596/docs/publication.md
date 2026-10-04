# Sealed mixed-source publication

## Current Cirq v2 publication

The current selector serves 936 records, 13 configurations and three sources.
The historical QMAP-only cohort below had 12 configurations; that is not the
current root report's configuration count. The root `data/results.json` still
contains the original v0.4 bytes.

The maintained reader accepts the existing QMAP v1 seal using its own sealed
12-configuration specification, even with 13 configurations in the execution
registry. It never imports or executes archived Python. Unknown spec or seal
versions are rejected. Results `schema_version=2` is independent of the new
`spec_format_version=2` and `seal_format_version=2` (`kind=cirq-mixed`).

A new Cirq workspace preserves the authenticated old publication closure byte for
byte under `history/pilot-v0.5` and reuses its 864 records without additions to
old rows or path rewriting. `data/cirq-results.json` contains only the new 72
Cirq entries. `data/results.json` combines 936 entries across three sources.
Source ownership determines budget labels: v0.4 initial120/retry600, old QMAP420,
new Cirq420, with distinct windows. No universal budget is implied.

The completion marker hashes a snapshot containing both the old closure and new
raw, source, input and artifact files. The builder verifies hashes, recomposes
three sources and checks artifact links before writing derived pages. Old seals
are verified under the old protocol, not the live registry. Reruns and partial
recovery are refused. Missing files, changed hashes and unsafe paths fail closed.

The approved Cirq publication added its campaign archive, standalone and combined
raw, source-scoped FileMap and 216 Cirq artifacts under their original new-config
paths. Identical historical bytes are referenced in the map instead of duplicated.
It selected the Cirq mixed-source campaign and rebuilt the report/notes, without
changing old raw records, artifacts or seals. That publication does not authorize
further measurement, selector changes, pushes or publication.

## Preserved QMAP v1 publication

GitHub Pages serves the committed repository root. Run `python build_site.py`
locally before committing generated HTML. No deployment workflow or server-side
build is required.

The QMAP v1 publication selected its sealed campaign through a committed
`file-map.json`. The current selector has since advanced to the Cirq v2 campaign;
this section describes the preserved QMAP archive. The combined raw data and standalone QMAP raw data are new files
under `data/campaigns/<campaign_id>/`. The original completion marker, snapshot,
campaign specification, input manifest, run log and frozen source files retain
their original bytes. These are an archive, not code to execute in place.

The file map maps every logical sealed path to a repository-relative physical
file. Existing v0.4 results, attempts, inputs, corpus files and output artifacts
are referenced rather than duplicated. Every mapped file must match the original
snapshot SHA-256. The completion marker authenticates the unchanged snapshot.
The validator also recomposes the dataset and checks campaign identity, source
provenance and artifact link resolution. Missing, modified or escaping paths stop
the build. Original raw provenance paths remain logical campaign paths; consult
the file map to locate their published physical files.

The 216 new QMAP QASM files occupy their original record paths in `data/outputs/`.
No old artifact is replaced. The root `data/results.json` remains v0.4, and the
footer provides a separate v0.4 raw link. Data, Raw JSON and the no-JavaScript
fallback point to the combined raw file. The generated configuration-note sidecar
is stored next to that combined file; the old sidecar is retained.

The historical QMAP report showed 12 configurations and distinguished QMAP's new
420-second workers from the reused v0.4 initial 120-second outcomes and 42
600-second timeout-only retries. This is not a matched-budget rerun. Qiskit L2
is the unchanged v0.4 reference. Publication does not authorize remeasurement,
selective retry, push or release creation.

## Standalone compile-retention v3, not yet published

The new `kind=compile-retention` reader handles spec, result schema and seal v3
as a standalone dataset, never a fourth source merged into the historical rows.
An explicit precommitted ordered schedule and new execution identities separate
420/60/20-second retained-compilation diagnostics from the old timeout records.
QCEC remains 3.10.1; recipes and display configuration IDs are not new evidence
that the execution identity is unchanged.

Every scheduled job must have terminal facts. The validator re-derives QPY/native
output rules, phase/maps, hashes, raw metrics, medians, classification and rollup
without running QCEC. QASM, actual QPY, compile commit manifests, check replies,
process cleanup/budget evidence, source/lock/input/license provenance and all
forensic logs/orphans are sealed. Incomplete verification can be sealed; a
missing job, cancelled schedule, corrupt bundle or altered file cannot. The
create-only snapshot is followed last by `MEASUREMENT_COMPLETE`. A FileMap must
cover exactly the snapshot files plus snapshot and marker, and artifact links
must resolve to the same sealed physical bytes.

A later publication needs separate approval and would add a standalone campaign
archive, raw result, exact FileMap, QASM/QPY/manifests/logs and a dedicated report
or standalone selector. It must not backfill the 18 historical identities, replace
old output files, recompute `qcec-adjusted-v1`, or rewrite old campaigns, releases,
attempts or seals. The partial-raw viewer uses `qcec-adjusted-partial-v2` only for
this protocol. No reference rows are in the timeout diagnostic, so Quality/Speed
are N/A for missing reference values, not merely because checks are unfinished.
Local previews belong outside the checkout and are not committed or published.
See [standalone protocol](retention.md).
