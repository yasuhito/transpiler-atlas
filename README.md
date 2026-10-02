# Transpiler Atlas

An English-language, table-first viewer for measured quantum transpiler benchmark results. Current data is a small **Qiskit/pytket/BQSKit pilot**, not a formal ranking or a general claim about SDK superiority.

## Open the site

**Website:** https://yasuhito.github.io/transpiler-atlas/

**Source:** https://github.com/yasuhito/transpiler-atlas

GitHub Pages serves the committed static site from `main` at the repository root. `.nojekyll` disables Jekyll processing. To update the report, regenerate it locally and commit the generated artifacts along with their sources; deployment does not rerun quantum benchmarks.

Open [`index.html`](index.html) directly in a browser. No server is needed. Data is embedded; local CSS/JavaScript, generated documentation, and QASM artifacts are linked from the report.

Views:

- **Leaderboard:** family-balanced Quality/Speed scores, raw metric medians, family breakdowns, completion.
- **Per circuit:** individual measurements, validation, timing ranges, output QASM.
- **Matrix:** circuit/compiler comparisons for a selected metric.
- **Trade-off:** compile time against 2Q count or depth.

Shared filters select topology, family, qubit width, compiler, and metric. Column controls, sortable headers, and URL-fragment permalinks preserve an analysis-oriented interface. There is no promotional hero or catchphrase. Linked documentation is also English.

The header's Theme control selects **Light**, **Dark**, or **System** (the default). The preference is saved when browser storage is available and shared with linked documentation. System follows live OS/browser color-scheme changes. Theme assets work offline.

## Reproduce and test

```bash
# Linux, Python 3.12; dependencies pinned in uv.lock
uv sync --frozen
uv run python atlas.py run --overwrite
uv run python build_site.py

uv run pytest -q
uv run ruff check .
uv run ruff format --check .
npm ci
npm test  # /usr/bin/chromium, or set CHROMIUM_PATH
```

To serve locally instead of using file URLs:

```bash
python -m http.server 8765 --directory . --bind 127.0.0.1
```

Open `http://localhost:8765/`. Deploy the site tree together with `web/`, `docs/`, and `data/`.

## Implemented pilot

Pilot v0.3: 12 circuits × 2 topologies × 3 compilers × 3 seed slots, with three repetitions each: 216 scheduled entries and up to 648 output checks. All 216 entries completed; 597/648 outputs passed strict validation. BQSKit had 17 verification-failed line-target entries; all 36 of its all-to-all entries passed. BQSKit outputs that fail the unchanged strict QCEC check remain unverified and receive N/A, rather than having the verifier relaxed.

- Six families: QFT, QAOA, Adder, Grover, VQE, Hamiltonian. Six original generated circuits plus six fixed QASMBench imports.
- [Corpus sources and license review](docs/corpora.md); original QASM, license, parameters, and source/input hashes are retained. Expand Input details in the per-circuit view.
- [Pilot v0.1](releases/pilot-v0.1/index.html) and [Pilot v0.2](releases/pilot-v0.2/index.html) retain their original reports, measurements, artifacts, sources, and dependency locks.
- [BQSKit adapter](docs/bqskit.md): standard level 1, two-qubit blocks, synthesis epsilon `1e-12`, seeded, one local worker/BLAS thread, returned wire maps, unchanged QCEC acceptance.
- Targets: input-width all-to-all and line, bidirectional CX.
- Native basis: `rz,sx,x,cx`.
- Shared host, single-core affinity; not an exclusive controlled machine.
- Frozen low-level OpenQASM 2 inputs lowered by Qiskit level 0; not a high-level-neutral input track. Corpus barriers and per-wire terminal readout are removed; preparation gates remain.
- pytket does not use the seed in this pipeline. Its seed slots represent repeated measurements.
- Quality and Speed use the same measured Qiskit reference = 100. Missing required trials yield N/A.

See [pilot protocol](docs/pilot.md) / [HTML](docs/pilot.html) for precision, maps, timing boundaries, and limitations.

## Files

- `atlas.py`: input generation, explicit pipelines, measurement, validation.
- `build_site.py`: static report and documentation generator.
- `web/report.html`, `web/style.css`, `web/app.js`: editable site sources.
- `web/theme.css`, `web/theme.js`: shared theme tokens, preference persistence, and system-theme handling.
- [Raw results](data/results.json), [input manifest](data/manifest.json), `data/inputs/`, `data/outputs/`.
- [Landscape and candidates](docs/research.md) / [HTML](docs/research.html).
- [Formal methodology proposal](docs/methodology.md) / [HTML](docs/methodology.html).

`index.html`, `docs/*.html`, and `data/*` are generated artifacts. Do not hand-edit them. `corpora/` contains unmodified licensed upstream inputs. `releases/` contains immutable published snapshots; do not regenerate them with current sources. v0.2 includes its linked v0.1 snapshot to preserve historical relative links.

`atlas.py run` refuses to replace current-suite measurements without `--overwrite`, and refuses a suite change without a matching archived results file. Preserve any measurements you need before explicitly overwriting them. Tests generate their inputs in temporary directories.

## Planned scope

Add Cirq after choosing an explicit pipeline. BQSKit's higher optimization levels and approximate-error tracks require separate declared configurations. Broaden widths, parameter sets, and fixed grid/large targets after validating adapters. Shor, specialized mapping, fault-tolerant, cloud, and dynamic-circuit tracks remain separate proposals. No unmeasured compilers appear as fabricated leaderboard entries.

Compiler benchmarking already exists in Benchpress, ucc-bench, Arline, and others. This project aims at reproducible conditional results presentation, not a claim to be the first comparison.

Published under `yasuhito/transpiler-atlas`. Domain and trademark availability have not been assessed, and a project license has not yet been chosen. No paid API usage or hardware jobs have been performed.
