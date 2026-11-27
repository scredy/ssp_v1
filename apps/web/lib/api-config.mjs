const LOCAL_HTTP_HOSTS = new Set(["localhost", "127.0.0.1", "::1"]);

/** Validate the single server-configured Django origin. Request data never selects this origin. */
export function resolveApiUpstreamUrl(configuredUrl, nodeEnv = "development") {
  if (typeof configuredUrl !== "string" || !configuredUrl.trim()) {
    throw new Error("API_UPSTREAM_URL is required by the server-side API proxy.");
  }

  let upstream;
  try {
    upstream = new URL(configuredUrl.trim());
  } catch {
    throw new Error("API_UPSTREAM_URL must be an absolute HTTP(S) origin.");
  }

  const localDevelopmentHttp = nodeEnv !== "production"
    && upstream.protocol === "http:"
    && LOCAL_HTTP_HOSTS.has(upstream.hostname);
  if (upstream.protocol !== "https:" && !localDevelopmentHttp) {
    throw new Error("API_UPSTREAM_URL must use HTTPS outside local development.");
  }
  if (upstream.username || upstream.password || upstream.search || upstream.hash || upstream.pathname !== "/") {
    throw new Error("API_UPSTREAM_URL must contain only a trusted origin, without credentials, path, query, or fragment.");
  }

  return upstream.origin;
}
