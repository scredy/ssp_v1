import { resolveApiUpstreamUrl } from "@/lib/api-config.mjs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const revalidate = 0;

type RouteContext = { params: Promise<{ path: string[] }> };
type StreamingRequestInit = RequestInit & { duplex?: "half" };

const HOP_BY_HOP_HEADERS = new Set([
  "connection", "content-length", "host", "keep-alive", "proxy-authenticate",
  "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade",
  "forwarded", "x-forwarded-for", "x-forwarded-host", "x-forwarded-port",
  "x-forwarded-proto",
]);
const REQUEST_HEADER_ALLOWLIST = [
  "accept", "content-type", "cookie", "if-modified-since", "if-none-match",
  "if-range", "origin", "range", "referer", "x-csrftoken", "idempotency-key",
];

function jsonError(status: number, detail: string) {
  return Response.json({ detail }, {
    status,
    headers: { "Cache-Control": "private, no-store, max-age=0", Pragma: "no-cache" },
  });
}

function safePath(path: string[]) {
  return path.length > 0 && path.every((segment) =>
    segment.length > 0 && segment.length <= 200 && segment !== "." && segment !== ".."
    && !/[\\/\u0000-\u001f\u007f]/.test(segment)
  );
}

function splitSetCookieHeader(value: string) {
  // The lookahead splits only at a new cookie pair, not the comma in Expires.
  return value.split(/,(?=\s*[^;,=\s]+=[^;,]*)/g);
}

function hostOnlyCookie(setCookie: string) {
  // Upstream cookies become host-only cookies on the frontend origin. In
  // particular, never broaden cookies to a shared .onrender.com domain.
  return setCookie.split(";")
    .filter((attribute, index) => index === 0 || !/^\s*domain\s*=/i.test(attribute))
    .join(";");
}

function appendSetCookies(source: Headers, target: Headers) {
  const headersWithCookieApi = source as Headers & { getSetCookie?: () => string[] };
  const cookies = headersWithCookieApi.getSetCookie?.()
    ?? (source.get("set-cookie") ? splitSetCookieHeader(source.get("set-cookie")!) : []);
  for (const cookie of cookies) target.append("Set-Cookie", hostOnlyCookie(cookie));
}

async function forward(request: Request, context: RouteContext) {
  const { path } = await context.params;
  if (!safePath(path)) return jsonError(400, "Invalid API path.");

  let upstreamOrigin: string;
  try {
    upstreamOrigin = resolveApiUpstreamUrl(process.env.API_UPSTREAM_URL, process.env.NODE_ENV);
  } catch (error) {
    console.error("API proxy configuration is invalid.", error instanceof Error ? error.message : "unknown configuration error");
    return jsonError(503, "The API service is not configured.");
  }

  const incomingUrl = new URL(request.url);
  // Django API routes use APPEND_SLASH. Next may normalize a trailing slash
  // before invoking this route handler, so always send the canonical API path.
  const upstreamUrl = new URL(`/api/${path.map(encodeURIComponent).join("/")}/`, upstreamOrigin);
  upstreamUrl.search = incomingUrl.search;
  const headers = new Headers();
  for (const name of REQUEST_HEADER_ALLOWLIST) {
    const value = request.headers.get(name);
    if (value !== null) headers.set(name, value);
  }
  // Render terminates public TLS before Next.js, so its trusted forwarded
  // scheme is needed when the internal request URL is HTTP. Only the exact
  // HTTPS value is honored; the upstream host remains fixed and configured.
  const forwardedProto = request.headers.get("x-forwarded-proto")?.split(",", 1)[0].trim().toLowerCase();
  headers.set("X-Forwarded-Proto", incomingUrl.protocol === "https:" || forwardedProto === "https" ? "https" : "http");
  headers.set("Accept-Encoding", "identity");

  const method = request.method.toUpperCase();
  const hasBody = method !== "GET" && method !== "HEAD";
  const init: StreamingRequestInit = {
    method,
    headers,
    body: hasBody ? request.body : undefined,
    cache: "no-store",
    redirect: "manual",
    ...(hasBody ? { duplex: "half" as const } : {}),
  };

  let upstreamResponse: Response;
  try {
    upstreamResponse = await fetch(upstreamUrl, init);
  } catch {
    return jsonError(502, "The API service is unavailable.");
  }

  const responseHeaders = new Headers();
  upstreamResponse.headers.forEach((value, name) => {
    const lowerName = name.toLowerCase();
    if (lowerName === "set-cookie" || HOP_BY_HOP_HEADERS.has(lowerName)
      || lowerName.startsWith("access-control-")) return;
    if (lowerName === "location") {
      try {
        const location = new URL(value, upstreamOrigin);
        if (location.origin === upstreamOrigin) {
          responseHeaders.set(name, `${location.pathname}${location.search}${location.hash}`);
        }
      } catch { /* Drop malformed redirect locations. */ }
      return;
    }
    responseHeaders.set(name, value);
  });
  appendSetCookies(upstreamResponse.headers, responseHeaders);
  responseHeaders.set("Cache-Control", "private, no-store, max-age=0");
  responseHeaders.set("Pragma", "no-cache");

  const bodyAllowed = method !== "HEAD" && upstreamResponse.status !== 204 && upstreamResponse.status !== 304;
  return new Response(bodyAllowed ? upstreamResponse.body : null, {
    status: upstreamResponse.status,
    statusText: upstreamResponse.statusText,
    headers: responseHeaders,
  });
}

export const GET = forward;
export const HEAD = forward;
export const POST = forward;
export const PUT = forward;
export const PATCH = forward;
export const DELETE = forward;
export const OPTIONS = forward;
