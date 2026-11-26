import { existsSync, readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const testDbName = 'ssp_playwright';
const envFile = resolve(root, '.env');
const rootEnv = new Map();
if (existsSync(envFile)) {
  for (const line of readFileSync(envFile, 'utf8').split(/\r?\n/)) {
    const match = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/);
    if (match) rootEnv.set(match[1], match[2].replace(/^(['"])(.*)\1$/, '$2'));
  }
}

const configuredDb = rootEnv.get('POSTGRES_DB') ?? '(unset)';
const python = resolve(root, 'apps/api/.venv/Scripts/python.exe');
let identityVerified = false;
let identityOutput = '';

if (configuredDb.toLowerCase() === testDbName || !existsSync(python)) {
  identityOutput = configuredDb.toLowerCase() === testDbName
    ? 'Refused: repository default unexpectedly names the test database.'
    : 'Django virtualenv Python is unavailable.';
} else {
  const result = spawnSync(python, [resolve(import.meta.dirname, 'verify_database.py'), testDbName], {
    cwd: root,
    encoding: 'utf8',
    timeout: 10000,
  });
  const output = `${result.stdout ?? ''}${result.stderr ?? ''}`;
  const match = output.match(/database_probe=\('([^']+)'/);
  identityVerified = result.status === 0 && match?.[1] === testDbName;
  const failureCause = /connection refused|actively refused/i.test(output) ? 'connection refused'
    : /database .* does not exist|InvalidCatalogName/i.test(output) ? 'target database does not exist'
      : /could not translate host|name or service not known/i.test(output) ? 'database host could not be resolved'
        : /password authentication failed/i.test(output) ? 'database authentication failed'
          : /timeout|timed out/i.test(output) ? 'connection timed out'
            : 'identity query failed';
  identityOutput = identityVerified
    ? `Read-only server identity confirmed: ${match[1]}`
    : `Read-only identity query did not confirm ${testDbName} (exit ${result.status ?? 'unknown'}; ${failureCause}). No database writes were attempted.`;
}

let playwrightAvailable = false;
playwrightAvailable = existsSync(resolve(import.meta.dirname, 'node_modules/playwright/package.json'));

const results = [
  `Repository default database name: ${configuredDb}`,
  `Test database identity verified: ${identityVerified ? 'yes' : 'no'}`,
  identityOutput,
  `Playwright package installed in test-harness: ${playwrightAvailable ? 'yes' : 'no'}`,
];

for (const [label, url] of [
  ['Test web', 'http://localhost:3100'],
  ['Test API health', 'http://localhost:8100/api/health/'],
]) {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(1500) });
    results.push(`${label} endpoint: HTTP ${response.status}`);
  } catch (error) {
    results.push(`${label} endpoint: unavailable (${error.cause?.code ?? error.name})`);
  }
}

for (const result of results) console.log(result);
const blockers = [];
if (!identityVerified) blockers.push(`could not verify isolated PostgreSQL database ${testDbName}`);
if (!playwrightAvailable) blockers.push('Playwright is not installed in test-harness');
if (blockers.length) {
  console.error(`BLOCKED: ${blockers.join('; ')}`);
  process.exitCode = 2;
}
