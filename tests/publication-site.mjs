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
  assert.equal(data.results.length, 864);
  assert.equal(await page.locator('#result-rows tr').count(), 12);
  assert.equal(await page.getByRole('link', { name: 'Raw JSON', exact: true }).getAttribute('href'), mapping['data/results.json']);
  assert.equal(await page.getByRole('link', { name: 'v0.4 Raw JSON (reused source)', exact: true }).getAttribute('href'), 'data/results.json');
  assert.match(await page.locator('#budget-note').innerText(), /QMAP alone newly measured at 420 s/);
  assert.match(await page.locator('#budget-note').innerText(), /This is not a matched-budget rerun/);
  assert.match(await page.locator('[data-compiler="qiskit-l2"] .budget-provenance').innerText(), /initial 120 s; timeout-only retries 600 s/);
  assert.match(await page.locator('[data-compiler="qmap-sc-heuristic-maponly-v1"] .budget-provenance').innerText(), /420 s/);
  assert.equal(raw.results.filter(r => r.compiler === 'qmap').length, 72);
  assert.deepEqual(errors, []);
  console.log('Publication root: sealed 864 records, QMAP row, mixed budgets, both raw links and no browser errors passed.');
} finally { await browser.close(); }
