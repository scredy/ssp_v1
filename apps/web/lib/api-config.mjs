export function resolveApiBaseUrl(configuredUrl, webOrigin) {
  const value = typeof configuredUrl === "string" && configuredUrl.trim()
    ? configuredUrl.trim()
    : "";
  if (!value) return "";
  const normalized = value.replace(/\/+$/, "");
  if (!webOrigin) return normalized;
  try {
    const apiUrl = new URL(normalized);
    const siteUrl = new URL(webOrigin);
    const localHosts = new Set(["localhost", "127.0.0.1"]);
    if (localHosts.has(apiUrl.hostname) && localHosts.has(siteUrl.hostname)) {
      apiUrl.hostname = siteUrl.hostname;
      return apiUrl.toString().replace(/\/$/, "");
    }
  } catch {
    return normalized;
  }
  return normalized;
}
