# Sealed mixed-source publication

GitHub Pages serves the committed repository root. Run `python build_site.py`
locally before committing generated HTML. No deployment workflow or server-side
build is required.

`publication.json` selects the sealed QMAP campaign through its committed
`file-map.json`. The combined raw data and standalone QMAP raw data are new files
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

The root report shows 12 configurations and explicitly distinguishes QMAP's new
420-second workers from the reused v0.4 initial 120-second outcomes and 42
600-second timeout-only retries. This is not a matched-budget rerun. Qiskit L2
is the unchanged v0.4 reference. Publication does not authorize remeasurement,
selective retry, push or release creation.
