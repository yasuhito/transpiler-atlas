# Benchmark methodology proposal

This document proposes a future formal suite. Numerical budgets and weights are design choices, not measured universal constants. The implemented pilot has a narrower scope; see the [pilot protocol](pilot.md).

## Comparison unit

An entry is a specific **compiler + version + dependencies + pipeline/configuration + target + resource profile + input track + validation tier**. SDK names alone are insufficient.

The initial formal track measures static circuit end-to-end compilation: optimization, decomposition, placement, routing, and final native-gate lowering. No quantum hardware is required to measure compilation or inspect outputs. Full simulation and equivalence checking can be much harder than compilation, especially at large widths.

Separate future tracks:

1. Optimization-only, with a common output gate set and no routing.
2. Routing-only, with common predecomposed inputs and fixed initial placement; allowed postprocessing is declared.
3. Fault-tolerant compilation, with T-count/T-depth, precision, and workspace rules.
4. Cloud services, with network/queue time, server version information, and pricing kept separate from local CPU measurements.
5. Dynamic circuits, with measurement/reset/classical-control semantics checked independently.
6. Hardware execution, with controlled calibration, shots, mitigation, and scheduling. Hardware success probability is not inferred directly from gate counts.

## Inputs

- Use identical circuit content and hashes across compilers, not separately generated versions of the same algorithm.
- Separate high-level structured inputs from common low-level gate sequences. A circuit optimized by one competitor is not a neutral baseline input.
- Start with a static OpenQASM 2 subset and concrete nontrivial angles. General OpenQASM 3 or SDK-specific boxes are not assumed interoperable.
- Adapters perform representation conversion only. Required decomposition, structural information loss, and conversion cost are disclosed. No optimizer is hidden in an adapter.
- Record generator/source version, source commit, parameters, seeds, total width including ancillas, provenance, and licenses.
- Symbolic-parameter tracks are separate. QAOA/VQE compilation does not measure a classical optimizer's convergence or the quality of its solution.

## Targets

Proposed suite v1 synthetic targets:

| Target | Physical width | Coupling | Gate set |
| --- | --- | --- | --- |
| all-to-all-32-cx | 32 | Fully connected, bidirectional CX | rz, sx, x, cx |
| line-32-cx | 32 | Path, bidirectional CX | rz, sx, x, cx |
| grid-4x8-cx | 32 | 4 × 8 grid, bidirectional CX | rz, sx, x, cx |

These target definitions are Atlas design choices, not imported corpus conditions, a named hardware specification, or a claim of conformance to an existing benchmark standard. The current pilot uses input-width variants rather than these proposed 32-qubit targets.

Produce separate tables/scores per target. Fully connected targets emphasize optimization; lines emphasize routing; grids provide another interaction structure. Do not combine different physical constraints into an unexplained single ranking.

Persist physical IDs, edges, directionality, parameter domains, and gate definitions. Check each adapter's native output capability before including it. A competitor that cannot reach a target must not be silently assisted by another competitor's optimizer.

CZ, ECR, RXX, and other native entanglers define separate target tracks. One instance of each gate is not assumed to have equal cost. Noise, durations, pulses, and schedules are excluded initially. Noise-aware tracks require identical frozen calibration snapshots.

End-to-end compilers choose initial placement; routing-only placement is fixed. Initially prohibit added workspace, allow only declared input clean ancillas, and check initialization/cleanup conditions. Reject input/target capacity mismatches in the manifest, not after measuring competitors.

## Pipelines and resources

Qiskit level 3 and pytket level 2 do not imply equal effort. Cirq requires explicit transformers; numerical synthesis depends on precision. Start with one documented fixed standard pipeline per compiler, confirm its intent with documentation/maintainers, and version adapter changes. Higher-quality and submitted configurations are separate entries.

A shared budget does not guarantee equal internal search effort, so always show quality and time together. A future best-within-budget track includes all candidate generation, retries, and seed search in its budget.

