import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { chromium } from 'playwright';

const raw = JSON.parse(fs.readFileSync('data/results.json', 'utf8'));
const median = xs => {
  const values = xs.filter(Number.isFinite).sort((a, b) => a - b);
  if (!values.length) return null;
  const m = Math.floor(values.length / 2);
  return values.length % 2 ? values[m] : (values[m - 1] + values[m]) / 2;
};
const formatted = (v, key) => v.toFixed(key === 'speed' && v > 0 && v < 1 ? 3 : 1);
const gm = xs => Math.exp(xs.reduce((sum, x) => sum + Math.log(x), 0) / xs.length);
const passed = r => r.status === 'passed' && r.trials?.length === raw.protocol.timing_repeats && r.trials.every(t => t.validation.accepted);
function expected(target, family, compiler, key) {
  const cases = raw.cases.filter(c => family === 'all' || c.family === family);
  const caseBase = c => {
    const rows = name => raw.results.filter(r => r.case_id === c.id && r.target === target && r.compiler === name);
    const count = name => median(rows(name).map(r => r.metrics?.two_qubit_count));
    const depth = name => median(rows(name).map(r => r.metrics?.two_qubit_depth));
    const time = name => median(rows(name).map(r => r.compile_ms));
    return key === 'quality' ? 100 * Math.sqrt((count('qiskit') + 1) / (count(compiler) + 1) * (depth('qiskit') + 1) / (depth(compiler) + 1))
      : 100 * Math.max(time('qiskit'), 1) / Math.max(time(compiler), 1);
  };
  const families = [...new Set(cases.map(c => c.family))];
  const base = gm(families.map(f => gm(cases.filter(c => c.family === f).map(caseBase))));
  const rows = raw.results.filter(r => cases.some(c => c.id === r.case_id) && r.target === target && r.compiler === compiler);
  const accepted = rows.filter(passed).length;
  const required = cases.length * raw.protocol.seeds.length;
  return { base, accepted, required, rate: accepted / required, score: base * accepted / required };
}
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  const url = pathToFileURL(path.resolve('index.html')).href;
  await page.goto(url);
  const cell = (compiler, key) => page.locator(`#result-rows tr[data-compiler="${compiler}"] td`).nth(key === 'quality' ? 2 : 3);
  const initial = expected('line', 'all', 'bqskit', 'quality');
  assert.equal(await cell('bqskit', 'quality').locator('.score-value').innerText(), initial.score.toFixed(1) + '*');
  assert.match(await cell('bqskit', 'quality').getAttribute('title'), /QCEC passed 19\/36/);
  assert.ok((await cell('bqskit', 'quality').getAttribute('class')).includes('penalized-score'));
  assert.equal(await cell('bqskit', 'quality').evaluate(n => getComputedStyle(n).backgroundColor), 'rgb(255, 245, 229)');
  assert.match(await page.locator('#selection-status').innerText(), /QCEC 91\/108 seed slots passed/);
  assert.equal(await page.locator('#score-version').innerText(), 'Scores: qcec-adjusted-v1');
  assert.equal(await page.evaluate(() => data.score_version), 'qcec-adjusted-v1');

  for (const target of ['line', 'all-to-all']) {
    await page.selectOption('#target', target);
    for (const family of ['all', ...new Set(raw.cases.map(c => c.family))]) {
      await page.locator(`[data-family="${family}"]`).click();
      for (const compiler of raw.protocol.compilers) {
        for (const key of ['quality', 'speed']) {
          const e = expected(target, family, compiler, key);
          const marked = e.rate < 1;
          assert.equal(await cell(compiler, key).locator('.score-value').innerText(), formatted(e.score, key) + (marked ? '*' : ''));
          assert.equal(await cell(compiler, key).evaluate(n => n.classList.contains('penalized-score')), marked);
          assert.ok((await cell(compiler, key).getAttribute('title')).includes(`QCEC passed ${e.accepted}/${e.required}`));
        }
      }
    }
  }
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await page.locator('[data-family="QFT"]').click();
  const qft = expected('line', 'QFT', 'bqskit', 'quality');
  assert.equal(qft.accepted, 4);
  assert.equal(qft.required, 9);
  assert.equal(await cell('bqskit', 'quality').locator('.score-value').innerText(), qft.score.toFixed(1) + '*');
  const familyCell = page.locator('#result-rows tr[data-compiler="bqskit"] td').nth(7);
  assert.equal(await familyCell.locator('.score-value').innerText(), qft.score.toFixed(1) + '*');
  await familyCell.locator('.score-breakdown summary').click();
  assert.match(await familyCell.innerText(), /Before penalty/);
  assert.match(await familyCell.innerText(), /QCEC passed 4\/9/);
  await page.screenshot({ path: '/tmp/transpiler-atlas-adjusted-scores.png', fullPage: true });

  // Filtering compilers must retain the measured Qiskit reference.
  await page.selectOption('#compiler', 'bqskit');
  assert.equal(await cell('bqskit', 'quality').locator('.score-value').innerText(), qft.score.toFixed(1) + '*');
  await page.getByRole('tab', { name: 'Matrix', exact: true }).click();
  const qftRow = () => page.locator('#result-rows tr').filter({ hasText: 'qft-4q' });
  assert.match(await qftRow().locator('td').last().innerText(), /^\d+\.\d\*/);
  assert.equal(await qftRow().locator('td.penalized-score').count(), 1);
  await page.uncheck('#columns');
  assert.match(await qftRow().innerText(), /Unverified/);

  // All recorded outputs rejected: measured score is zero, not N/A or Not scored.
  await page.evaluate(() => {
    window.savedResults = JSON.parse(JSON.stringify(data.results));
    for (const r of data.results.filter(r => r.target === 'line' && r.case_id === 'qft-4q' && r.compiler === 'bqskit')) {
      r.status = 'verification_failed'; r.trials.forEach(t => { t.validation.accepted = false; });
    }
    state.view = 'circuits'; render();
  });
  assert.equal(await qftRow().locator('td').nth(2).locator('.score-value').innerText(), '0.0*');
  await page.selectOption('#metric', 'speed');
  assert.equal(await qftRow().locator('td').nth(2).locator('.score-value').innerText(), '0.0*');

  // A missing required slot stays in the penalty denominator.
  await page.evaluate(() => {
    data.results = JSON.parse(JSON.stringify(window.savedResults));
    data.results = data.results.filter(r => !(r.target === 'line' && r.case_id === 'qft-4q' && r.compiler === 'bqskit' && r.seed === 43));
    state.metric = 'quality'; render();
  });
  assert.equal(await qftRow().locator('td').nth(2).locator('.score-value').innerText(), '0.0*');
  assert.match(await qftRow().locator('td').nth(2).getAttribute('title'), /QCEC passed 0\/3/);

  // A status label alone is insufficient if one of its output checks failed.
  await page.evaluate(() => {
    data.results = JSON.parse(JSON.stringify(window.savedResults));
    const r = data.results.find(r => r.target === 'line' && r.case_id === 'qft-4q' && r.compiler === 'bqskit' && r.seed === 43);
    r.trials[0].validation.accepted = false;
    render();
  });
  assert.equal(await qftRow().locator('td').nth(2).locator('.score-value').innerText(), '0.0*');

  // Duplicate evidence must not increase pass rates or exceed the scheduled denominator.
  await page.evaluate(() => {
    data.results = JSON.parse(JSON.stringify(window.savedResults));
    const r = data.results.find(r => r.target === 'line' && r.case_id === 'qft-4q' && r.compiler === 'bqskit' && r.seed === 43);
    data.results.push(JSON.parse(JSON.stringify(r)));
    render();
  });
  assert.equal(await qftRow().locator('td').nth(2).locator('.score-value').innerText(), '0.0*');
  assert.match(await qftRow().locator('td').nth(2).getAttribute('title'), /QCEC passed 0\/3/);

  // No required raw metric or reference: do not invent a score or silently drop cases.
  await page.evaluate(() => {
    data.results = JSON.parse(JSON.stringify(window.savedResults));
    for (const r of data.results.filter(r => r.target === 'line' && r.case_id === 'qft-4q' && r.compiler === 'qiskit')) delete r.metrics;
    render();
  });
  assert.equal(await qftRow().locator('td').nth(2).locator('.score-value').innerText(), 'N/A');
  await page.getByRole('tab', { name: 'Leaderboard', exact: true }).click();
  assert.equal(await cell('bqskit', 'quality').locator('.score-value').innerText(), 'N/A');
  assert.deepEqual(errors, []);
  console.log('Adjusted scoring checks passed: independent formulas for all families/targets/compilers, Quality/Speed, asterisks, breakdown, matrix, zero/missing/reference cases.');
} finally { await browser.close(); }
