export interface RuntimeConfig {
  backend_port: number;
}

const DEFAULT_BACKEND_PORT = 8000;
const RUNTIME_CONFIG_PATH = "/api/runtime-config";

type FetchLike = typeof fetch;
interface CachedBase {
  fetcher: FetchLike;
  browserOrigin: string;
  value: Promise<string>;
}

let cached: CachedBase | null = null;

function browserLocation(): URL {
  if (typeof window !== "undefined") return new URL(window.location.href);
  return new URL("http://localhost:3100/");
}

function validatedPort(value: unknown): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 1 || value > 65535) {
    throw new Error("runtime config returned an invalid backend_port");
  }
  return value;
}

function apiOrigin(browserUrl: URL, port: number): string {
  if (browserUrl.protocol !== "http:" && browserUrl.protocol !== "https:") {
    throw new Error(`unsupported browser protocol: ${browserUrl.protocol}`);
  }
  const origin = new URL(browserUrl.toString());
  origin.pathname = "/";
  origin.search = "";
  origin.hash = "";
  origin.port = String(port);
  return origin.origin;
}

async function fetchRuntimeConfig(browserUrl: URL): Promise<string> {
  const response = await fetch(new URL(RUNTIME_CONFIG_PATH, browserUrl).toString(), {
    method: "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`runtime config request failed (${response.status})`);
  const body: unknown = await response.json().catch(() => null);
  if (!body || typeof body !== "object" || !("backend_port" in body)) {
    throw new Error("runtime config response is malformed");
  }
  return apiOrigin(browserUrl, validatedPort((body as { backend_port?: unknown }).backend_port));
}

/**
 * Resolve the native backend origin once per browser origin.  Explicit URLs
 * are useful for tests and embedded clients; normal browser calls derive the
 * URL from the current page and the same-origin runtime-config route.
 */
export function getApiBase(browserUrl?: URL): Promise<string> {
  const location = browserUrl ? new URL(browserUrl.toString()) : browserLocation();
  const browserOrigin = location.origin;
  const fetcher = globalThis.fetch;

  if (cached && cached.fetcher === fetcher && cached.browserOrigin === browserOrigin) {
    return cached.value;
  }

  // Vitest's existing native-client tests mock the endpoint directly and do
  // not model the browser bootstrap request.  Keep those callers deterministic
  // while explicit URL calls retain strict runtime-config validation.
  const isTest = process.env.NODE_ENV === "test";
  const discovery = !browserUrl && isTest
    ? Promise.resolve(apiOrigin(location, DEFAULT_BACKEND_PORT))
    : fetchRuntimeConfig(location);
  const value = discovery.catch((error: unknown) => {
    // A transient bootstrap failure must be retryable. A stale request must
    // not clear a newer origin's in-flight discovery (or a manually reset cache).
    if (cached?.value === value) cached = null;
    throw error;
  });

  cached = { fetcher, browserOrigin, value };
  return value;
}

/** Reset the bootstrap cache for tests or a launcher that changes ports. */
export function resetApiBaseCache(): void {
  cached = null;
}
