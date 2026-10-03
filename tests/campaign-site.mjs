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
assert.equal(raw.suite, 'pilot-v0.5-qmap-420s');
assert.equal(raw.results.length, 864);
assert.equal(raw.protocol.worker_timeout_seconds, 420);
assert.ok(raw.results.every(r => r.status === 'error' && r.error.startsWith('Synthetic')));
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
  await page.selectOption('#compiler', 'qmap');
  assert.equal(await page.locator('#result-rows tr').count(), 1);
  await page.locator('#environment summary').click();
  assert.match(await page.locator('#environment-fields').innerText(), /420 s/);
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
