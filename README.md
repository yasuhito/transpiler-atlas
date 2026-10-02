# Transpiler Atlas

An English-language, table-first viewer for measured quantum transpiler benchmark results. Current data is a small **Qiskit/pytket pilot**, not a formal ranking or a general claim about SDK superiority.

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

The UI was revised after inspecting SWE-bench, DeepSWE, LiveBench, and Artificial Analysis. [Design review](docs/design.md) / [HTML](docs/design.html).

## Reproduce and test

```bash
# Linux, Python 3.12; dependencies pinned in uv.lock
uv sync --frozen
uv run python atlas.py run
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

6 circuits × 2 topologies × 2 compilers × 3 seed slots, with three repetitions each: 72 entries and 216 output checks. All recorded outputs passed QCEC's decision-diagram equivalence check.

- Families: QFT, QAOA, full ripple-carry adder.
- Targets: input-width all-to-all and line, bidirectional CX.
- Native basis: `rz,sx,x,cx`.
- Shared host, single-core affinity; not an exclusive controlled machine.
- Frozen low-level OpenQASM 2 inputs generated/lowered by Qiskit level 0; not a high-level-neutral input track.
- pytket does not use the seed in this pipeline. Its seed slots represent repeated measurements.
- Quality and Speed use the same measured Qiskit reference = 100. Missing required trials yield N/A.

See [pilot protocol](docs/pilot.md) / [HTML](docs/pilot.html) for precision, maps, timing boundaries, and limitations.

## Files

- `atlas.py`: input generation, explicit pipelines, measurement, validation.
- `build_site.py`: static report and documentation generator.
- `web/report.html`, `web/style.css`, `web/app.js`: editable site sources.
- [Raw results](data/results.json), [input manifest](data/manifest.json), `data/inputs/`, `data/outputs/`.
- [Landscape and candidates](docs/research.md) / [HTML](docs/research.html).
- [Formal methodology proposal](docs/methodology.md) / [HTML](docs/methodology.html).

`index.html`, `docs/*.html`, and `data/*` are generated artifacts. Do not hand-edit them.

## Planned scope

Add Cirq/BQSKit, Grover/VQE/Hamiltonian circuits, and fixed grid/large targets after validating adapters. Shor, specialized mapping, fault-tolerant, cloud, and dynamic-circuit tracks remain separate proposals. No unmeasured compilers appear as fabricated leaderboard entries.

Compiler benchmarking already exists in Benchpress, ucc-bench, Arline, and others. This project aims at reproducible conditional results presentation, not a claim to be the first comparison.

Published under `yasuhito/transpiler-atlas`. Domain and trademark availability have not been assessed, and a project license has not yet been chosen. No paid API usage or hardware jobs have been performed.
