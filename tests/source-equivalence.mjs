import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { chromium } from 'playwright';

// Run the actual app.js in both generated pages, not a replacement scoring model.
const root = process.env.COMBINED_SITE || execFileSync('.venv/bin/python', ['tests/make_campaign_site.py'], { encoding: 'utf8', env: { ...process.env, PYTHONPATH: '.' } }).trim().split('\n').at(-1);
const baseline = process.env.BASELINE_SITE || '/home/yasuhito/Work/transpiler-atlas';
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', headless: true });
const evidence = { baseline, combined: root, oldConfigurations: [], selections: 0, comparisons: [], qmap: [] };
try {
  const pages = await Promise.all([baseline, root].map(async dir => {
    const page = await browser.newPage();
    await page.goto(pathToFileURL(path.resolve(dir, 'index.html')).href);
    return page;
  }));
  const [before, after] = pages;
  const definitions = await before.evaluate(() => ({ ids: compilerIds, families: enums.family, widths: enums.width }));
  evidence.oldConfigurations = definitions.ids;
  assert.equal(definitions.ids.length, 11);
  for (const target of ['line', 'all-to-all']) {
    for (const family of definitions.families) for (const width of definitions.widths) {
      const selection = { target, family, width, ids: definitions.ids };
      const collect = page => page.evaluate(({ target, family, width, ids }) => {
        Object.assign(state, { target, family, width });
        const cases = data.cases.filter(c => (family === 'all' || c.family === family) && (width === 'all' || String(c.qubits) === width));
        if (!cases.length) return null;
        const items = scoreCases(aggregate(cases));
        const rows = compilerRows(items, ids);
        return { items: items.filter(r => ids.includes(r.compiler)), rows,
          values: rows.map(r => Object.fromEntries(['quality', 'speed', 'count', 'depth', 'time'].map(key => [key, value(r[key], key)]))),
          rankings: Object.fromEntries(['quality', 'speed', 'count', 'depth', 'time'].map(metric => {
            state.metric = metric; return [metric, [...rows].sort(compare).map(r => r.compiler)];
          })) };
      }, selection);
      const original = await collect(before), combined = await collect(after);
      assert.deepEqual(combined, original, JSON.stringify(selection));
      if (original) evidence.selections++;
    }
    const summaries = await after.evaluate(target => {
      Object.assign(state, { target, family: 'all', width: 'all' });
      return compilerRows(scoreCases(aggregate(data.cases)), compilerIds).map(({ compiler, quality, speed, count, depth, time, validationRate, passSlots, requiredSlots, familyScores }) => ({ compiler, quality, speed, count, depth, time, validationRate, passSlots, requiredSlots, familyScores }));
    }, target);
    evidence.comparisons.push({ target, summaries });
    evidence.qmap.push({ target, ...summaries.find(r => r.compiler === 'qmap-sc-heuristic-maponly-v1') });
  }
  assert.equal(await after.locator('#result-rows tr').count(), 12);
  const raw = JSON.parse(fs.readFileSync(path.join(root, 'data/results.json')));
  const oldRaw = JSON.parse(fs.readFileSync(path.join(baseline, 'data/results.json')));
  assert.deepEqual(raw.results.slice(0, 792), oldRaw.results);
  evidence.passed = true;
  evidence.scope = 'Actual browser app.js aggregate, scoreCases, compilerRows, value and compare across every nonempty target/family/width selection; old-only ranks, all raw records exact. Absolute ranks with QMAP may change.';
  if (process.env.EQUIVALENCE_OUTPUT) fs.writeFileSync(process.env.EQUIVALENCE_OUTPUT, JSON.stringify(evidence, null, 2) + '\n');
  console.log(`Source equivalence: 11 configurations, ${evidence.selections} selections, raw values, adjusted/raw scores, pass rates, N/A, formatting and old-only ranks identical.`);
} finally { await browser.close(); }
