import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { resolveApiUpstreamUrl } from "./api-config.mjs";

test("the trusted upstream accepts HTTPS deployment origins and local development HTTP", () => {
  assert.equal(resolveApiUpstreamUrl("https://ssp-backend.example.onrender.com", "production"), "https://ssp-backend.example.onrender.com");
  assert.equal(resolveApiUpstreamUrl("http://localhost:8000", "development"), "http://localhost:8000");
  assert.equal(resolveApiUpstreamUrl("http://127.0.0.1:8000", "test"), "http://127.0.0.1:8000");
});

test("untrusted schemes, credentials, paths, and missing configuration are rejected", () => {
  assert.throws(() => resolveApiUpstreamUrl(undefined), /API_UPSTREAM_URL is required/);
  assert.throws(() => resolveApiUpstreamUrl("http://backend.example.test", "production"), /must use HTTPS/);
  assert.throws(() => resolveApiUpstreamUrl("https://user:pass@backend.example.test"), /without credentials/);
  assert.throws(() => resolveApiUpstreamUrl("https://backend.example.test/prefix"), /without credentials/);
  assert.throws(() => resolveApiUpstreamUrl("https://backend.example.test?next=http://169.254.169.254"), /without credentials/);
});

test("browser API calls are relative and do not expose the server-only origin", async () => {
  const [client, route, webExample] = await Promise.all([
    readFile(new URL("./car-api.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/api/[...path]/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../.env.example", import.meta.url), "utf8"),
  ]);
  assert.match(client, /export const API = ""/);
  assert.match(client, /function sameOriginProxyPath/);
  assert.match(client, /url\.pathname = url\.pathname\.replace\(\/\\\/\$\//);
  assert.doesNotMatch(client, /API_UPSTREAM_URL|NEXT_PUBLIC_API_BASE_URL/);
  assert.match(route, /process\.env\.API_UPSTREAM_URL/);
  assert.match(route, /Cache-Control.*private, no-store/s);
  assert.match(webExample, /^API_UPSTREAM_URL=http:\/\/localhost:8000$/m);
  assert.doesNotMatch(webExample, /^NEXT_PUBLIC_API_BASE_URL=/m);
});

test("all staff auth and public enquiry forms use the same-origin API client", async () => {
  const [login, logout, shell, enquiry] = await Promise.all([
    readFile(new URL("../app/staff/login/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/staff-shell.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/staff-shell.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/public-enquiry-form.tsx", import.meta.url), "utf8"),
  ]);
  assert.match(login, /import \{ api \} from "@\/lib\/car-api"/);
  assert.match(shell, /api<void>\("\/api\/auth\/logout\/"/);
  assert.match(shell, /api<User>\("\/api\/auth\/me\/"/);
  assert.match(enquiry, /api<\{reference:string\}>\("\/api\/public\/enquiries\/"/);
  assert.doesNotMatch([login, logout].join("\n"), /localStorage/);
});

test("proxy forwards request bodies, CSRF and cookies, and canonicalizes Django API paths", async () => {
  const route = await readFile(new URL("../app/api/[...path]/route.ts", import.meta.url), "utf8");
  for (const header of ["cookie", "origin", "referer", "x-csrftoken", "idempotency-key", "content-type", "range"]) {
    assert.match(route, new RegExp(`\\"${header}\\"`));
  }
  assert.match(route, /body: hasBody \? request\.body : undefined/);
  assert.match(route, /getSetCookie/);
  assert.match(route, /always send the canonical API path/);
  assert.ok(route.includes('new URL(`/api/${path.map(encodeURIComponent).join("/")}/`, upstreamOrigin)'));
  assert.match(route, /domain\\s\*=/i);
  assert.match(route, /forwardedProto === "https" \? "https" : "http"/);
});
