// Short-lived, shared reads for configuration used by several screens.
const reads = new Map<string, { until: number; promise: Promise<unknown> }>();
export function sharedRead<T>(key: string, read: () => Promise<T>, ttlMs = 30_000): Promise<T> {
  const cached = reads.get(key);
  if (cached && cached.until > Date.now()) return cached.promise as Promise<T>;
  const promise = read().catch((error: unknown) => { reads.delete(key); throw error; });
  reads.set(key, { until: Date.now() + ttlMs, promise });
  return promise;
}
