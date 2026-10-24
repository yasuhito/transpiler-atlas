# Results UI: benchmark site references

Reviewed on 2026-10-02 using the live sites in Chromium, screenshots at 1440 × 1000, and their rendered text. These are references for information architecture and interaction, not sources for quantum benchmark measurements. No logos, assets, or source code were copied.

## Sites reviewed

| Primary source | Observed interface | Applied here |
| --- | --- | --- |
| [SWE-bench](https://www.swebench.com/) | Benchmark subset tabs, configuration filters, dense sortable leaderboard, evaluation metadata and links to trajectories | A table-first default view, selected metric ordering, configuration labels, artifact links |
| [DeepSWE](https://deepswe.datacurve.ai/) | Compact navigation, release and effort selectors, switchable cost/token/step axes, score-versus-cost plot, adjacent numeric results | Separate comparison views and a switchable quality/time plot. No introduction or promotional section in this dashboard |
| [LiveBench](https://livebench.ai/) | Release selection, category filters, column controls, per-category scores, table cell shading, subtask drill-down | Family buttons, detailed-column toggle, family breakdowns, per-circuit matrix shading |
| [Artificial Analysis](https://artificialanalysis.ai/leaderboards/models) | Multiple metric columns, model filters, column expansion, quality/price/speed separation | Keep quality and speed separate; show raw metrics beside normalized scores |

All four live pages loaded during the review. LiveBench's text extraction service did not return readable content, but its rendered browser page was inspected successfully. The current sites also have introductions or marketing sections; those are intentionally not adopted because this product is a results viewer.

## Layout decisions

- English-only UI and linked HTML documentation.
- Small top navigation, neutral white background, light table rules, restrained color.
- No hero, catchphrase, large statistics cards, per-compiler score cards, roadmap, signup, or narrative sections.
- Results begin immediately after a short dataset label and a one-line pilot caveat.
- Four views: compiler leaderboard, per-circuit results, circuit/compiler matrix, and trade-off plot.
- Shared filters: topology, circuit family, width, compiler, metric.
- Detailed columns can be hidden. Numeric headers sort by the corresponding metric.
- State is represented in the URL fragment, including for local file use. A permalink preserves the selection.
- Protocol details remain collapsed; longer methodology and source material live on separate pages.

## Data integrity and accessibility

- Only the existing measured pilot is shown. No placeholder compilers, invented runs, or synthetic rankings.
- There is only one measured release, so there is no misleading release/history control.
- Raw metric columns and normalized score columns are identified separately.
- Missing required trials produce N/A; an incomplete suite is not averaged over surviving cases.
- Matrix shading means best available value in that row, not statistical significance.
- Compiler filtering does not change the Qiskit baseline used to calculate scores.
- Tab controls support arrow keys, Home, and End. Filters are labeled; results announce changes; sort direction is exposed through `aria-sort`.
- Tables scroll within their container on narrow screens. A plot has an accessible textual description and the same values are available in the per-circuit view.
