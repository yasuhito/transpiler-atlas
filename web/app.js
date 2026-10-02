'use strict';

const data = JSON.parse(document.getElementById('benchmark-data').textContent);
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
const compilerIds = data.protocol.compilers ?? [...new Set(data.results.map(r => r.compiler))];
const label = compiler => ({ qiskit: 'Qiskit', pytket: 'pytket', bqskit: 'BQSKit' })[compiler] ?? compiler;
const colors = { qiskit: 'var(--qiskit)', pytket: 'var(--pytket)', bqskit: 'var(--bqskit)' };
const configurations = { qiskit: 'Preset level 2', pytket: 'Peephole + mapping + rebase', bqskit: 'Level 1 · 2Q blocks' };
const metrics = {
  quality: { name: 'Quality', higher: true, unit: 'reference = 100' },
  speed: { name: 'Speed', higher: true, unit: 'reference = 100' },
  count: { name: '2Q count', higher: false, unit: 'CX gates' },
  depth: { name: '2Q depth', higher: false, unit: 'layers' },
  time: { name: 'Compile time', higher: false, unit: 'ms' },
};
const defaults = { view: 'leaderboard', target: 'line', family: 'all', width: 'all', compiler: 'all', metric: 'quality', columns: 'on', y: 'count' };
const state = { ...defaults };
const enums = {
  view: ['leaderboard', 'circuits', 'matrix', 'tradeoff'],
  target: ['line', 'all-to-all'], family: ['all', ...new Set(data.cases.map(c => c.family))],
  width: ['all', ...new Set(data.cases.map(c => String(c.qubits)))], compiler: ['all', ...compilerIds],
  metric: Object.keys(metrics), columns: ['on', 'off'], y: ['count', 'depth'],
};

$('compiler').innerHTML = '<option value="all">All compilers</option>' + compilerIds.map(c => `<option value="${esc(c)}">${esc(label(c))}</option>`).join('');
document.querySelector('.legend').innerHTML = compilerIds.map(c => `<span><i class="dot ${esc(c)}"></i>${esc(label(c))}</span>`).join('');
$('width').innerHTML = '<option value="all">All widths</option>' + [...new Set(data.cases.map(c => c.qubits))].sort((a, b) => a - b).map(n => `<option value="${n}">${n} qubits</option>`).join('');
document.querySelector('.categories').innerHTML = enums.family.map(f => `<button data-family="${esc(f)}" aria-pressed="${f === 'all'}">${f === 'all' ? 'All' : esc(f)}</button>`).join('');

