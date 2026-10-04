import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { chromium } from 'playwright';

const root = execFileSync('.venv/bin/python', ['tests/make_retention_site.py'], { encoding: 'utf8', env: { ...process.env, PYTHONPATH: '.' } }).trim().split('\n').at(-1);
assert.ok(path.resolve(root).startsWith('/tmp/ta-hardto/test-sites/'));
const rawPath = path.join(root, 'data/results.json');
const before = fs.readFileSync(rawPath);
const raw = JSON.parse(before);
assert.equal(raw.schema_version, 3);
assert.equal(raw.kind, 'compile-retention');
assert.equal(raw.results.length, 2);
assert.ok(raw.results.every(r => r.status === 'passed'));
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', headless: true });
try {
  const page = await browser.newPage();
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto(pathToFileURL(path.resolve(root, 'index.html')).href);
  assert.match(await page.locator('#score-version').innerText(), /qcec-adjusted-partial-v2/);
  assert.match(await page.locator('#budget-note').innerText(), /min\(60 s, remaining job time\)/);
  assert.match(await page.locator('#dataset-meta').innerText(), /6\/6 QCEC checks passed/);
  assert.match(await page.locator('#dataset-meta').innerText(), /1 topology/);
  assert.equal(await page.locator('#target option').count(), 1);
  assert.equal(await page.evaluate(() => { const saved = state.target; state.target = 'all-to-all'; const count = aggregate(data.cases).length; state.target = saved; return count; }), 0);
  // Controlled in-browser synthetic mutations test unfinished/partial states.
  // The real sealed raw and on-disk control evidence remain unchanged.
  await page.evaluate(() => {
    const row = data.results.find(r => r.configuration_id === 'qiskit-l1');
    row.status = 'verification_incomplete'; row.coverage.accepted_repeats = 0;
    for (const trial of row.trials) {
      trial.validation = { accepted: false, criterion: 'no_information' };
      trial.verification = { state: 'verification_incomplete', reason: 'nonconclusive_criterion', wall_seconds: 20, effective_budget_seconds: 60 };
    }
    render();
  });
  const scores = await page.evaluate(() => scoreCases(aggregate(data.cases)).find(r => r.compiler === 'qiskit-l1'));
  assert.equal(scores.quality, 0); assert.equal(scores.speed, 0);
  assert.equal(scores.passSlots, 0); assert.equal(scores.requiredSlots, 1);
  assert.ok(Number.isFinite(scores.rawQuality) && Number.isFinite(scores.rawSpeed));
  await page.locator('#tab-circuits').click();
  const row = page.locator('[data-compiler="qiskit-l1"]');
  assert.match(await row.innerText(), /Saved output rules met/);
  assert.match(await row.innerText(), /Verification incomplete/);
  assert.doesNotMatch(await row.innerText(), /Strict check failed/);
  await row.locator('summary').filter({ hasText: 'Validation details' }).click();
  assert.match(await row.innerText(), /compiled 3\/3 repeats/);
  assert.match(await row.innerText(), /no_information/);
  assert.match(await row.innerText(), /20\.000 s \/ 60\.000 s cap/);
  for (const name of ['Native QPY', 'Compile manifest']) {
    const link = row.getByRole('link', { name, exact: true }).first();
    const href = await link.getAttribute('href');
    assert.ok(fs.existsSync(path.join(root, href)), href);
  }
  await page.evaluate(() => {
    const row = data.results.find(r => r.configuration_id === 'qiskit-l1');
    row.status = 'compile_incomplete'; row.trials.splice(1);
    row.coverage.compiled = 1;
    row.metrics = row.trials[0].metrics; row.compile_ms = row.trials[0].compile_ms;
    row.timing_samples_ms = [row.compile_ms];
    row.trials[0].verification.reason = 'hard_timeout';
    row.trials[0].validation.criterion = null;
    render();
  });
  assert.match(await row.innerText(), /Compiled 1\/3 repeats/);
  assert.match(await row.innerText(), /Compilation incomplete/);
  await page.evaluate(() => {
    const index = compilerIds.indexOf('qiskit-l2');
    compilerIds.splice(index, 1);
    specs.splice(specs.findIndex(c => c.id === 'qiskit-l2'), 1);
    data.results = data.results.filter(r => r.configuration_id !== 'qiskit-l2');
    render();
  });
  const missingReference = await page.evaluate(() => scoreCases(aggregate(data.cases))[0]);
  assert.equal(missingReference.quality, null); assert.equal(missingReference.speed, null);
  assert.ok(Number.isFinite(missingReference.count) && Number.isFinite(missingReference.time));
  assert.match(await row.innerText(), /N\/A/);
  // A required missing circuit must propagate N/A into aggregate scores.
  await page.evaluate(() => {
    data.cases.push({ ...data.cases[0], id: 'synthetic-missing' });
    data.protocol.ordered_schedule.push({ case_id: 'synthetic-missing', configuration_id: 'qiskit-l1', target: 'line', seed: 7 });
    render();
  });
  const aggregateScores = await page.evaluate(() => compilerRows(scoreCases(aggregate(data.cases)), compilerIds)[0]);
  assert.equal(aggregateScores.quality, null); assert.equal(aggregateScores.speed, null);
  assert.equal(aggregateScores.requiredSlots, 2);
  await page.locator('#environment summary').click();
  assert.doesNotMatch(await page.locator('#environment-fields').innerText(), /undefined/);
  for (const theme of ['light', 'dark']) {
    await page.selectOption('#theme', theme);
    await page.screenshot({ path: path.join(path.dirname(root), `retention-${theme}.png`), fullPage: true });
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: path.join(path.dirname(root), 'retention-mobile.png'), fullPage: true });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  assert.deepEqual(errors, []);
  assert.deepEqual(fs.readFileSync(rawPath), before);
  console.log('Retention site: real controls; synthetic unfinished/partial labels, raw/ref 0 vs N/A, planned denominator, artifact links, themes/mobile, sealed bytes unchanged.');
} finally { await browser.close(); }
