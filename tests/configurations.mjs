import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { chromium } from 'playwright';

const raw = JSON.parse(fs.readFileSync('data/results.json', 'utf8'));
assert.equal(raw.protocol.configurations.length, 11);
assert.equal(raw.protocol.reference_configuration, 'qiskit-l2');
assert.equal(raw.results.length, raw.cases.length * 11 * 2 * raw.protocol.seeds.length);
assert.equal(new Set(raw.results.map(r => [r.case_id, r.target, r.configuration_id, r.seed].join(':'))).size, raw.results.length);
for (const r of raw.results) {
  const spec = raw.protocol.configurations.find(c => c.id === r.configuration_id);
  assert.equal(r.compiler, spec.compiler);
  assert.equal(r.seed_supported, spec.seed_supported);
  for (const t of r.trials ?? []) {
    assert.ok(t.artifact.includes(r.configuration_id));
    assert.ok(fs.existsSync(t.artifact));
  }
}
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  const url = pathToFileURL(path.resolve('index.html')).href;
  await page.goto(url);
  assert.equal(await page.locator('#result-rows tr').count(), 11);
  assert.equal(await page.locator('#suite-version').innerText(), 'Pilot v0.4');
  assert.match(await page.locator('#dataset-meta').innerText(), /3 SDKs · 11 configurations/);
  const ref = () => page.locator('#result-rows tr[data-compiler="qiskit-l2"] .score-value').first();
  assert.equal(await ref().innerText(), '100.0');
  const unavailable = page.locator('#result-rows tr[data-compiler="bqskit-l2"] td').nth(2);
  assert.equal(await unavailable.locator('.score-value').innerText(), 'N/A');
  await unavailable.locator('summary').focus();
  await page.keyboard.press('Enter');
  assert.match(await unavailable.innerText(), /qasmbench-ising_n10/);
  await page.keyboard.press('Enter');
  await page.locator('#environment summary').click();
  assert.match(await page.locator('#environment-fields').innerText(), /600 s per circuit/);
  assert.match(await page.locator('#environment-fields').innerText(), /42 initial 120 s timeouts/);
  await page.locator('#environment summary').click();
  for (const sdk of raw.protocol.compilers) {
    await page.selectOption('#compiler', sdk);
    const specs = raw.protocol.configurations.filter(c => c.compiler === sdk);
    assert.equal(await page.locator('#result-rows tr').count(), specs.length);
    assert.equal(await page.locator('#configuration option').count(), specs.length + 1);
    for (const spec of specs) {
      const row = page.locator(`#result-rows tr[data-compiler="${spec.id}"]`);
      assert.match(await row.innerText(), new RegExp(spec.label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
    }
  }
  await page.selectOption('#compiler', 'qiskit');
  await page.selectOption('#configuration', 'qiskit-l3');
  assert.equal(await page.locator('#result-rows tr').count(), 1);
  const score = await page.locator('.score-value').first().innerText();
  const permalink = await page.locator('#permalink').getAttribute('href');
  await page.goto(permalink);
  assert.equal(await page.locator('#compiler').inputValue(), 'qiskit');
  assert.equal(await page.locator('#configuration').inputValue(), 'qiskit-l3');
  assert.equal(await page.locator('.score-value').first().innerText(), score);
  await page.selectOption('#compiler', 'pytket');
  assert.equal(await page.locator('#configuration').inputValue(), 'all');
  assert.equal(await page.locator('#result-rows tr').count(), 3);
  await page.selectOption('#configuration', 'pytket-pauli');
  await page.getByRole('tab', { name: 'Per circuit', exact: true }).click();
  assert.equal(await page.locator('#result-rows tr').count(), raw.cases.length);
  assert.match(await page.locator('#result-rows').innerText(), /Pauli \+ peephole/);
  await page.uncheck('#columns');
  assert.match(await page.locator('#result-rows').innerText(), /Pauli \+ peephole/);
  await page.getByRole('tab', { name: 'Matrix', exact: true }).click();
  assert.equal(await page.locator('#result-head th').count(), 3);
  assert.match(await page.locator('#result-head').innerText(), /pytket · Pauli \+ peephole/i);
  await page.getByRole('tab', { name: 'Trade-off', exact: true }).click();
  assert.equal(await page.locator('#chart circle').count(), raw.cases.length);
  assert.match(await page.locator('#chart circle').first().getAttribute('aria-label'), /pytket · Pauli \+ peephole/);
  await page.goto(url + '#compiler=bqskit&configuration=qiskit-l3');
  assert.equal(await page.locator('#configuration').inputValue(), 'all');
  assert.equal(await page.locator('#result-rows tr').count(), 4);
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  assert.equal(await page.locator('#result-rows tr').count(), 11);
  await page.screenshot({ path: '/tmp/transpiler-atlas-configurations.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await page.screenshot({ path: '/tmp/transpiler-atlas-configurations-mobile.png', fullPage: true });
  assert.deepEqual(errors, []);
  console.log('Configuration checks passed: 11 measured entries, distinct artifacts, SDK/effort filtering, fixed reference, permalinks, all views, mobile.');
} finally { await browser.close(); }