function readHash() {
  const params = new URLSearchParams(location.hash.slice(1));
  for (const key of Object.keys(defaults)) {
    state[key] = enums[key].includes(params.get(key)) ? params.get(key) : defaults[key];
  }
}
function syncControls() {
  for (const key of ['target', 'width', 'compiler', 'metric']) $(key).value = state[key];
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
function aggregate(cases) {
  return cases.flatMap(circuit => compilerIds.map(compiler => {
    const rows = data.results.filter(r => r.target === state.target && r.case_id === circuit.id && r.compiler === compiler);
    const seeds = rows.map(r => r.seed).sort((a, b) => a - b);
    const expected = [...data.protocol.seeds].sort((a, b) => a - b);
    const complete = JSON.stringify(seeds) === JSON.stringify(expected) && rows.every(r => r.status === 'passed');
    return {
      id: circuit.id, family: circuit.family, qubits: circuit.qubits, compiler, complete, rows,
      count: complete ? median(rows.map(r => r.metrics.two_qubit_count)) : null,
      depth: complete ? median(rows.map(r => r.metrics.two_qubit_depth)) : null,
      time: complete ? median(rows.map(r => r.compile_ms)) : null,
      one: complete ? median(rows.map(r => r.metrics.one_qubit_count)) : null,
      total: complete ? median(rows.map(r => r.metrics.total_depth)) : null,
    };
  }));
}
function scoreCases(items) {
  for (const row of items) {
    const ref = items.find(r => r.id === row.id && r.compiler === 'qiskit');
    row.quality = row.complete && ref?.complete
      ? 100 * Math.sqrt((ref.count + 1) / (row.count + 1) * (ref.depth + 1) / (row.depth + 1)) : null;
    row.speed = row.complete && ref?.complete ? 100 * Math.max(ref.time, 1) / Math.max(row.time, 1) : null;
  }
  return items;
}
function groupedScore(rows, key) {
  if (!rows.length || rows.some(r => r[key] === null)) return null;
  const families = [...new Set(rows.map(r => r.family))];
  return geometricMean(families.map(f => geometricMean(rows.filter(r => r.family === f).map(r => r[key]))));
}
function compilerRows(items, compilers) {
  return compilers.map(compiler => {
    const rows = items.filter(r => r.compiler === compiler);
    const complete = rows.length > 0 && rows.every(r => r.complete);
    const families = [...new Set(rows.map(r => r.family))];
    return {
      compiler, rows, complete, passed: rows.filter(r => r.complete).length,
      quality: groupedScore(rows, 'quality'), speed: groupedScore(rows, 'speed'),
      count: complete ? median(rows.map(r => r.count)) : null,
      depth: complete ? median(rows.map(r => r.depth)) : null,
      time: complete ? median(rows.map(r => r.time)) : null,
      familyScores: Object.fromEntries(families.map(f => [f, groupedScore(rows.filter(r => r.family === f), 'quality')])),
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
  return ['count', 'depth', 'one', 'total'].includes(key) ? String(v) : v.toFixed(key === 'time' ? 2 : 1);
}
function heading(key, caption = metrics[key].name) {
  const active = state.metric === key;
  return `<th class="num" scope="col"${active ? ' aria-sort="' + (metrics[key].higher ? 'descending' : 'ascending') + '"' : ''}><button data-sort="${key}" aria-label="Sort by ${esc(caption)}">${esc(caption)}${active ? ' ' + (metrics[key].higher ? '↓' : '↑') : ''}</button><small>${esc(metrics[key].unit)}</small></th>`;
}
function numberCell(row, key) {
  const samples = key === 'time' && row.rows ? row.rows.flatMap(r => r.timing_samples_ms ?? []) : [];
  const tooltip = samples.length ? `${samples.length} timing samples: ${Math.min(...samples).toFixed(2)} to ${Math.max(...samples).toFixed(2)} ms` : '';
  return `<td class="num${state.metric === key ? ' selected-metric' : ''}"${tooltip ? ' title="' + esc(tooltip) + '"' : ''}>${value(row[key], key)}</td>`;
}
function nameCell(compiler, detailed) {
  return `<span class="compiler-name"><i class="dot ${compiler}"></i>${label(compiler)}</span>${detailed ? '<span class="sub mono">' + esc(data.environment.versions[compiler]) + '</span>' : ''}`;
}
function renderLeaderboard(items, compilers) {
  const rows = compilerRows(items, compilers).sort(compare);
  const families = [...new Set(items.map(r => r.family))];
  const detailed = state.columns === 'on';
  $('result-head').innerHTML = `<tr><th scope="col">#</th><th scope="col">Compiler / configuration</th>${heading('quality')}${heading('speed')}${heading('count')}${heading('depth')}${heading('time')}${detailed ? families.map(f => '<th class="num" scope="col">' + esc(f) + '<small>quality</small></th>').join('') : ''}<th class="num" scope="col">Validated<small>circuits</small></th></tr>`;
  $('result-rows').innerHTML = rows.map(row => {
    const config = configurations[row.compiler] ?? row.compiler;
    const eligible = row[state.metric] !== null;
    const rank = eligible ? 1 + rows.filter(r => r[state.metric] !== null && (metrics[state.metric].higher ? r[state.metric] > row[state.metric] : r[state.metric] < row[state.metric])).length : 'N/A';
    return `<tr data-compiler="${row.compiler}"><td class="rank">${rank}</td><td>${nameCell(row.compiler, true)}<span class="sub">${esc(config)}</span></td>${['quality', 'speed', 'count', 'depth', 'time'].map(k => numberCell(row, k)).join('')}${detailed ? families.map(f => '<td class="num">' + value(row.familyScores[f], 'quality') + '</td>').join('') : ''}<td class="num ${row.complete ? 'valid' : ''}">${row.passed}/${row.rows.length}</td></tr>`;
  }).join('');
  $('view-note').innerHTML = 'Quality and Speed are exploratory, family-balanced scores relative to Qiskit = 100. Raw 2Q count, depth, and time columns are medians across selected circuits, not normalized scores. Missing required trials produce N/A. <a href="docs/pilot.html">Definitions ↗</a>';
}
function inputDetails(id) {
  const circuit = data.cases.find(c => c.id === id);
  const p = circuit.provenance;
  const source = p ? `<a href="${esc(p.url)}">${esc(p.corpus)} source ↗</a> · <a href="${esc(p.source_path)}">Original QASM</a> · <a href="${esc(p.license_path)}">License</a>` : 'Atlas-generated input';
  return `<details class="input-details"><summary>Input details</summary>${source}<div class="mono">${esc(JSON.stringify(circuit.parameters))}</div><div>${esc(p?.transformation ?? 'Qiskit level-0 lowering')}</div><div class="mono">SHA-256: ${esc(circuit.sha256)}</div></details>`;
}
function validationDetails(row) {
  if (row.complete) return '';
  return `<details class="input-details"><summary>Validation details</summary>${row.rows.map(r => `<div>Seed slot ${r.seed}: ${esc(r.status)}; ${esc((r.trials ?? []).map(t => t.validation.criterion).join(', '))}</div>`).join('')}</details>`;
}
function renderCircuits(items) {
  const detailed = state.columns === 'on';
  const scoreColumn = ['quality', 'speed'].includes(state.metric);
  $('result-head').innerHTML = `<tr><th scope="col">Circuit</th><th scope="col">Compiler</th>${scoreColumn ? heading(state.metric) : ''}${heading('count')}${heading('depth')}${heading('time')}${detailed ? '<th class="num" scope="col">1Q count</th><th class="num" scope="col">Total depth</th>' : ''}<th scope="col">Validation / artifact</th></tr>`;
  $('result-rows').innerHTML = [...items].sort(compare).map(row => {
    const artifact = row.rows[0]?.trials?.[0]?.artifact;
    return `<tr data-compiler="${row.compiler}"><td><strong class="mono">${esc(row.id)}</strong><span class="sub" style="margin-left:0">${esc(row.family)} · ${row.qubits} qubits</span>${inputDetails(row.id)}</td><td>${nameCell(row.compiler, detailed)}</td>${scoreColumn ? numberCell(row, state.metric) : ''}${['count', 'depth', 'time'].map(k => numberCell(row, k)).join('')}${detailed ? numberCell(row, 'one') + numberCell(row, 'total') : ''}<td><span class="${row.complete ? 'valid' : 'artifact'}">${row.complete ? 'QCEC passed' : 'Incomplete / unverified'}</span>${validationDetails(row)}${artifact ? ' · <a class="artifact" href="' + esc(artifact) + '">QASM ↗</a>' : ''}</td></tr>`;
  }).join('');
  $('view-note').textContent = 'Each value is the median across three seed slots; each slot has three timing repetitions. Hover over time for the nine-sample range. The QASM link opens the first output trial. Per-circuit scores use that circuit’s Qiskit reference.';
}
function renderMatrix(items, cases, compilers) {
  const metric = metrics[state.metric];
  $('result-head').innerHTML = `<tr><th scope="col">Circuit</th><th class="num" scope="col">Qubits</th>${compilers.map(c => '<th class="num" scope="col">' + label(c) + '<small>' + esc(metric.name) + ' · ' + esc(metric.unit) + '</small></th>').join('')}</tr>`;
  $('result-rows').innerHTML = cases.map(circuit => {
    const rows = compilers.map(c => items.find(r => r.id === circuit.id && r.compiler === c));
    const available = rows.map(r => r[state.metric]).filter(v => v !== null);
    const best = available.length ? (metric.higher ? Math.max(...available) : Math.min(...available)) : null;
    return `<tr><td class="mono">${esc(circuit.id)}</td><td class="num">${circuit.qubits}</td>${rows.map(r => '<td class="num' + (r[state.metric] !== null && r[state.metric] === best ? ' selected-metric' : '') + '">' + value(r[state.metric], state.metric) + (state.columns === 'on' ? '<span class="cell-sub">' + (r.complete ? 'QCEC passed' : 'Incomplete') + '</span>' : '') + '</td>').join('')}</tr>`;
  }).join('');
  $('view-note').textContent = `One row per circuit. Shading marks the best available value in each row, including ties. ${metric.name}: ${metric.higher ? 'higher' : 'lower'} is better. Scores are per-circuit comparisons, not suite-level scores.`;
}
function renderPlot(items) {
  const rows = items.filter(r => r.complete);
  if (!rows.length) { $('chart').textContent = 'No validated data to plot.'; return; }
  const width = Math.max(300, $('chart').clientWidth), mobile = width < 650;
  const height = mobile ? 300 : 350, left = 48, right = mobile ? 25 : 80, top = 32, bottom = 52;
  const times = rows.map(r => r.time), key = state.y;
  const lo = Math.floor(Math.log10(Math.max(Math.min(...times) * .7, .001)));
  const hi = Math.max(lo + 1, Math.ceil(Math.log10(Math.max(...times) * 1.3)));
  const ymax = Math.max(10, Math.ceil(Math.max(...rows.map(r => r[key])) / 20) * 20);
  const x = v => left + (Math.log10(Math.max(v, .001)) - lo) / (hi - lo) * (width - left - right);
  const y = v => height - bottom - v / ymax * (height - top - bottom);
  let svg = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="chart-title chart-desc"><title id="chart-title">${metrics[key].name} versus compile time</title><desc id="chart-desc">${esc(rows.map(r => `${r.id}, ${label(r.compiler)}, ${r[key]} ${metrics[key].unit}, ${r.time.toFixed(2)} ms`).join('; '))}</desc>`;
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
    const description = `${row.id} / ${label(row.compiler)}: ${row[key]} ${metrics[key].unit}, ${row.time.toFixed(2)} ms`;
    svg += `<circle class="${esc(row.compiler)}" cx="${px}" cy="${py}" r="4.5" fill="${colors[row.compiler]}" stroke="white" stroke-width="1.5" tabindex="0" aria-label="${esc(description)}"><title>${esc(description)}</title></circle>`;
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
    svg += `<text class="chart-label ${esc(row.compiler)}" x="${box.x}" y="${box.y + 10}" fill="${colors[row.compiler]}" font-size="10">${esc(row.id)}</text>`;
  }
  svg += `<text x="${left}" y="16" fill="#6e7887" font-size="11">${metrics[key].name}</text><text x="${(width + left - right) / 2}" y="${height - 6}" text-anchor="middle" fill="#6e7887" font-size="10">Compile time · ms (log scale)</text></svg>`;
  $('chart').innerHTML = svg;
  $('view-note').textContent = 'Each point is one compiler/circuit median, not a suite score. Only completed, validated entries are plotted. Detailed values and output artifacts are available in the Per circuit view.';
}
function render() {
  syncControls();
  saveHash();
  const cases = data.cases.filter(c => (state.family === 'all' || c.family === state.family) && (state.width === 'all' || String(c.qubits) === state.width));
  const compilers = compilerIds.filter(c => state.compiler === 'all' || c === state.compiler);
  const allItems = scoreCases(aggregate(cases));
  const items = allItems.filter(r => compilers.includes(r.compiler));
  const plot = state.view === 'tradeoff';
  $('table-container').hidden = plot || !cases.length;
  $('plot-container').hidden = !plot || !cases.length;
  $('empty').hidden = cases.length > 0;
  $('columns').disabled = plot;
  $('columns').closest('label').hidden = plot;
  $('metric').closest('.field').hidden = plot;
  document.querySelector('label[for="metric"]').textContent = state.view === 'matrix' ? 'Metric' : 'Metric / order';
  $('selection-status').textContent = `${cases.length} circuits · ${compilers.length} compilers · ${items.filter(r => r.complete).length}/${items.length} validated entries · ${state.target === 'line' ? 'Line' : 'All-to-all'}`;
  $('metric-direction').textContent = plot ? 'Both axes: lower is better' : `${metrics[state.metric].name}: ${metrics[state.metric].higher ? 'higher' : 'lower'} is better`;
  if (!cases.length) { $('result-head').innerHTML = ''; $('result-rows').innerHTML = ''; $('view-note').textContent = ''; return; }
  if (state.view === 'leaderboard') renderLeaderboard(allItems, compilers);
  if (state.view === 'circuits') renderCircuits(items);
  if (state.view === 'matrix') renderMatrix(allItems, cases, compilers);
  if (plot) renderPlot(items);
}
function reset() { Object.assign(state, defaults); render(); }
for (const key of ['target', 'width', 'compiler', 'metric']) $(key).addEventListener('change', () => { state[key] = $(key).value; render(); });
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
$('updated').textContent = 'Measured ' + data.created_at.slice(0, 10);
$('dataset-meta').textContent = `${data.cases.length} circuits · ${compilerIds.length} compilers · 2 topologies · ${accepted}/${trials.length} QCEC checks passed`;
$('footer-meta').textContent = `${data.suite} · rz / sx / x / cx · ${data.environment.python ? 'Python ' + data.environment.python : ''}`;
const env = data.environment;
const fields = [
  ['CPU', env.cpu], ['Affinity', env.cpu_affinity.join(', ')], ['OS', env.platform],
  ['Versions', Object.entries(env.versions).map(([k, v]) => k + ' ' + v).join(' · ')],
  ['Qiskit', data.protocol.qiskit_pipeline], ['pytket', data.protocol.pytket_pipeline.join(' → ')],
  ...(data.protocol.bqskit_pipeline ? [['BQSKit', JSON.stringify(data.protocol.bqskit_pipeline)]] : []),
  ['Validation', data.protocol.validation],
];
$('environment-fields').innerHTML = fields.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');
readHash(); render();
