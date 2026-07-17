// Agent-driven E2E (done-condition item 7). Drives the BUILT widget on the
// mock dev server through a real Chromium, walking the entry surface -> a
// free-text message -> stepper chips -> a delivered file card, asserting the
// rendered blocks. This is the reproducible form of the agent-run acceptance
// check the proposal calls for (Playwright MCP / /browse); it is intentionally
// NOT a widget dependency — run it on demand (see e2e/README.md).
//
//   Terminal A:  npm --prefix widget run dev:mock
//   Terminal B:  node widget/e2e/drive.mjs
//
// Requires playwright-core resolvable on NODE_PATH (npm i -g playwright-core,
// or run from a dir that has it). Chromium is discovered from
// PLAYWRIGHT_CHROMIUM_EXECUTABLE or the ms-playwright cache. --no-sandbox is
// passed because CI/container kernels often block unprivileged user namespaces.
import { existsSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { homedir } from 'node:os';
import { createRequire } from 'node:module';

const BASE = process.env.WIDGET_URL ?? 'http://localhost:5178';
const URL = `${BASE}/?userId=X008593&page=support&platform=web&isDarkTheme=false`;

function findChromium() {
  if (process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE) return process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;
  const cache = process.env.PLAYWRIGHT_BROWSERS_PATH || join(homedir(), '.cache', 'ms-playwright');
  if (!existsSync(cache)) return null;
  const dirs = readdirSync(cache)
    .filter((d) => d.startsWith('chromium_headless_shell-') || d.startsWith('chromium-'))
    .sort();
  for (const d of dirs.reverse()) {
    for (const rel of ['chrome-headless-shell-linux64/chrome-headless-shell', 'chrome-linux/chrome', 'chrome-linux/headless_shell']) {
      const p = join(cache, d, rel);
      if (existsSync(p)) return p;
    }
  }
  return null;
}

const results = [];
const record = (step, pass, detail) => {
  results.push({ step, pass });
  console.log(`${pass ? 'PASS' : 'FAIL'} — ${step}${detail ? ' :: ' + detail : ''}`);
};

const require = createRequire(import.meta.url);
let chromium;
try {
  ({ chromium } = require('playwright-core'));
} catch {
  console.error('playwright-core not found. Install it (npm i -g playwright-core) and retry.');
  process.exit(2);
}

const exe = findChromium();
if (!exe) {
  console.error('No Chromium found. Set PLAYWRIGHT_CHROMIUM_EXECUTABLE or run `npx playwright install chromium`.');
  process.exit(2);
}

const browser = await chromium.launch({ executablePath: exe, args: ['--no-sandbox'] });
const page = await browser.newPage({ viewport: { width: 440, height: 720 } });
const errors = [];
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));

try {
  await page.goto(URL, { waitUntil: 'networkidle' });

  await page.getByRole('button', { name: /Get my P&L/ }).first().waitFor({ timeout: 8000 });
  const greeting = await page.locator('.bub.bot').first().innerText();
  const placeholder = await page.locator('input[aria-label="Message"]').getAttribute('placeholder');
  const footer = await page.getByText('Factual answers only — never investment advice.').count();
  record('1. entry surface seeded (greeting + chips + composer + compliance footer)', /X008593/.test(greeting) && placeholder === 'Ask anything about FinX…' && footer === 1);

  await page.locator('input[aria-label="Message"]').fill('Get my P&L');
  await page.getByRole('button', { name: 'Send' }).click();
  await page.getByRole('button', { name: 'Equity' }).waitFor({ timeout: 8000 });
  const userEcho = await page.locator('.bub.user').last().innerText();
  record('2. free-text -> user bubble + stepper (segment step)', userEcho === 'Get my P&L' && (await page.getByText('1 · Segment').count()) >= 1);

  await page.getByRole('button', { name: 'Equity' }).click();
  await page.getByRole('button', { name: 'This FY' }).waitFor({ timeout: 8000 });
  record('3. tap Equity -> segment chosen, period step active', (await page.getByText('Equity').count()) >= 1);

  await page.getByRole('button', { name: 'This FY' }).click();
  await page.getByRole('button', { name: 'PDF' }).waitFor({ timeout: 8000 });
  record('4. tap This FY -> format step active (PDF + Excel)', (await page.getByRole('button', { name: 'Excel' }).count()) === 1);

  await page.getByRole('button', { name: 'PDF' }).click();
  await page.getByText('PnL_Equity_FY2025-26.pdf').waitFor({ timeout: 8000 });
  const sub = await page.getByText('196 KB · PDF · password: PAN').count();
  const dl = await page.getByRole('button', { name: 'Download' }).count();
  const helper = await page.getByRole('button', { name: /Trouble opening it/ }).count();
  record('5. tap PDF -> file card (filename + sub + Download + helper)', sub === 1 && dl === 1 && helper === 1);

  record('6. no uncaught console errors', errors.length === 0, errors.join(' | '));
} catch (err) {
  record('EXCEPTION', false, err.message);
} finally {
  await browser.close();
}

const failed = results.filter((r) => !r.pass).length;
console.log(`\nSUMMARY: ${results.length - failed}/${results.length} passed`);
process.exit(failed ? 1 : 0);
