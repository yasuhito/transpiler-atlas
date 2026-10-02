import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { chromium } from 'playwright';

const root = process.cwd();
const url = pathToFileURL(path.join(root, 'index.html')).href;
const raw = JSON.parse(fs.readFileSync(path.join(root, 'data/results.json'), 'utf8'));
const compilers = raw.protocol.compilers ?? ['qiskit', 'pytket'];
const nc = compilers.length;
const passRate = (target, family, width, compiler) => {
  const cases = raw.cases.filter(c => (family === 'all' || c.family === family) && (width === 'all' || String(c.qubits) === width));
  const rows = raw.results.filter(r => cases.some(c => c.id === r.case_id) && r.target === target && r.compiler === compiler);
  return rows.filter(r => r.status === 'passed' && r.trials?.length === raw.protocol.timing_repeats && r.trials.every(t => t.validation.accepted)).length / (cases.length * raw.protocol.seeds.length);
};
const plotted = (target, family = 'all', width = 'all') => raw.cases.filter(c => (family === 'all' || c.family === family) && (width === 'all' || String(c.qubits) === width)).reduce((n, c) => n + compilers.filter(compiler => raw.results.some(r => r.target === target && r.case_id === c.id && r.compiler === compiler && Number.isFinite(r.compile_ms) && Number.isFinite(r.metrics?.two_qubit_count))).length, 0);
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium',
  headless: true,
});
const errors = [];
const japanese = /[\u3040-\u30ff\u3400-\u9fff]/;
const median = values => {
  const xs = [...values].sort((a, b) => a - b);
  return xs.length % 2 ? xs[Math.floor(xs.length / 2)] : (xs[xs.length / 2 - 1] + xs[xs.length / 2]) / 2;
};
const gm = values => Math.exp(values.reduce((a, b) => a + Math.log(b), 0) / values.length);

function expectedQuality(target, family, width, compiler) {
  const cases = raw.cases.filter(c => (family === 'all' || c.family === family) && (width === 'all' || String(c.qubits) === width));
  const families = [...new Set(cases.map(c => c.family))];
  return 100 * gm(families.map(f => gm(cases.filter(c => c.family === f).map(c => {
    const rows = name => raw.results.filter(r => r.target === target && r.case_id === c.id && r.compiler === name);
    const count = name => median(rows(name).map(r => r.metrics.two_qubit_count));
    const depth = name => median(rows(name).map(r => r.metrics.two_qubit_depth));
    return Math.sqrt((count('qiskit') + 1) / (count(compiler) + 1) * (depth('qiskit') + 1) / (depth(compiler) + 1));
  })))) * passRate(target, family, width, compiler);
}

