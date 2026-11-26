import { appendFileSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { randomUUID } from 'node:crypto';

export const root = resolve(import.meta.dirname, '..', '..');
export const artifacts = resolve(root, 'test-harness', 'artifacts');
export const screenshots = resolve(artifacts, 'screenshots');
export const emails = resolve(artifacts, 'emails');
export const stateFile = resolve(artifacts, 'run-state.json');
mkdirSync(screenshots, { recursive: true });
mkdirSync(emails, { recursive: true });

export function readEnvFile(path = resolve(root, 'test-harness', '.env.test')) {
  const values = {};
  for (const line of readFileSync(path, 'utf8').split(/\r?\n/)) {
    const match = line.match(/^\s*([^#=]+)=(.*)$/);
    if (match) values[match[1].trim()] = match[2].trim().replace(/^(['"])(.*)\1$/, '$2');
  }
  return values;
}

export function readState() {
  try { return JSON.parse(readFileSync(stateFile, 'utf8')); } catch { return {}; }
}

export function writeState(state) {
  writeFileSync(stateFile, JSON.stringify(state, null, 2), 'utf8');
}

export function newPassword(role) {
  return `Ssp!E2E_${role}_${randomUUID()}_2026`;
}

export function attachDiagnostics(page) {
  const events = [];
  page.on('console', (message) => {
    if (message.type() === 'error') events.push({ type: 'console', message: message.text() });
  });
  page.on('pageerror', (error) => events.push({ type: 'pageerror', message: error.message }));
  page.on('requestfailed', (request) => events.push({
    type: 'requestfailed', method: request.method(), url: request.url(), error: request.failure()?.errorText,
  }));
  page.on('response', async (response) => {
    if (response.status() < 400) return;
    let body = '';
    try { body = (await response.text()).slice(0, 500); } catch {}
    events.push({ type: 'http', status: response.status(), url: response.url(), body });
  });
  return events;
}

function safeName(value) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 70);
}

let stepNumber = (() => {
  try { return readFileSync(resolve(artifacts, 'steps.jsonl'), 'utf8').trim().split(/\r?\n/).filter(Boolean).length; }
  catch { return 0; }
})();
let previousAction = (() => {
  try {
    const lines = readFileSync(resolve(artifacts, 'steps.jsonl'), 'utf8').trim().split(/\r?\n/).filter(Boolean);
    return lines.length ? JSON.parse(lines.at(-1)).action : null;
  } catch { return null; }
})();
export async function step(page, role, action, expected, operation, { continueOnFailure = false } = {}) {
  stepNumber += 1;
  const name = `${String(stepNumber).padStart(3, '0')}-${safeName(action)}`;
  const events = page.__acceptanceEvents ?? [];
  const eventStart = events.length;
  let actual;
  let failure = null;
  try {
    actual = await operation();
  } catch (error) {
    failure = error;
    actual = `FAILED: ${error?.message ?? String(error)}`;
  }
  const screenshot = resolve(screenshots, `${name}.png`);
  try { await page.screenshot({ path: screenshot, fullPage: true, timeout: 8000 }); }
  catch (error) { if (!failure) failure = error; }
  const record = {
    route: new URL(page.url()).pathname + new URL(page.url()).search,
    role,
    precedingAction: previousAction,
    action,
    expected,
    actual: typeof actual === 'string' ? actual : JSON.stringify(actual),
    passed: !failure,
    screenshot: `screenshots/${name}.png`,
    browserErrors: events.slice(eventStart),
    timestamp: new Date().toISOString(),
  };
  appendFileSync(resolve(artifacts, 'steps.jsonl'), `${JSON.stringify(record)}\n`, 'utf8');
  previousAction = action;
  if (failure && !continueOnFailure) throw failure;
  return actual;
}

export function attachPageDiagnostics(page) {
  page.__acceptanceEvents = attachDiagnostics(page);
}

export function listEmails() {
  return readdirSync(emails).filter((name) => name.endsWith('.eml'));
}

export function invitationLink(fileName, kind = 'accept-invitation') {
  const text = readFileSync(resolve(emails, fileName), 'utf8');
  const match = text.match(new RegExp(`http:\\/\\/localhost:3100\\/staff\\/${kind}\\?token=[A-Za-z0-9_-]+`));
  if (!match) throw new Error(`No local ${kind} link found in generated test email ${fileName}.`);
  return match[0];
}

export function resetSteps() {
  stepNumber = 0;
  previousAction = null;
  writeFileSync(resolve(artifacts, 'steps.jsonl'), '', 'utf8');
}
