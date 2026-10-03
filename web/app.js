'use strict';

const data = JSON.parse(document.getElementById('benchmark-data').textContent);
const scoreVersion = data.score_version;
const $ = id => document.getElementById(id);
const median = values => {
  const xs = [...values].sort((a, b) => a - b);
  const middle = Math.floor(xs.length / 2);
  return xs.length % 2 ? xs[middle] : (xs[middle - 1] + xs[middle]) / 2;
};
const geometricMean = values => Math.exp(values.reduce((a, b) => a + Math.log(b), 0) / values.length);
const esc = value => String(value).replace(/[&<>"']/g, c => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[c]));
const sdkNames = { qiskit: 'Qiskit', pytket: 'pytket', bqskit: 'BQSKit' };
const legacyLabels = { qiskit: 'Preset level 2', pytket: 'Peephole + mapping + rebase', bqskit: 'Level 1 · 2Q blocks' };
const specs = data.protocol.configurations ?? data.protocol.compilers.map(compiler => ({ id: compiler, compiler, label: legacyLabels[compiler] }));
const compilerIds = specs.map(c => c.id);
const sdkIds = [...new Set(specs.map(c => c.compiler))];
const specFor = id => specs.find(c => c.id === id);
const sdkFor = id => specFor(id).compiler;
const label = id => sdkNames[sdkFor(id)] ?? sdkFor(id);
const entryLabel = id => `${label(id)} · ${specFor(id).label}`;
const approximationText = id => specFor(id)?.numerical_approximation ? '; approx. Numerical approximation' : '';
const approximationTag = id => specFor(id)?.numerical_approximation
  ? `<span class="approximation-tag" data-configuration="${esc(id)}" role="note" aria-label="Numerical approximation" aria-describedby="approximation-note">approx.</span>` : '';
const timeoutOnly = row => row.rows?.length === row.required && row.rows.every(r => r.status === 'timeout'
  && ![...Object.values(r.metrics ?? {}), r.compile_ms, ...(r.timing_samples_ms ?? [])].some(Number.isFinite) && !r.trials?.length);
const timeoutExplanation = 'Worker timed out before a verified result and completed measurements were recorded. This is not a returned equivalence failure.';
function timeoutScoreNote(row, key) {
  const affected = row.id ? [row] : (row.rows ?? []).filter(r => r[key === 'quality' ? 'rawQuality' : 'rawSpeed'] === null);
  return affected.length && affected.every(timeoutOnly) ? `<div>${timeoutExplanation}</div>` : '';
}
const approximationDetail = row => specFor(row.compiler)?.numerical_approximation
  ? '<div>Numerical approximation. <a href="docs/bqskit.html#numerical-approximation-and-unfinished-checks">See BQSKit notes.</a></div>' : '';
const colors = Object.fromEntries(specs.map(c => [c.id, `var(--${c.compiler})`]));
const configurations = Object.fromEntries(specs.map(c => [c.id, c.label]));
const referenceId = data.protocol.reference_configuration ?? 'qiskit';
const metrics = {
  quality: { name: 'Quality', higher: true, unit: 'QCEC-adjusted' },
  speed: { name: 'Speed', higher: true, unit: 'QCEC-adjusted' },
  count: { name: '2Q count', higher: false, unit: 'CX gates' },
  depth: { name: '2Q depth', higher: false, unit: 'layers' },
  time: { name: 'Compile time', higher: false, unit: 'ms' },
};
const defaults = { view: 'leaderboard', target: 'line', family: 'all', width: 'all', compiler: 'all', configuration: 'all', metric: 'quality', columns: 'on', y: 'count' };
const state = { ...defaults };
const enums = {
  view: ['leaderboard', 'circuits', 'matrix', 'tradeoff'],
  target: ['line', 'all-to-all'], family: ['all', ...new Set(data.cases.map(c => c.family))],
  width: ['all', ...new Set(data.cases.map(c => String(c.qubits)))], compiler: ['all', ...sdkIds], configuration: ['all', ...compilerIds],
  metric: Object.keys(metrics), columns: ['on', 'off'], y: ['count', 'depth'],
};

$('compiler').innerHTML = '<option value="all">All SDKs</option>' + sdkIds.map(c => `<option value="${esc(c)}">${esc(sdkNames[c])}</option>`).join('');
document.querySelector('.legend').innerHTML = sdkIds.map(c => `<span><i class="dot ${esc(c)}"></i>${esc(sdkNames[c])}</span>`).join('');
$('width').innerHTML = '<option value="all">All widths</option>' + [...new Set(data.cases.map(c => c.qubits))].sort((a, b) => a - b).map(n => `<option value="${n}">${n} qubits</option>`).join('');
document.querySelector('.categories').innerHTML = enums.family.map(f => `<button data-family="${esc(f)}" aria-pressed="${f === 'all'}">${f === 'all' ? 'All' : esc(f)}</button>`).join('');

function readHash() {
  const params = new URLSearchParams(location.hash.slice(1));
  for (const key of Object.keys(defaults)) {
    state[key] = enums[key].includes(params.get(key)) ? params.get(key) : defaults[key];
  }
}
function syncControls() {
  const available = specs.filter(c => state.compiler === 'all' || c.compiler === state.compiler);
  if (state.configuration !== 'all' && !available.some(c => c.id === state.configuration)) state.configuration = 'all';
  $('configuration').innerHTML = '<option value="all">All configurations</option>' + available.map(c => `<option value="${esc(c.id)}">${esc(entryLabel(c.id))}</option>`).join('');
  for (const key of ['target', 'width', 'compiler', 'configuration', 'metric']) $(key).value = state[key];
  $('columns').checked = state.columns === 'on';
  $('plot-y').value = state.y;
  document.querySelectorAll('[data-family]').forEach(button => {
    button.setAttribute('aria-pressed', String(button.dataset.family === state.family));
  });
  document.querySelectorAll('[data-view]').forEach(button => {
    const active = button.dataset.view === state.view;
    button.setAttribute('aria-selected', String(active));
    button.tabIndex = active ? 0 : -1;
  });
  $('result-panel').setAttribute('aria-labelledby', 'tab-' + state.view);
}
function saveHash() {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(state)) if (value !== defaults[key]) params.set(key, value);
  const hash = params.toString();
  history.replaceState(null, '', location.pathname + location.search + (hash ? '#' + hash : ''));
  $('permalink').href = location.href;
}
function measuredMedian(values) {
  const available = values.filter(Number.isFinite);
  return available.length ? median(available) : null;
}
function trialPassed(row) {
  return row.status === 'passed' && row.trials?.length === data.protocol.timing_repeats
    && row.trials.every(t => t.validation.accepted);
}
function aggregate(cases) {
  return cases.flatMap(circuit => compilerIds.map(compiler => {
    const matching = data.results.filter(r => r.target === state.target && r.case_id === circuit.id && (r.configuration_id ?? r.compiler) === compiler);
    // Count each scheduled seed slot once; ambiguous duplicates are not accepted.
    const expected = [...data.protocol.seeds].sort((a, b) => a - b);
    const rows = expected.flatMap(seed => {
      const matches = matching.filter(r => r.seed === seed);
      return matches.length === 1 ? matches : [];
    });
    const seeds = rows.map(r => r.seed).sort((a, b) => a - b);
    const measuredRows = rows.filter(r => [r.metrics?.two_qubit_count, r.metrics?.two_qubit_depth, r.compile_ms].every(Number.isFinite));
    const measurementComplete = JSON.stringify(seeds) === JSON.stringify(expected) && measuredRows.length === expected.length;
    const passed = rows.filter(trialPassed).length;
    const complete = measurementComplete && passed === expected.length;
    const rulesMet = measurementComplete && rows.every(r => ['passed', 'verification_failed'].includes(r.status));
    return {
      id: circuit.id, family: circuit.family, qubits: circuit.qubits, compiler, complete, rows,
      measured: measuredRows.length, required: expected.length, measurementComplete, passed, rulesMet,
      count: measuredMedian(rows.map(r => r.metrics?.two_qubit_count)),
      depth: measuredMedian(rows.map(r => r.metrics?.two_qubit_depth)),
      time: measuredMedian(rows.map(r => r.compile_ms)),
      one: measuredMedian(rows.map(r => r.metrics?.one_qubit_count)),
      total: measuredMedian(rows.map(r => r.metrics?.total_depth)),
    };
  }));
}
function scoreCases(items) {
  for (const row of items) {
    const ref = items.find(r => r.id === row.id && r.compiler === referenceId);
    row.rawQuality = [row.count, row.depth, ref?.count, ref?.depth].every(Number.isFinite)
      ? 100 * Math.sqrt((ref.count + 1) / (row.count + 1) * (ref.depth + 1) / (row.depth + 1)) : null;
    row.rawSpeed = [row.time, ref?.time].every(Number.isFinite)
      ? 100 * Math.max(ref.time, 1) / Math.max(row.time, 1) : null;
    row.passSlots = row.passed;
    row.requiredSlots = row.required;
    row.validationRate = row.passSlots / row.requiredSlots;
    row.quality = row.rawQuality === null ? null : row.rawQuality * row.validationRate;
    row.speed = row.rawSpeed === null ? null : row.rawSpeed * row.validationRate;
  }
  return items;
}
function groupedScore(rows, key) {
  if (!rows.length || rows.some(r => r[key] === null)) return null;
  const families = [...new Set(rows.map(r => r.family))];
  return geometricMean(families.map(f => geometricMean(rows.filter(r => r.family === f).map(r => r[key]))));
}
function scoreSummary(rows) {
  const passSlots = rows.reduce((n, r) => n + r.passed, 0);
  const requiredSlots = rows.reduce((n, r) => n + r.required, 0);
  const validationRate = requiredSlots ? passSlots / requiredSlots : 0;
  const rawQuality = groupedScore(rows, 'rawQuality');
  const rawSpeed = groupedScore(rows, 'rawSpeed');
  return {
    passSlots, requiredSlots, validationRate, rawQuality, rawSpeed,
    quality: rawQuality === null ? null : rawQuality * validationRate,
    speed: rawSpeed === null ? null : rawSpeed * validationRate,
  };
}
function compilerRows(items, compilers) {
  return compilers.map(compiler => {
    const rows = items.filter(r => r.compiler === compiler);
    const complete = rows.length > 0 && rows.every(r => r.complete);
    const families = [...new Set(rows.map(r => r.family))];
    return {
      compiler, rows, complete, passed: rows.filter(r => r.complete).length,
      measured: rows.filter(r => r.measured > 0).length,
      partial: rows.some(r => !r.measurementComplete),
      ...scoreSummary(rows),
      count: measuredMedian(rows.map(r => r.count)),
      depth: measuredMedian(rows.map(r => r.depth)),
      time: measuredMedian(rows.map(r => r.time)),
      familyScores: Object.fromEntries(families.map(f => [f, scoreSummary(rows.filter(r => r.family === f))])),
    };
  });
}
function compare(a, b) {
  const x = a[state.metric], y = b[state.metric];
  if (x === null && y === null) return a.compiler.localeCompare(b.compiler);
  if (x === null) return 1;
  if (y === null) return -1;
  return (metrics[state.metric].higher ? y - x : x - y)
    || (a.id ?? '').localeCompare(b.id ?? '') || a.compiler.localeCompare(b.compiler);
}
function value(v, key) {
  if (v === null || v === undefined) return 'N/A';
  return ['count', 'depth', 'one', 'total'].includes(key) ? String(v) : v.toFixed(key === 'time' ? 2 : key === 'speed' && v > 0 && v < 1 ? 3 : 1);
}
function heading(key, caption = metrics[key].name) {
  const active = state.metric === key;
  return `<th class="num" scope="col"${active ? ' aria-sort="' + (metrics[key].higher ? 'descending' : 'ascending') + '"' : ''}><button data-sort="${key}" aria-label="Sort by ${esc(caption)}">${esc(caption)}${active ? ' ' + (metrics[key].higher ? '↓' : '↑') : ''}</button><small>${esc(metrics[key].unit)}</small></th>`;
}
function scoreExplanation(row, key) {
  const base = row[key === 'quality' ? 'rawQuality' : 'rawSpeed'];
  if (!Number.isFinite(row[key])) {
    const rawKey = key === 'quality' ? 'rawQuality' : 'rawSpeed';
    const affected = row.id ? [row.id] : (row.rows ?? []).filter(r => r[rawKey] === null).map(r => r.id);
    return 'N/A: required raw measurements or Qiskit reference values are unavailable.' + (affected.length ? ' Affected circuits: ' + affected.join(', ') + '.' : '');
  }
  return `Before penalty: ${value(base, key)}; QCEC passed ${row.passSlots}/${row.requiredSlots} slots (${(row.validationRate * 100).toFixed(1)}%); score = before penalty × pass rate.`;
}
function scoreContent(row, key) {
  const marked = Number.isFinite(row[key]) && row.validationRate < 1;
  const base = row[key === 'quality' ? 'rawQuality' : 'rawSpeed'];
  const unavailable = !Number.isFinite(row[key]) ? `<details class="score-breakdown"><summary aria-label="Why is this score unavailable?">Why?</summary><div>${esc(scoreExplanation(row, key))}</div>${timeoutScoreNote(row, key)}${approximationDetail(row)}</details>` : '';
  const detail = marked ? `<details class="score-breakdown"><summary>Details</summary><div>Before penalty: ${value(base, key)}<br>QCEC passed ${row.passSlots}/${row.requiredSlots} slots<br>Pass rate: ${(row.validationRate * 100).toFixed(1)}%<br>Score = before penalty × pass rate.</div>${approximationDetail(row)}</details>` : '';
  return `<span class="score-value">${value(row[key], key)}${marked ? '<span class="score-marker" aria-label="QCEC pass-rate penalty" aria-describedby="score-note">*</span>' : ''}</span>${detail}${unavailable}`;
}
function numberCell(row, key, options = {}) {
  const samples = key === 'time' && row.rows ? row.rows.flatMap(r => r.timing_samples_ms ?? []) : [];
  const provisional = !row.complete && !['quality', 'speed'].includes(key) && Number.isFinite(row[key]);
  const scored = ['quality', 'speed'].includes(key);
  const penalized = scored && Number.isFinite(row[key]) && row.validationRate < 1;
  const selected = options.selected ?? state.metric === key;
  const tooltip = [scored ? scoreExplanation(row, key) : provisional ? 'Raw measurements; not all strict equivalence checks passed.' : '', samples.length ? `${samples.length} timing samples: ${Math.min(...samples).toFixed(2)} to ${Math.max(...samples).toFixed(2)} ms` : ''].filter(Boolean).join(' ');
  const status = options.matrix && !row.complete ? `<span class="cell-sub measurement-warning">${timeoutOnly(row) ? 'Not verified' : 'Unverified'} · QCEC ${row.passed}/${row.required}</span><span class="cell-sub">${timeoutOnly(row) ? 'No measurement · ' : ''}Measured ${row.measured}/${row.required}</span>` : options.matrix && state.columns === 'on' ? '<span class="cell-sub">QCEC passed</span>' : '';
  return `<td class="num${selected ? ' selected-metric' : ''}${provisional ? ' unverified-metric' : ''}${penalized ? ' penalized-score' : ''}"${tooltip ? ' title="' + esc(tooltip) + '"' : ''}>${scored ? scoreContent(row, key) : value(row[key], key)}${status}${options.matrix ? approximationTag(row.compiler) : ''}</td>`;
}
function nameCell(compiler, detailed) {
  return `<span class="compiler-name"><i class="dot ${sdkFor(compiler)}"></i>${label(compiler)}</span>${detailed ? '<span class="sub mono">' + esc(data.environment.versions[sdkFor(compiler)]) + '</span>' : ''}<span class="sub">${esc(configurations[compiler])} ${approximationTag(compiler)}</span>`;
}
function renderLeaderboard(items, compilers) {
  const rows = compilerRows(items, compilers).sort(compare);
  const families = [...new Set(items.map(r => r.family))];
  const detailed = state.columns === 'on';
  $('result-head').innerHTML = `<tr><th scope="col">#</th><th scope="col">Compiler / configuration</th>${heading('quality')}${heading('speed')}${heading('count')}${heading('depth')}${heading('time')}${detailed ? families.map(f => '<th class="num" scope="col">' + esc(f) + '<small>quality</small></th>').join('') : ''}<th class="num" scope="col">Coverage<small>circuits</small></th></tr>`;
  $('result-rows').innerHTML = rows.map(row => {
    const eligible = r => Number.isFinite(r[state.metric]) && (['quality', 'speed'].includes(state.metric) || r.complete);
    const rank = eligible(row) ? 1 + rows.filter(r => eligible(r) && (metrics[state.metric].higher ? r[state.metric] > row[state.metric] : r[state.metric] < row[state.metric])).length : 'Not ranked';
    const status = row.complete ? '' : `<span class="sub measurement-warning">${row.measured ? (row.partial ? 'Partial measurements; unverified' : 'Unverified measurements') : 'No measurements'}</span>`;
    return `<tr data-compiler="${row.compiler}"><td class="rank">${rank}</td><td>${nameCell(row.compiler, true)}${status}</td>${['quality', 'speed', 'count', 'depth', 'time'].map(k => numberCell(row, k)).join('')}${detailed ? families.map(f => numberCell({ ...row.familyScores[f], compiler: row.compiler, rows: row.rows.filter(r => r.family === f) }, 'quality', { selected: false })).join('') : ''}<td class="num">Measured ${row.measured}/${row.rows.length}<span class="cell-sub ${row.complete ? 'valid' : ''}">QCEC ${row.passSlots}/${row.requiredSlots} slots</span></td></tr>`;
  }).join('');
  $('view-note').innerHTML = 'Quality and Speed = unpenalized performance × QCEC pass rate. Performance uses equal family weights and a measured Qiskit level 2 reference of 100; the pass rate weights each required seed slot equally. Details shows the value before penalty. Scores are experimental benchmark rules, not hardware success probabilities. Raw metrics include unverified measurements; partial coverage is labeled. N/A means a required circuit lacks measurements or reference values, not simply a failed QCEC check. A worker timeout means no completed measurement and no verified result, not a returned equivalence failure. Why? identifies the affected circuits; select a measured family or width to compare those configurations. The approx. tag describes numerical synthesis, not a score adjustment. <a href="docs/pilot.html">Definitions ↗</a>';
}
function inputDetails(id) {
  const circuit = data.cases.find(c => c.id === id);
  const p = circuit.provenance;
  const source = p ? `<a href="${esc(p.url)}">${esc(p.corpus)} source ↗</a> · <a href="${esc(p.source_path)}">Original QASM</a> · <a href="${esc(p.license_path)}">License</a>` : 'Atlas-generated input';
  return `<details class="input-details"><summary>Input details</summary>${source}<div class="mono">${esc(JSON.stringify(circuit.parameters))}</div><div>${esc(p?.transformation ?? 'Qiskit level-0 lowering')}</div><div class="mono">SHA-256: ${esc(circuit.sha256)}</div></details>`;
}
function validationDetails(row) {
  if (row.complete) return '';
  const slots = row.rows.map(r => {
    const criteria = (r.trials ?? []).map(t => t.validation.criterion).join(', ');
    const description = [r.status === 'timeout' ? r.error : '', criteria].filter(Boolean).join('; ');
    const missing = timeoutOnly({ rows: [r], required: 1 }) ? 'Not verified; no completed measurement.' : '';
    return `<div>Seed slot ${r.seed}: ${esc(r.status)}; ${esc(description + (missing ? (description ? '. ' : '') + missing : ''))}</div>`;
  }).join('');
  return `<details class="input-details"><summary>Validation details</summary>${slots}</details>`;
}
function equivalenceLabel(row) {
  if (row.complete) return 'QCEC passed';
  if (row.rows.some(r => r.status === 'verification_failed' || r.trials?.some(t => !t.validation.accepted))) return 'Strict check failed';
  return timeoutOnly(row) ? 'Not verified' : 'Incomplete checks';
}
function outputRules(row) {
  return `<span class="${row.rulesMet ? 'valid' : 'artifact'}">${row.rulesMet ? 'Output rules met' : 'Output rules not fully checked'}</span><span class="cell-sub">${timeoutOnly(row) ? 'No measurement · ' : ''}Measured ${row.measured}/${row.required} slots</span>${!row.measurementComplete && row.measured ? '<span class="cell-sub measurement-warning">Partial measurements</span>' : ''}`;
}
function renderCircuits(items) {
  const detailed = state.columns === 'on';
  const scoreColumn = ['quality', 'speed'].includes(state.metric);
  $('result-head').innerHTML = `<tr><th scope="col">Circuit</th><th scope="col">Compiler</th>${scoreColumn ? heading(state.metric) : ''}${heading('count')}${heading('depth')}${heading('time')}${detailed ? '<th class="num" scope="col">1Q count</th><th class="num" scope="col">Total depth</th>' : ''}<th scope="col">Output rules<small>gates / connections</small></th><th scope="col">Equivalence / artifact</th></tr>`;
  $('result-rows').innerHTML = [...items].sort(compare).map(row => {
    const artifact = row.rows.flatMap(r => r.trials ?? []).find(t => t.artifact)?.artifact;
    return `<tr data-compiler="${row.compiler}"><td><strong class="mono">${esc(row.id)}</strong><span class="sub" style="margin-left:0">${esc(row.family)} · ${row.qubits} qubits</span>${inputDetails(row.id)}</td><td>${nameCell(row.compiler, detailed)}</td>${scoreColumn ? numberCell(row, state.metric) : ''}${['count', 'depth', 'time'].map(k => numberCell(row, k)).join('')}${detailed ? numberCell(row, 'one') + numberCell(row, 'total') : ''}<td>${outputRules(row)}</td><td><span class="${row.complete ? 'valid' : 'measurement-warning'}">${equivalenceLabel(row)}</span><span class="cell-sub">QCEC ${row.passed}/${row.required} slots</span>${validationDetails(row)}${artifact ? ' · <a class="artifact" href="' + esc(artifact) + '">QASM ↗</a>' : ''}</td></tr>`;
  }).join('');
  $('view-note').textContent = 'Raw medians include every measured seed slot, regardless of strict equivalence results. Missing slots are excluded from raw medians and labeled partial. Output rules check gates, connections, and width, separately from equivalence. Quality and Speed include a QCEC pass-rate penalty, marked with *. The approx. tag describes numerical synthesis and does not replace the individual QCEC result. N/A means required raw measurements or reference values are unavailable. Timed-out workers are not verified and have no completed measurements. Hover over time for the sample range. QASM opens the first recorded output.';
}
function renderMatrix(items, cases, compilers) {
  const metric = metrics[state.metric];
  $('result-head').innerHTML = `<tr><th scope="col">Circuit</th><th class="num" scope="col">Qubits</th>${compilers.map(c => '<th class="num" scope="col">' + esc(entryLabel(c)) + ' ' + approximationTag(c) + '<small>' + esc(metric.name) + ' · ' + esc(metric.unit) + '</small></th>').join('')}</tr>`;
  $('result-rows').innerHTML = cases.map(circuit => {
    const rows = compilers.map(c => items.find(r => r.id === circuit.id && r.compiler === c));
    const eligible = r => Number.isFinite(r[state.metric]) && (['quality', 'speed'].includes(state.metric) || r.complete);
    const available = rows.filter(eligible).map(r => r[state.metric]);
    const best = available.length ? (metric.higher ? Math.max(...available) : Math.min(...available)) : null;
    return `<tr><td class="mono">${esc(circuit.id)}</td><td class="num">${circuit.qubits}</td>${rows.map(r => numberCell(r, state.metric, { selected: eligible(r) && r[state.metric] === best, matrix: true })).join('')}</tr>`;
  }).join('');
  $('view-note').textContent = `One row per circuit. Raw values remain visible for unverified outputs. Best-value shading includes pass-rate-adjusted scores; for raw metrics it only compares fully verified outputs. Tinted * scores include a QCEC penalty. The approx. tag is configuration metadata, not an additional penalty. N/A means no required measurement or reference value; it does not mean a returned equivalence failure. ${metric.name}: ${metric.higher ? 'higher' : 'lower'} is better. Scores are per-circuit comparisons, not suite-level scores.`;
}
function renderPlot(items) {
  $('view-note').textContent = 'Each point is one compiler/circuit raw median, not a verified rank or suite score. Filled points passed all required checks; hollow points include unverified or partial measurements. No measurement means no point. The approx. tag describes numerical synthesis; point fill still shows individual verification coverage. Details and artifacts are in Per circuit.';
  const rows = items.filter(r => Number.isFinite(r.time) && Number.isFinite(r[state.y]));
  if (!rows.length) { $('chart').textContent = 'No measurements to plot.'; return; }
  const width = Math.max(300, $('chart').clientWidth), mobile = width < 650;
  const height = mobile ? 300 : 350, left = 48, right = mobile ? 25 : 80, top = 32, bottom = 52;
  const times = rows.map(r => r.time), key = state.y;
  const lo = Math.floor(Math.log10(Math.max(Math.min(...times) * .7, .001)));
  const hi = Math.max(lo + 1, Math.ceil(Math.log10(Math.max(...times) * 1.3)));
  const ymax = Math.max(10, Math.ceil(Math.max(...rows.map(r => r[key])) / 20) * 20);
  const x = v => left + (Math.log10(Math.max(v, .001)) - lo) / (hi - lo) * (width - left - right);
  const y = v => height - bottom - v / ymax * (height - top - bottom);
  let svg = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="chart-title chart-desc"><title id="chart-title">${metrics[key].name} versus compile time</title><desc id="chart-desc">${esc(rows.map(r => `${r.id}, ${entryLabel(r.compiler)}${approximationText(r.compiler)}, ${r[key]} ${metrics[key].unit}, ${r.time.toFixed(2)} ms, ${equivalenceLabel(r)}, measured ${r.measured}/${r.required} slots`).join('; '))}</desc>`;
  for (let i = 0; i <= 4; i++) {
    const v = ymax * i / 4;
    svg += `<line x1="${left}" x2="${width - right}" y1="${y(v)}" y2="${y(v)}" stroke="#e9ecf1"/><text x="${left - 12}" y="${y(v) + 4}" text-anchor="end" fill="#818b99" font-size="10">${v}</text>`;
  }
  for (let p = lo; p <= hi; p++) {
    const v = 10 ** p;
    svg += `<line x1="${x(v)}" x2="${x(v)}" y1="${top}" y2="${height - bottom}" stroke="#e9ecf1"/><text x="${x(v)}" y="${height - bottom + 22}" text-anchor="middle" fill="#818b99" font-size="10">${v.toLocaleString('en-US', { maximumFractionDigits: 3 })}</text>`;
  }
  for (const id of new Set(rows.map(r => r.id))) {
    const group = rows.filter(r => r.id === id);
    const reference = group.find(r => r.compiler === 'qiskit');
    if (reference) for (const row of group.filter(r => r !== reference)) {
      svg += `<line x1="${x(reference.time)}" y1="${y(reference[key])}" x2="${x(row.time)}" y2="${y(row[key])}" stroke="var(--border)" stroke-dasharray="3 4"/>`;
    }
  }
  const points = rows.map(row => ({ row, px: x(row.time), py: y(row[key]) }));
  const occupied = [];
  const intersects = (a, b) => a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
  for (const { row, px, py } of [...points].sort((a, b) => a.py - b.py)) {
    const description = `${row.id} / ${entryLabel(row.compiler)}${approximationText(row.compiler)}: ${row[key]} ${metrics[key].unit}, ${row.time.toFixed(2)} ms; ${equivalenceLabel(row)}, QCEC ${row.passed}/${row.required}, measured ${row.measured}/${row.required} slots`;
    svg += `<circle data-case-id="${esc(row.id)}" data-compiler="${esc(row.compiler)}" data-verified="${row.complete}" style="--point-color:${colors[row.compiler]}" class="${esc(sdkFor(row.compiler))}${row.complete ? '' : ' unverified'}" cx="${px}" cy="${py}" r="4.5" fill="${colors[row.compiler]}" stroke="white" stroke-width="1.5" tabindex="0"${specFor(row.compiler)?.numerical_approximation ? ' aria-describedby="approximation-note"' : ''} aria-label="${esc(description)}"><title>${esc(description)}</title></circle>`;
    if (mobile) continue;
    const labelWidth = row.id.length * 6 + 4;
    const candidates = [8, -10, 24, -26, 40, -42].flatMap(dy => [
      { x: px + 9, y: py + dy - 10, w: labelWidth, h: 14 },
      { x: px - labelWidth - 9, y: py + dy - 10, w: labelWidth, h: 14 },
    ]);
    const box = candidates.find(b => b.x >= left && b.x + b.w <= width - 8 && b.y >= top - 12 && b.y + b.h <= height - bottom
      && !occupied.some(o => intersects(b, o))
      && !points.some(p => intersects(b, { x: p.px - 6, y: p.py - 6, w: 12, h: 12 })));
    if (!box) continue;
    occupied.push(box);
    if (Math.abs(box.y + 10 - py) > 20) svg += `<line x1="${px}" y1="${py}" x2="${box.x}" y2="${box.y + 6}" stroke="${colors[row.compiler]}" opacity=".35"/>`;
    svg += `<text class="chart-label ${esc(sdkFor(row.compiler))}" x="${box.x}" y="${box.y + 10}" fill="${colors[row.compiler]}" font-size="10">${esc(row.id)}</text>`;
  }
  svg += `<text x="${left}" y="16" fill="#6e7887" font-size="11">${metrics[key].name}</text><text x="${(width + left - right) / 2}" y="${height - 6}" text-anchor="middle" fill="#6e7887" font-size="10">Compile time · ms (log scale)</text></svg>`;
  $('chart').innerHTML = svg;
}
function render() {
  syncControls();
  saveHash();
  const cases = data.cases.filter(c => (state.family === 'all' || c.family === state.family) && (state.width === 'all' || String(c.qubits) === state.width));
  const compilers = compilerIds.filter(c => (state.compiler === 'all' || sdkFor(c) === state.compiler) && (state.configuration === 'all' || c === state.configuration));
  const allItems = scoreCases(aggregate(cases));
  const items = allItems.filter(r => compilers.includes(r.compiler));
  const plot = state.view === 'tradeoff';
  $('table-container').hidden = plot || !cases.length;
  $('plot-container').hidden = !plot || !cases.length;
  $('empty').hidden = cases.length > 0;
  $('score-note').hidden = plot || !cases.length;
  if ($('approximation-note')) {
    const annotated = compilers.map(specFor).filter(c => c.numerical_approximation);
    $('approximation-note').hidden = !cases.length || !annotated.length;
    $('approximation-note-text').textContent = annotated[0]?.approximation_note ?? '';
  }
  $('columns').disabled = plot;
  $('columns').closest('label').hidden = plot;
  $('metric').closest('.field').hidden = plot;
  document.querySelector('label[for="metric"]').textContent = state.view === 'matrix' ? 'Metric' : 'Metric / order';
  $('target-note').innerHTML = `Atlas-designed synthetic target, not a named device or corpus requirement. ${state.target === 'line' ? 'Line: CX only between neighboring qubits, in either direction.' : 'All-to-all: CX between any pair, in either direction.'} Physical width equals input width; no extra qubits. <a href="docs/pilot.html#target-and-pipelines">Target definition ↗</a>`;
  const passedSlots = items.reduce((n, r) => n + r.passed, 0);
  const requiredSlots = items.reduce((n, r) => n + r.required, 0);
  $('selection-status').textContent = `${cases.length} circuits · ${compilers.length} configurations · ${items.filter(r => r.measured > 0).length}/${items.length} measured runs · QCEC ${passedSlots}/${requiredSlots} seed slots passed · ${state.target === 'line' ? 'Line' : 'All-to-all'}`;
  $('metric-direction').textContent = plot ? 'Both axes: lower is better' : `${metrics[state.metric].name}: ${metrics[state.metric].higher ? 'higher' : 'lower'} is better`;
  if (!cases.length) { $('result-head').innerHTML = ''; $('result-rows').innerHTML = ''; $('view-note').textContent = ''; return; }
  if (state.view === 'leaderboard') renderLeaderboard(allItems, compilers);
  if (state.view === 'circuits') renderCircuits(items);
  if (state.view === 'matrix') renderMatrix(allItems, cases, compilers);
  if (plot) renderPlot(items);
}
function reset() { Object.assign(state, defaults); render(); }
for (const key of ['target', 'width', 'compiler', 'configuration', 'metric']) $(key).addEventListener('change', () => { state[key] = $(key).value; render(); });
$('columns').addEventListener('change', () => { state.columns = $('columns').checked ? 'on' : 'off'; render(); });
$('plot-y').addEventListener('change', () => { state.y = $('plot-y').value; render(); });
$('reset').addEventListener('click', reset);
$('empty-reset').addEventListener('click', reset);
document.querySelectorAll('[data-family]').forEach(button => button.addEventListener('click', () => { state.family = button.dataset.family; render(); }));
document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => { state.view = button.dataset.view; render(); }));
$('result-head').addEventListener('click', event => {
  const button = event.target.closest('[data-sort]');
  if (button) { state.metric = button.dataset.sort; render(); }
});
document.querySelector('.views').addEventListener('keydown', event => {
  const buttons = [...document.querySelectorAll('[data-view]')];
  const i = buttons.indexOf(document.activeElement);
  if (i < 0 || !['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(event.key)) return;
  event.preventDefault();
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : (i + (event.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length;
  buttons[next].focus(); state.view = buttons[next].dataset.view; render();
});
window.addEventListener('hashchange', () => { readHash(); render(); });
window.addEventListener('resize', () => { if (state.view === 'tradeoff') render(); });

const trials = data.results.flatMap(r => r.trials ?? []);
const accepted = trials.filter(t => t.validation.accepted).length;
$('suite-version').textContent = data.suite.replace('pilot-v', 'Pilot v');
$('score-version').textContent = 'Scores: ' + scoreVersion;
$('updated').textContent = 'Measured ' + (data.updated_at ?? data.created_at).slice(0, 10);
$('dataset-meta').textContent = `${data.cases.length} circuits · ${sdkIds.length} SDKs · ${compilerIds.length} configurations · 2 topologies · ${accepted}/${trials.length} QCEC checks passed`;
$('footer-meta').textContent = `${data.suite} · rz / sx / x / cx · ${data.environment.python ? 'Python ' + data.environment.python : ''}`;
const env = data.environment;
const fields = [
  ['CPU', env.cpu], ['Affinity', env.cpu_affinity.join(', ')], ['OS', env.platform],
  ['Versions', Object.entries(env.versions).map(([k, v]) => k + ' ' + v).join(' · ')],
  ['Qiskit', data.protocol.qiskit_pipeline], ['pytket', Array.isArray(data.protocol.pytket_pipeline) ? data.protocol.pytket_pipeline.join(' → ') : JSON.stringify(data.protocol.pytket_pipeline)],
  ...(data.protocol.bqskit_pipeline ? [['BQSKit', JSON.stringify(data.protocol.bqskit_pipeline)]] : []),
  ['Targets', 'Atlas-designed synthetic targets, not a named device or a corpus requirement. Input-width line or all-to-all; bidirectional CX; no added workspace.'],
  ['Score version', scoreVersion + ': performance × QCEC pass rate; a pass-rate penalty is not a measured physical error.'],
  ['Worker budget', `${data.protocol.worker_timeout_seconds} s per circuit/configuration/target/seed worker, including three compilations, checks, and startup/shutdown; not a per-compilation timeout.`],
  ...(data.protocol.timeout_retry_entries ? [['Retries', `${data.protocol.timeout_retry_entries} initial ${data.protocol.initial_worker_timeout_seconds} s timeouts retried at ${data.protocol.worker_timeout_seconds} s; ${data.results.length - data.protocol.timeout_retry_entries} completed outcomes retained. Initial results and previous attempts remain in raw data.`]] : []),
  ['Validation', data.protocol.validation],
  ...specs.filter(c => c.numerical_approximation).map(c => ['Configuration note: ' + c.id, c.approximation_note]),
];
$('environment-fields').innerHTML = fields.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');
readHash(); render();
