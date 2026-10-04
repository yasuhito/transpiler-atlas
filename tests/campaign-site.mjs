import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { chromium } from 'playwright';

const root = execFileSync('.venv/bin/python', ['tests/make_campaign_site.py'], { encoding: 'utf8', env: { ...process.env, PYTHONPATH: '.' } }).trim().split('\n').at(-1);
assert.ok(path.resolve(root).startsWith(path.resolve('.checks/tmp') + path.sep));
const rawPath = path.join(root, 'data/results.json');
const before = fs.readFileSync(rawPath);
const raw = JSON.parse(before);
assert.equal(raw.suite, 'pilot-v0.5-qmap-mixed-budgets');
assert.equal(raw.results.length, 864);
assert.equal(raw.protocol.worker_timeout_seconds, undefined);
assert.equal(raw.protocol.measurement_sources.qmap420.protocol.worker_timeout_seconds, 420);
assert.equal(raw.protocol.measurement_sources['v0.4'].protocol.timeout_retry_entries, 42);
assert.ok(raw.results.slice(792).every(r => r.status === 'error' && r.error.startsWith('Synthetic')));
assert.deepEqual(raw.results.slice(0, 792), JSON.parse(fs.readFileSync('data/results.json')).results);
const notes = JSON.parse(fs.readFileSync(path.join(root, 'data/configuration-notes.json')));
assert.equal(notes.campaign_id, raw.campaign_id);
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', headless: true });
try {
  const page = await browser.newPage();
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto(pathToFileURL(path.resolve(root, 'index.html')).href);
  assert.equal(await page.locator('#result-rows tr').count(), 12);
  assert.match(await page.locator('#dataset-meta').innerText(), /4 SDKs · 12 configurations/);
  const row = page.locator('[data-compiler="qmap-sc-heuristic-maponly-v1"]');
  assert.match(await row.innerText(), /MQT QMAP/);
  assert.match(await row.innerText(), /3\.10\.0/);
  assert.equal(await row.locator('.approximation-tag').count(), 0);
  assert.match(await row.locator('.budget-provenance').innerText(), /New QMAP measurement: 420 s/);
  assert.match(await page.locator('[data-compiler="qiskit-l2"] .budget-provenance').innerText(), /initial 120 s; timeout-only retries 600 s/);
  assert.match(await page.locator('#budget-note').innerText(), /only 42 initial timeouts retried/);
  assert.match(await page.locator('#budget-note').innerText(), /not a matched-budget rerun/);
  await page.selectOption('#compiler', 'qmap');
  assert.equal(await page.locator('#result-rows tr').count(), 1);
  await page.locator('#environment summary').click();
  assert.match(await page.locator('#environment-fields').innerText(), /420 s/);
  assert.match(await page.locator('#environment-fields').innerText(), /750 initial outcomes retained/);
  const budgets = await page.evaluate(() => data.results.map(recordBudget));
  assert.equal(budgets.filter(x => x === 120).length, 750);
  assert.equal(budgets.filter(x => x === 600).length, 42);
  assert.equal(budgets.filter(x => x === 420).length, 72);
  assert.match(await page.locator('#environment-fields').innerText(), /Unseeded independent slots/);
  assert.match(await page.locator('#environment-fields').innerText(), /pre_mapping_optimizations/);
  const embedded = await page.locator('#benchmark-data').textContent();
  assert.equal(JSON.parse(embedded).campaign_id, raw.campaign_id);
  for (const theme of ['light', 'dark']) {
    await page.selectOption('#theme', theme);
    const color = await page.locator('.dot.qmap').first().evaluate(el => getComputedStyle(el).backgroundColor);
    assert.notEqual(color, 'rgba(0, 0, 0, 0)');
  }
  assert.deepEqual(errors, []);
  assert.deepEqual(fs.readFileSync(rawPath), before);
  console.log('Campaign site: QMAP/filter/version/recipe/budget/themes/raw preservation passed (synthetic unmeasured fixture).');
} finally {
  await browser.close();
}
