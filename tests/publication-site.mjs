import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { chromium } from 'playwright';
import { siteData } from './site-data.mjs';

const raw = siteData();
const config = JSON.parse(fs.readFileSync('publication.json'));
const mapping = JSON.parse(fs.readFileSync(config.file_map));
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', headless: true });
try {
  const page = await browser.newPage();
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  await page.goto(pathToFileURL(path.resolve('index.html')).href);
  const data = JSON.parse(await page.locator('#benchmark-data').textContent());
  assert.equal(data.campaign_id, config.campaign_id);
  assert.equal(data.results.length, raw.results.length);
  assert.equal(data.results.length, raw.cases.length * raw.protocol.configurations.length * 2 * raw.protocol.seeds.length);
  assert.equal(await page.locator('#result-rows tr').count(), raw.protocol.configurations.length);
  assert.equal(await page.getByRole('link', { name: 'Raw JSON', exact: true }).getAttribute('href'), mapping['data/results.json']);
  assert.equal(await page.getByRole('link', { name: 'v0.4 Raw JSON (reused source)', exact: true }).getAttribute('href'), 'data/results.json');
  for (const source of Object.values(raw.protocol.measurement_sources)) {
    assert.ok((await page.locator('#budget-note').innerText()).includes(`${source.kind === 'new' ? 'New' : 'Reused'} ${source.suite}:`));
  }
  if (raw.protocol.configuration_sources['cirq-routecqc-maponly-v1']) {
    assert.match(await page.locator('[data-compiler="cirq-routecqc-maponly-v1"] .budget-provenance').innerText(), /New Cirq measurement: 420 s/);
  }
  assert.match(await page.locator('#budget-note').innerText(), /This is not a matched-budget rerun/);
  assert.match(await page.locator('[data-compiler="qiskit-l2"] .budget-provenance').innerText(), /initial 120 s; timeout-only retries 600 s/);
  assert.match(await page.locator('[data-compiler="qmap-sc-heuristic-maponly-v1"] .budget-provenance').innerText(), /420 s/);
  assert.equal(raw.results.filter(r => r.compiler === 'qmap').length, raw.protocol.measurement_sources.qmap420.records);
  assert.deepEqual(errors, []);
  console.log(`Publication root: sealed ${raw.results.length} records, ${raw.protocol.configurations.length} configurations, source budgets, both raw links and no browser errors passed.`);
} finally { await browser.close(); }