try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
  await page.goto(url);
  await page.waitForSelector('#result-rows tr');
  assert.equal(await page.locator('html').getAttribute('lang'), 'en');
  assert.equal(japanese.test(await page.locator('body').innerText()), false);
  assert.equal(await page.locator('h1').innerText(), 'Benchmark results');
  assert.equal(await page.locator('#result-rows tr').count(), nc);
  assert.equal(await page.locator('#table-container').evaluate(n => n.scrollWidth <= n.clientWidth), true, 'Desktop leaderboard must fit all columns');
  assert.match(await page.locator('#target-note').innerText(), /Atlas-designed synthetic target/);
  const trials = raw.results.flatMap(r => r.trials ?? []);
  const accepted = trials.filter(t => t.validation.accepted).length;
  assert.ok((await page.locator('#dataset-meta').innerText()).includes(`${accepted}/${trials.length}`));
  assert.equal(await page.getByRole('link', { name: 'Design references', exact: true }).count(), 0);
  assert.equal(await page.locator('a[href*="releases/"]').count(), 0);
  const qualityCell = compiler => page.locator(`#result-rows tr[data-compiler="${compiler}"] td`).nth(2).locator('.score-value');
  assert.equal(await qualityCell('qiskit').innerText(), '100.0');
  assert.equal(await qualityCell('pytket').innerText(), expectedQuality('line', 'all', 'all', 'pytket').toFixed(1));
  await page.screenshot({ path: '/tmp/transpiler-atlas-desktop.png', fullPage: true });

  for (const target of ['line', 'all-to-all']) {
    await page.selectOption('#target', target);
    assert.match(await page.locator('#target-note').innerText(), target === 'line' ? /neighboring qubits/ : /any pair/);
    for (const family of [...new Set(raw.cases.map(c => c.family))]) {
      const n = raw.cases.filter(c => c.family === family).length;
      await page.locator(`[data-family="${family}"]`).click();
      assert.equal(await qualityCell('qiskit').innerText(), '100.0');
      for (const compiler of compilers) {
        const expected = expectedQuality(target, family, 'all', compiler);
        assert.equal(await qualityCell(compiler).innerText(), expected.toFixed(1) + (passRate(target, family, 'all', compiler) < 1 ? '*' : ''));
      }
      assert.ok((await page.locator('#selection-status').innerText()).includes(`${n} circuits`));
      await page.getByRole('tab', { name: 'Per circuit', exact: true }).click();
      assert.equal(await page.locator('#result-rows tr').count(), n * nc);
      await page.getByRole('tab', { name: 'Matrix', exact: true }).click();
      assert.equal(await page.locator('#result-rows tr').count(), n);
      await page.getByRole('tab', { name: 'Trade-off', exact: true }).click();
      assert.equal(await page.locator('#chart circle').count(), plotted(target, family));
      await page.getByRole('tab', { name: 'Leaderboard', exact: true }).click();
    }
  }
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await page.selectOption('#metric', 'time');
  let times = await page.locator('#result-rows tr td').allTextContents();
  assert.ok(times.length > 0);
  assert.equal(await page.locator('th[aria-sort="ascending"]').count(), 1);
  const firstCompiler = await page.locator('#result-rows tr').first().getAttribute('data-compiler');
  const compilerTime = compiler => median(raw.cases.map(c => median(raw.results.filter(r => r.target === 'line' && r.case_id === c.id && r.compiler === compiler).map(r => r.compile_ms))));
  assert.equal(firstCompiler, compilerTime('qiskit') <= compilerTime('pytket') ? 'qiskit' : 'pytket');
  await page.getByRole('button', { name: 'Sort by Quality', exact: true }).click();
  assert.equal(await page.locator('#metric').inputValue(), 'quality');
  assert.equal(await page.locator('th[aria-sort="descending"]').count(), 1);
  const fullColumns = await page.locator('#result-head th').count();
  await page.uncheck('#columns');
  assert.equal(await page.locator('#result-head th').count(), fullColumns - new Set(raw.cases.map(c => c.family)).size);

  // Compiler filtering must not change the reference computation.
  await page.selectOption('#compiler', 'pytket');
  assert.equal(await page.locator('#result-rows tr').count(), 1);
  assert.equal(await qualityCell('pytket').innerText(), expectedQuality('line', 'all', 'all', 'pytket').toFixed(1));
  if (compilers.includes('bqskit')) {
    await page.selectOption('#compiler', 'bqskit');
    assert.equal(await page.locator('#result-rows tr').count(), 1);
    const expected = expectedQuality('line', 'all', 'all', 'bqskit');
    assert.equal(await qualityCell('bqskit').innerText(), expected.toFixed(1) + '*');
    const permalink = await page.locator('#permalink').getAttribute('href');
    await page.goto(permalink);
    assert.equal(await page.locator('#compiler').inputValue(), 'bqskit');
    await page.getByRole('tab', { name: 'Per circuit', exact: true }).click();
    const failed = page.locator('#result-rows tr').filter({ hasText: 'Strict check failed' }).first();
    await failed.getByText('Validation details', { exact: true }).click();
    assert.match(await failed.innerText(), /verification_failed/);
    assert.match(await failed.innerText(), /not_equivalent/);
  }
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await page.getByRole('tab', { name: 'Per circuit', exact: true }).click();
  await page.selectOption('#metric', 'time');
  assert.equal(await page.locator('#result-rows tr').count(), raw.cases.length * nc);
  times = await page.locator('#result-rows tr td:nth-child(5)').allTextContents();
  const validTimes = times.map(Number).filter(Number.isFinite);
  assert.deepEqual(validTimes, [...validTimes].sort((a, b) => a - b));
  await page.selectOption('#metric', 'count');
  const counts = await page.locator('#result-rows tr td:nth-child(3)').allTextContents();
  const validCounts = counts.map(Number).filter(Number.isFinite);
  assert.deepEqual(validCounts, [...validCounts].sort((a, b) => a - b));
  await page.screenshot({ path: '/tmp/transpiler-atlas-circuits.png', fullPage: true });
  const imported = page.locator('#result-rows tr').filter({ hasText: 'qasmbench-vqe_n4' }).first();
  await imported.locator('summary').click();
  assert.match(await imported.innerText(), /QASMBench source/);
  assert.match(await imported.innerText(), /SHA-256/);
  for (const href of await imported.locator('a[href]').evaluateAll(nodes => nodes.map(n => n.href))) {
    if (href.startsWith('file:')) assert.ok(fs.existsSync(fileURLToPath(new URL(href))), href);
  }
  const qasm = page.getByRole('link', { name: 'QASM ↗', exact: true }).first();
  assert.ok(fs.existsSync(fileURLToPath(new URL(await qasm.getAttribute('href'), page.url()))));

  await page.getByRole('tab', { name: 'Matrix', exact: true }).click();
  await page.selectOption('#metric', 'depth');
  assert.equal(await page.locator('#result-rows tr').count(), raw.cases.length);
  const expected = expectedQuality('line', 'all', 'all', 'pytket');
  assert.ok(expected > 0);
  await page.screenshot({ path: '/tmp/transpiler-atlas-matrix.png', fullPage: true });
  await page.getByRole('tab', { name: 'Trade-off', exact: true }).click();
  assert.equal(await page.locator('#chart circle').count(), plotted('line'));
  await page.selectOption('#plot-y', 'depth');
  assert.match(await page.locator('#chart').innerHTML(), /2Q depth versus compile time/);
  assert.equal(await page.evaluate(() => {
    const boxes = [...document.querySelectorAll('.chart-label')].map(n => n.getBoundingClientRect());
    return boxes.every((a, i) => boxes.slice(i + 1).every(b =>
      !(a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top)));
  }), true, 'Chart labels must not overlap');
  await page.screenshot({ path: '/tmp/transpiler-atlas-tradeoff.png', fullPage: true });

  // Permalinks preserve all filters and the view across reload, even on file://.
  await page.selectOption('#target', 'all-to-all');
  await page.locator('[data-family="QAOA"]').click();
  await page.selectOption('#width', '6');
  const permalink = await page.locator('#permalink').getAttribute('href');
  await page.goto(permalink);
  assert.equal(await page.locator('#target').inputValue(), 'all-to-all');
  assert.equal(await page.locator('#width').inputValue(), '6');
  assert.equal(await page.locator('#plot-y').inputValue(), 'depth');
  assert.equal(await page.getByRole('tab', { name: 'Trade-off', exact: true }).getAttribute('aria-selected'), 'true');
  assert.equal(await page.locator('#chart circle').count(), plotted('all-to-all', 'QAOA', '6'));

  // No data for QFT at 8 qubits: explicit empty state, no synthetic entries.
  await page.locator('[data-family="QFT"]').click();
  await page.selectOption('#width', '8');
  assert.equal(await page.locator('#empty').isVisible(), true);
  await page.getByRole('button', { name: 'Reset filters', exact: true }).click();
  assert.equal(await page.locator('#result-rows tr').count(), nc);
  await page.getByRole('tab', { name: 'Leaderboard', exact: true }).focus();
  await page.keyboard.press('ArrowRight');
  assert.equal(await page.getByRole('tab', { name: 'Per circuit', exact: true }).getAttribute('aria-selected'), 'true');
  await page.keyboard.press('End');
  assert.equal(await page.getByRole('tab', { name: 'Trade-off', exact: true }).getAttribute('aria-selected'), 'true');
  await page.keyboard.press('Home');

  const links = await page.locator('a[href]').evaluateAll(nodes => nodes.map(n => n.href));
  for (const href of links) {
    if (href.startsWith('file:')) assert.ok(fs.existsSync(fileURLToPath(new URL(href))), href);
  }
  await page.locator('#environment summary').click();
  assert.match(await page.locator('#environment-fields').innerText(), /pytket/);
  for (const name of ['pilot', 'methodology', 'research', 'design', 'corpora', 'bqskit']) {
    await page.goto(pathToFileURL(path.join(root, 'docs', name + '.html')).href);
    assert.equal(await page.locator('html').getAttribute('lang'), 'en');
    assert.equal(japanese.test(await page.locator('body').innerText()), false, name);
    const localLinks = await page.locator('a[href]').evaluateAll(nodes => nodes.map(n => n.href));
    for (const href of localLinks) if (href.startsWith('file:')) assert.ok(fs.existsSync(fileURLToPath(new URL(href))), href);
  }

  await page.goto(pathToFileURL(path.join(root, 'releases/pilot-v0.1/index.html')).href);
  assert.match(await page.locator('#dataset-meta').innerText(), /216\/216/);
  assert.equal(await page.locator('.badge').innerText(), 'Pilot v0.1');
  await page.getByRole('tab', { name: 'Per circuit', exact: true }).click();
  const archivedQasm = await page.getByRole('link', { name: 'QASM ↗', exact: true }).first().getAttribute('href');
  assert.ok(fs.existsSync(fileURLToPath(new URL(archivedQasm, page.url()))));

  await page.goto(pathToFileURL(path.join(root, 'releases/pilot-v0.2/index.html')).href);
  assert.match(await page.locator('#dataset-meta').innerText(), /432\/432/);
  assert.equal(await page.locator('.badge').innerText(), 'Pilot v0.2');
  const archiveLinks = await page.locator('a[href]').evaluateAll(nodes => nodes.map(n => n.href));
  for (const href of archiveLinks) if (href.startsWith('file:')) assert.ok(fs.existsSync(fileURLToPath(new URL(href))), href);

  await page.goto(url + '#family=Hamiltonian&width=10');
  assert.equal(await page.locator('#width').inputValue(), '10');
  assert.equal(await page.locator('[data-family="Hamiltonian"]').getAttribute('aria-pressed'), 'true');
  assert.equal(await qualityCell('qiskit').innerText(), '100.0');
  await page.goto(url);
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  await page.screenshot({ path: '/tmp/transpiler-atlas-mobile.png', fullPage: true });
  await page.getByRole('tab', { name: 'Trade-off', exact: true }).click();
  await page.locator('[data-family="QAOA"]').click();
  assert.equal(await page.locator('#chart circle').count(), plotted('line', 'QAOA'));
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  await page.screenshot({ path: '/tmp/transpiler-atlas-mobile-plot.png', fullPage: true });

  // An unchecked slot reduces the score; it is not silently dropped.
  await page.evaluate(() => {
    data.results.find(r => r.target === 'line' && r.family === 'QAOA' && r.compiler === 'pytket').status = 'timeout';
    state.view = 'leaderboard'; state.metric = 'quality'; render();
  });
  assert.equal(await qualityCell('pytket').innerText(), (expectedQuality('line', 'QAOA', 'all', 'pytket') * 8 / 9).toFixed(1) + '*');
  await page.getByRole('tab', { name: 'Per circuit', exact: true }).click();
  assert.match(await page.locator('#result-rows').innerText(), /Incomplete/);
  assert.deepEqual(errors, []);
  console.log('Browser checks passed: four views, filters, score calculations, sorting, columns, permalinks, English docs, keyboard controls, mobile, incomplete data.');
} finally {
  await browser.close();
}
