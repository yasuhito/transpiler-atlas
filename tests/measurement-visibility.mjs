import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { chromium } from 'playwright';

const raw = JSON.parse(fs.readFileSync('data/results.json', 'utf8'));
const url = pathToFileURL(path.resolve('index.html')).href;
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', headless: true });
const median = values => {
  const xs = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (!xs.length) return null;
  const n = Math.floor(xs.length / 2);
  return xs.length % 2 ? xs[n] : (xs[n - 1] + xs[n]) / 2;
};
const samples = raw.results.filter(r => r.target === 'line' && r.compiler === 'bqskit' && r.case_id === 'qft-4q');
const expected = rows => [median(rows.map(r => r.metrics?.two_qubit_count)), median(rows.map(r => r.metrics?.two_qubit_depth)), median(rows.map(r => r.compile_ms))];
const displayed = values => values.map((v, i) => v === null ? 'N/A' : i === 2 ? v.toFixed(2) : String(v));
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  await page.goto(url + '#view=circuits&family=QFT&width=4&compiler=bqskit&metric=count');
  const row = () => page.locator('#result-rows tr').filter({ hasText: 'qft-4q' });
  const cells = () => row().locator('td');
  // The reported issue: genuine measurements disappeared when strict checks failed.
  assert.equal(await cells().nth(2).innerText(), displayed(expected(samples))[0]);
  assert.equal(await cells().nth(3).innerText(), displayed(expected(samples))[1]);
  assert.equal(await cells().nth(4).innerText(), displayed(expected(samples))[2]);
  assert.match(await row().innerText(), /Output rules met/);
  assert.match(await row().innerText(), /Measured 3\/3/);
  assert.match(await row().innerText(), /Strict check failed/);
  assert.match(await row().innerText(), /QCEC 1\/3/);
  await page.selectOption('#metric', 'quality');
  assert.equal(await cells().nth(2).innerText(), 'Not scored');
  assert.equal(await cells().nth(3).innerText(), displayed(expected(samples))[0]);
  await page.uncheck('#columns');
  assert.match(await row().innerText(), /Strict check failed/);
  await page.screenshot({ path: '/tmp/transpiler-atlas-qft-raw.png', fullPage: true });

  await page.getByRole('tab', { name: 'Leaderboard', exact: true }).click();
  const leader = () => page.locator('#result-rows tr[data-compiler="bqskit"]');
  assert.equal(await leader().locator('td').nth(2).innerText(), 'Not scored');
  for (const i of [4, 5, 6]) assert.notEqual(await leader().locator('td').nth(i).innerText(), 'N/A');
  assert.match(await leader().innerText(), /Unverified measurements/);
  await page.selectOption('#metric', 'count');
  assert.equal(await leader().locator('td').first().innerText(), 'Not ranked');

  await page.getByRole('tab', { name: 'Matrix', exact: true }).click();
  const matrix = () => page.locator('#result-rows tr').filter({ hasText: 'qft-4q' });
  assert.ok((await matrix().locator('td').nth(2).innerText()).startsWith(displayed(expected(samples))[0]));
  assert.match(await matrix().innerText(), /Unverified/);
  assert.equal(await matrix().locator('td.selected-metric').count(), 0);

  await page.getByRole('tab', { name: 'Trade-off', exact: true }).click();
  const point = () => page.locator('#chart circle[data-case-id="qft-4q"][data-compiler="bqskit"]');
  assert.equal(await point().count(), 1);
  assert.equal(await point().getAttribute('data-verified'), 'false');
  assert.ok((await point().getAttribute('class')).includes('unverified'));
  assert.match(await point().getAttribute('aria-label'), /Strict check failed/);
  await page.screenshot({ path: '/tmp/transpiler-atlas-qft-raw-plot.png', fullPage: true });

  // A genuine missing worker result must not discard other measured seed slots.
  await page.evaluate(() => {
    window.savedResults = JSON.parse(JSON.stringify(data.results));
    const row = data.results.find(r => r.target === 'line' && r.compiler === 'bqskit' && r.case_id === 'qft-4q' && r.seed === 7);
    for (const key of ['metrics', 'compile_ms', 'timing_samples_ms', 'trials']) delete row[key];
    row.status = 'timeout';
    state.view = 'circuits'; state.metric = 'count'; render();
  });
  const partial = samples.filter(r => r.seed !== 7);
  for (const [i, value] of displayed(expected(partial)).entries()) assert.equal(await cells().nth(i + 2).innerText(), value);
  assert.match(await row().innerText(), /Measured 2\/3/);
  assert.match(await row().innerText(), /Partial measurements/);
  assert.match(await row().innerText(), /Output rules not fully checked/);
  await page.selectOption('#metric', 'quality');
  assert.equal(await cells().nth(2).innerText(), 'Not scored');

  // Raw measurement availability must not grant a verified rank or best-cell shading.
  await page.evaluate(() => {
    data.results = JSON.parse(JSON.stringify(window.savedResults));
    for (const r of data.results.filter(r => r.target === 'line' && r.case_id === 'qft-4q' && r.compiler === 'bqskit')) {
      r.metrics.two_qubit_count = 0;
    }
    state.compiler = 'all'; state.metric = 'count'; state.view = 'matrix'; render();
  });
  const bqCell = matrix().locator('td').last();
  assert.ok((await bqCell.innerText()).startsWith('0'));
  assert.equal(await bqCell.evaluate(n => n.classList.contains('selected-metric')), false);
  await page.getByRole('tab', { name: 'Leaderboard', exact: true }).click();
  assert.equal(await leader().locator('td').first().innerText(), 'Not ranked');
  assert.equal(await page.locator('#result-rows tr[data-compiler="qiskit"] td').first().innerText(), '1');

  // If no numbers were recorded, N/A is appropriate and no point is invented.
  await page.evaluate(() => {
    data.results = JSON.parse(JSON.stringify(window.savedResults));
    for (const r of data.results.filter(r => r.target === 'line' && r.case_id === 'qft-4q' && r.compiler === 'bqskit')) {
      for (const key of ['metrics', 'compile_ms', 'timing_samples_ms', 'trials']) delete r[key];
      r.status = 'error';
    }
    state.compiler = 'bqskit'; state.view = 'circuits'; state.metric = 'count'; render();
  });
  for (const i of [2, 3, 4]) assert.equal(await cells().nth(i).innerText(), 'N/A');
  assert.match(await row().innerText(), /Measured 0\/3/);
  await page.getByRole('tab', { name: 'Trade-off', exact: true }).click();
  assert.equal(await point().count(), 0);
  await page.evaluate(() => {
    for (const r of data.results.filter(r => r.target === 'line' && r.family === 'QFT' && r.qubits === 4 && r.compiler === 'bqskit')) {
      for (const key of ['metrics', 'compile_ms', 'timing_samples_ms', 'trials']) delete r[key];
      r.status = 'error';
    }
    render();
  });
  assert.equal(await page.locator('#chart').innerText(), 'No measurements to plot.');
  assert.match(await page.locator('#view-note').innerText(), /No measurement means no point/);
  assert.deepEqual(errors, []);
  console.log('Measurement visibility checks passed: real QFT, all four views, strict-score exclusion, partial/missing data, verified-only ranks/shading.');
} finally { await browser.close(); }