Proposed initial formal measurement profile:

- Same dedicated host; record CPU, OS, RAM, affinity, governor, runtime/thread environment.
- Enforce one total CPU core initially; declare workers and verify enforcement. Separate multicore tracks preserve parallel compilers' capabilities.
- Tentative 60-second per-case/per-seed and 8 GiB limits, verified on the chosen environment. Larger tracks have separate budgets.
- Five fixed compiler seeds. Record tools that do not support seeds.
- Three timing repetitions per seed. Report medians and IQRs, not the best seed.
- Interleave/shuffle execution and avoid contention. Distinguish cold and warm profiles, initialization costs, and cache behavior.

Timing boundaries are reported separately:

1. Parsing and representation conversion.
2. Pipeline/compiler initialization.
3. Optimization, decomposition, placement, routing, final lowering.
4. Export.
5. Independent validation.
6. User-visible end-to-end time.

Speed uses **2 + 3** from a loaded SDK. Circuit-dependent initialization and required final lowering are included. Startup/import, generation, I/O, and validation are not quietly charged to some compilers but omitted for others. Amortized initialization is a separate profile.

## Metrics

| Metric | Definition/use |
| --- | --- |
| Native 2Q count | Number of final native 2Q gates, with gate-type breakdown |
| 2Q depth | Longest weighted path in the full qubit-dependency DAG; 2Q weight 1, 1Q weight 0 |
| Total depth | Same DAG, all gate weights 1; barrier/measurement rules fixed per suite |
| 1Q count | Supporting metric; gate decomposition differences are disclosed |
| Compile time | Wall time for initialization + compilation; CPU time is supplementary |
| Peak memory | Include child processes/native memory, not only Python heap |
| Coverage/completion | Unsupported, errors, timeouts, OOMs, and validation outcomes against the full required set |
| SWAP count | Supporting routing diagnostic; not an end-to-end primary metric because swaps can be absorbed/decomposed |
| Estimated execution cost | Only with an explicitly shared duration/error model; not actual hardware success probability |

Use shared analysis rules and do not optimize or unnecessarily redecompose outputs while counting them.

## Correctness and validation tiers

Correctness is an entry condition, not a bonus score. Check gate set, coupling/direction, capacity, angle domains, unresolved boxes, input/output wire maps, implicit swaps, measurement-to-classical maps, ancilla rules, and precision contracts.

Keep these tiers separate:

