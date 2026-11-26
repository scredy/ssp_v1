import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { resolveApiBaseUrl } from "./api-config.mjs";

test("an unset API base URL stays unset instead of silently targeting a hardcoded port", async () => {
  assert.equal(resolveApiBaseUrl(undefined), "");
  const client = await readFile(new URL("./car-api.ts", import.meta.url), "utf8");
  assert.match(client, /The SSP service is not configured\. Set NEXT_PUBLIC_API_BASE_URL and restart the web server\./);
});

test("local web configuration documents the API base URL in the web app environment", async () => {
  const webExample = await readFile(new URL("../.env.example", import.meta.url), "utf8");
  assert.match(webExample, /^NEXT_PUBLIC_API_BASE_URL=http:\/\/localhost:8000$/m);
});

test("API base URL preserves deployment configuration and removes trailing slashes", () => {
  assert.equal(resolveApiBaseUrl("https://api.example.test/service///"), "https://api.example.test/service");
});

test("local API and web URLs use one cookie host even when loopback aliases differ", () => {
  assert.equal(resolveApiBaseUrl("http://127.0.0.1:8000", "http://localhost:3000"), "http://localhost:8000");
  assert.equal(resolveApiBaseUrl("http://localhost:8000", "http://127.0.0.1:3000"), "http://127.0.0.1:8000");
  assert.equal(resolveApiBaseUrl("https://api.example.test", "https://www.example.test"), "https://api.example.test");
});

test("staff login and role dashboard share the configured API client", async () => {
  const [login, dashboardRoute, dashboard] = await Promise.all([
    readFile(new URL("../app/staff/login/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/staff/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/role-dashboard.tsx", import.meta.url), "utf8"),
  ]);
  assert.match(login, /import \{ api \} from "@\/lib\/car-api"/);
  assert.match(dashboardRoute, /RoleDashboard from "@\/components\/role-dashboard"/);
  assert.match(dashboard, /import \{ api, User \} from "@\/lib\/car-api"/);
  assert.doesNotMatch(login, /NEXT_PUBLIC_API_BASE_URL/);
  assert.doesNotMatch(dashboardRoute, /NEXT_PUBLIC_API_BASE_URL/);
  assert.doesNotMatch(dashboard, /NEXT_PUBLIC_API_BASE_URL/);
});

test("public appointment, enquiry, and quote submissions use the shared API client and retain entries on failure", async () => {
  const form = await readFile(new URL("../components/public-enquiry-form.tsx", import.meta.url), "utf8");
  assert.match(form, /import \{ api, Vehicle \} from "@\/lib\/car-api"/);
  assert.match(form, /api<\{reference:string\}>\("\/api\/public\/enquiries\/"/);
  assert.doesNotMatch(form, /fetch\(/);
  assert.match(form, /catch \(e\) \{ setError\(/);
  assert.match(form, /\{error && <p className="enquiry-error enquiry-wide" role="alert">\{error\}<\/p>\}/);
  assert.match(form, /value=\{form\.full_name\}/);
  assert.match(form, /value=\{form\.vehicle_reference\}/);
  assert.match(form, /value=\{form\.message\}/);
});

test("public vehicle-list API failures are shown instead of silently becoming an empty selector", async () => {
  const form = await readFile(new URL("../components/public-enquiry-form.tsx", import.meta.url), "utf8");
  assert.match(form, /setCarsError\(e instanceof Error \? `Available vehicles could not be loaded\./);
  assert.match(form, /\{carsError && <span className="enquiry-error" role="alert">\{carsError\}<\/span>\}/);
});
