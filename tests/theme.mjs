import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { chromium } from 'playwright';

const root = process.cwd();
const raw = JSON.parse(fs.readFileSync(path.join(root, 'data/results.json'), 'utf8'));
const bqId = raw.protocol.configurations ? 'bqskit-l1' : 'bqskit';
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json' };
const server = http.createServer((request, response) => {
  const pathname = new URL(request.url, 'http://localhost').pathname;
  const file = path.resolve(root, '.' + (pathname === '/' ? '/index.html' : pathname));
  if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    response.writeHead(404).end(); return;
  }
  response.setHeader('Content-Type', mime[path.extname(file)] ?? 'text/plain');
  response.end(fs.readFileSync(file));
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', headless: true });
try {
  const context = await browser.newContext({ colorScheme: 'dark', viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(base);
  const resolved = async theme => assert.equal(await page.locator('html').getAttribute('data-theme'), theme);
  assert.equal(await page.locator('#theme').inputValue(), 'system');
  await resolved('dark');
  assert.equal(await page.locator(`#result-rows tr[data-compiler="${bqId}"] td`).nth(2).evaluate(n => getComputedStyle(n).backgroundColor), 'rgb(53, 42, 28)');
  assert.equal(await page.locator('a[href*="releases/"]').count(), 0);
  const tagContrast = async () => {
    const ratio = await page.locator('#results-table .approximation-tag').first().evaluate(n => {
      const luminance = color => {
        const rgb = color.match(/[\d.]+/g).slice(0, 3).map(Number).map(v => v / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
        return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
      };
      const style = getComputedStyle(n), a = luminance(style.color), b = luminance(style.backgroundColor);
      return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
    });
    assert.ok(ratio >= 4.5, `approx. contrast ${ratio}`);
    assert.equal(await page.locator('#approximation-note').isVisible(), true);
  };
  await tagContrast();
  const darkBg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  await page.screenshot({ path: '/tmp/transpiler-atlas-dark.png', fullPage: true });
  await page.selectOption('#theme', 'light');
  await resolved('light');
  assert.notEqual(await page.evaluate(() => getComputedStyle(document.body).backgroundColor), darkBg);
  await tagContrast();
  await page.emulateMedia({ colorScheme: 'dark' });
  await resolved('light');
  await page.reload();
  assert.equal(await page.locator('#theme').inputValue(), 'light');
  await resolved('light');
  await page.selectOption('#theme', 'dark');
  await page.emulateMedia({ colorScheme: 'light' });
  await resolved('dark');
  await page.getByRole('tab', { name: 'Trade-off', exact: true }).click();
  assert.ok(await page.locator('#chart circle').count() > 0);
  assert.equal(await page.locator('#chart circle.qiskit').first().evaluate(n => getComputedStyle(n).fill), 'rgb(128, 173, 255)');
  await page.screenshot({ path: '/tmp/transpiler-atlas-dark-plot.png', fullPage: true });
  await page.goto(base + '/docs/pilot.html');
  assert.equal(await page.locator('#theme').inputValue(), 'dark');
  await resolved('dark');
  assert.equal(await page.getByRole('link', { name: 'Design references', exact: true }).count(), 0);
  assert.equal(await page.locator('a[href*="releases/"]').count(), 0);
  await page.screenshot({ path: '/tmp/transpiler-atlas-dark-docs.png', fullPage: true });
  await page.selectOption('#theme', 'system');
  await resolved('light');
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.waitForFunction(() => document.documentElement.dataset.theme === 'dark');
  await resolved('dark');
  await page.goto(base);
  assert.equal(await page.locator('#theme').inputValue(), 'system');
  await resolved('dark');
  const other = await context.newPage();
  await other.goto(base);
  await page.selectOption('#theme', 'light');
  await other.waitForFunction(() => document.documentElement.dataset.theme === 'light');
  assert.equal(await other.locator('#theme').inputValue(), 'light');
  await other.close();
  await page.selectOption('#theme', 'dark');
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await page.screenshot({ path: '/tmp/transpiler-atlas-dark-mobile.png', fullPage: true });
  assert.deepEqual(errors, []);
  await context.close();

  // Storage can be unavailable for direct-file or privacy-restricted use.
  const blocked = await browser.newContext({ colorScheme: 'light' });
  await blocked.addInitScript(() => {
    Storage.prototype.getItem = () => { throw new Error('blocked'); };
    Storage.prototype.setItem = () => { throw new Error('blocked'); };
  });
  const restricted = await blocked.newPage();
  restricted.on('pageerror', error => errors.push(error.message));
  await restricted.goto(base);
  assert.equal(await restricted.locator('#theme').inputValue(), 'system');
  await restricted.selectOption('#theme', 'dark');
  assert.equal(await restricted.locator('html').getAttribute('data-theme'), 'dark');
  assert.deepEqual(errors, []);
  await blocked.close();
  console.log('Theme checks passed: light/dark/system, persistence, OS changes, cross-page/tab sync, chart, mobile, blocked storage.');
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}