1. **Equivalence checked:** e.g. [MQT QCEC](https://mqt.readthedocs.io/projects/qcec/en/stable/), with checker result type, tolerances, and assumptions retained. Timeout/inconclusive is not automatically compiler incorrectness.
2. **Numerically validated:** full small-unitary/isometry comparison, accounting for global phase, permutations, and ancillas. A proposed metric is global-phase-minimized normalized Frobenius distance ≤ 1e-8. This is numerical validation, not a mathematical proof.
3. **Sample tested:** declared multiple test inputs for larger circuits, not proof of arbitrary-input equivalence. Testing only the all-zero input is insufficient.
4. **Structurally checked only / unverified:** constraints checked without conclusive equivalence. Raw metrics can be shown provisionally, not mixed into verified rankings.

Compare within the same tier and precision contract. Approximate synthesis has a separate track with a shared distance metric and tolerance; internal compiler error estimates are not treated as independent verification. Declare whether the contract preserves the full unitary or only an isometry for specified initial states.

## Scores

This future formal proposal retains verification as an admission condition. The current viewer instead offers a separately named exploratory score, `qcec-adjusted-v1`: performance × passed/required QCEC seed slots, with asterisks, tinted cells, and before-penalty details. See the [implemented pilot scoring rule](pilot.md#scores-and-ui-views). That penalty is a policy choice, not measured approximation error or a hardware success probability; it does not amend the proposed formal track below.

Keep **Quality**, **Speed**, and **completion/validation** separate. Show a quality/time trade-off rather than presenting arbitrary weighting as an absolute winner.

Freeze a reference implementation and version when the formal suite is released, provisionally Qiskit with a specified pipeline. A reference score of 100 is an anchor, not a claim of superiority. Do not track the latest Qiskit silently; changing reference requires a new score version. Resolve reference failures before finalizing a suite rather than removing inconvenient cases after measurement.

For circuit i, use five-seed median 2Q count G_i, depth D_i, and nested median time T_i:

```text
rG_i = (G_i_ref + 1) / (G_i + 1)
rD_i = (D_i_ref + 1) / (D_i + 1)
rT_i = max(T_i_ref, tau) / max(T_i, tau)

q_f = exp(mean_i_in_family_f(0.5 ln(rG_i) + 0.5 ln(rD_i)))
s_f = exp(mean_i_in_family_f(ln(rT_i)))

Quality = 100 × exp(mean_f(ln(q_f)))
Speed   = 100 × exp(mean_f(ln(s_f)))
```

Weight sizes/variants equally within each family and families equally within each target. Seeds/repetitions are already aggregated and do not increase family weight. Publish separate count/depth scores as well. The 50:50 Quality weights are choices, not a universal physical objective.

`+1` smoothing avoids division by zero and affects tiny circuits; raw values must be visible. Proposed tau is 1 ms, to be confirmed against timer resolution and frozen per suite. A Quality score of 200 means a geometric-mean improvement in smoothed metrics, not doubled hardware success.

A future optional balanced view could use `sqrt(Quality × Speed)`, but should not replace the separate primary axes.

### Missing results and uncertainty

- Formal scores require all predefined cases and seeds to finish and meet the required validation tier.
- Keep unsupported, timeout, OOM, compiler error, invalid output, equivalence mismatch, and verification inconclusive distinct.
- In this proposed verified formal track, missing or unverified required cases withhold formal scores rather than using a surviving-case average. This differs from the separately versioned pass-rate-adjusted pilot scores.
- Publish recorded raw measurements even when equivalence checks fail, with check results alongside them. Reserve N/A for unavailable raw measurements. Keep output-rule checks separate from equivalence; unverified raw values are not verified winners. Predefined Small/Medium/Large subsuites can score independently if complete.
- Clearly label supplemental common-success-subset comparisons; they are not comparable to complete-suite or historical scores.
- Publish median/IQR and repetition counts. Consider family-aware resampling for intervals, but do not claim significance from a handful of seeds or tiny differences. Declare rounding and practical-difference thresholds.

## Formal MVP scope and implementation path

Candidate suite: six families, total-width budgets 8/16/32 including ancillas, two meaningful variants per size, three targets, four compilers, five seeds. Actual supported generator widths are fixed in the manifest. If all cases are available this gives 2,160 compilation trials, or 6,480 with three timing repetitions, plus reference/validation cost.

Start with a verified Small suite, then expand larger widths by validation tier. Shor can follow after arithmetic coverage improves; toy order-finding is labeled explicitly if added earlier.

The implemented pilot has already checked Qiskit/pytket on QFT/QAOA/adder with all-to-all/line targets. ucc-bench's inspected pytket adapter lacked target routing; Benchpress's broader suite was excessive for this narrow experiment. A small explicit runner was used instead of building a general plugin/job infrastructure.

The initial publication pipeline is **fixed manifest → offline measurement → JSON/CSV → static site**. Only add a database, API, scheduler, or large plugin layer after concrete operational requirements justify it. Rerun on SDK releases or monthly on a stable host. External submissions remain separate until comparable provenance and environment information are available.

Before expanding the formal benchmark, decide the project license, measurement host, standard pipelines, and frozen score version. The pilot is published under `yasuhito/transpiler-atlas` using GitHub Pages. No paid cloud use or hardware jobs have been performed.
