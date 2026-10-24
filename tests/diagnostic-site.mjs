import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { chromium } from 'playwright';

const root = process.cwd();
const selectors = fs.readdirSync('diagnostics').sort().map(name => `diagnostics/${name}/report.json`).filter(name => fs.existsSync(name));
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  const failed = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('requestfailed', request => failed.push(request.url()));
  fs.mkdirSync('.checks/tmp/diagnostics', { recursive: true });
  const labels = [];
  for (const selector of selectors) {
    const diagnostic = path.resolve(path.dirname(selector), 'index.html');
    const config = JSON.parse(fs.readFileSync(selector));
    const mapping = JSON.parse(fs.readFileSync(config.file_map));
    const raw = JSON.parse(fs.readFileSync(mapping['data/results.json']));
    const version = Object.entries(raw.environment.versions).find(([key]) => key.replaceAll('-', '.').replaceAll('_', '.') === 'mqt.qcec')[1];
    const label = `Compile retention diagnostic (QCEC ${version})`;
    labels.push({ label, diagnostic });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(pathToFileURL(diagnostic).href);
    assert.equal(await page.locator('h1').textContent(), label);
    assert.equal(await page.locator('#diagnostic-identity-rows tr').count(), 18);
    assert.equal(await page.locator('#diagnostic-identity-rows .status').count(), 18);
    assert.equal(await page.getByRole('navigation', { name: 'Campaign comparison' }).getByRole('link').count(), selectors.length);
    for (let i = 0; i < raw.results.length; i++) {
      const row = raw.results[i];
      const cells = await page.locator(`#diagnostic-identity-rows tr[data-identity="${i}"] td`).allTextContents();
      assert.ok(cells[0].includes(row.case_id));
      assert.equal(cells[1], row.target);
      assert.equal(cells[2], `${row.configuration_id} / ${row.seed}`);
      assert.equal(cells[3], row.status);
      assert.equal(cells[4], `${row.coverage.compiled}/3 saved; ${row.coverage.accepted_repeats}/3 accepted`);
      assert.equal(cells[5], `${row.metrics.two_qubit_count} / ${row.metrics.two_qubit_depth}`);
      assert.equal(cells[6], `${row.metrics.one_qubit_count} / ${row.metrics.total_depth}`);
    }
    await page.locator('details').evaluateAll(nodes => nodes.forEach(node => node.open = true));
    const committed = raw.results.reduce((sum, row) => sum + row.coverage.compiled, 0);
    assert.equal(await page.getByRole('link', { name: 'QASM', exact: true }).count(), committed);
    assert.equal(await page.getByRole('link', { name: 'Native QPY', exact: true }).count(), committed);
    const links = await page.locator('a[href],link[href],script[src]').evaluateAll(nodes => nodes.map(node => ({ relative: node.getAttribute('href') ?? node.getAttribute('src'), resolved: node.href ?? node.src })));
    for (const link of links) {
      assert.ok(!link.relative.startsWith('/'), `Must work under a project subpath: ${link.relative}`);
      const target = fileURLToPath(link.resolved);
      assert.ok(target.startsWith(root + path.sep), `Escaping link: ${link.relative}`);
      assert.ok(fs.statSync(target).isFile(), `Missing link: ${link.relative}`);
    }
    await page.locator('details').evaluateAll(nodes => nodes.forEach(node => node.open = false));
    const slug = path.basename(path.dirname(selector));
    await page.selectOption('#theme', 'light');
    await page.screenshot({ path: `.checks/tmp/diagnostics/${slug}-light.png`, fullPage: true });
    await page.selectOption('#theme', 'dark');
    assert.equal(await page.locator('html').getAttribute('data-theme'), 'dark');
    await page.screenshot({ path: `.checks/tmp/diagnostics/${slug}-dark.png`, fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Mobile page must not overflow beyond the table scroller');
    await page.screenshot({ path: `.checks/tmp/diagnostics/${slug}-mobile.png`, fullPage: true });
    await page.selectOption('#theme', 'light');
    console.log(`${label}: 18 identities, ${committed} QASM/QPY links, ${links.length} relative targets, themes/mobile.`);
  }
  for (const { label, diagnostic } of labels) {
    await page.goto(pathToFileURL(path.resolve('docs/retention.html')).href);
    assert.equal(await page.getByRole('link', { name: label, exact: true }).count(), 1);
    await page.getByRole('link', { name: label, exact: true }).click();
    assert.equal(new URL(page.url()).pathname, new URL(pathToFileURL(diagnostic)).pathname);
  }
  assert.deepEqual(errors, []);
  assert.deepEqual(failed, []);
  console.log('Diagnostic campaign comparison, docs roundtrip, page errors 0.');
} finally { await browser.close(); }
