import { beforeEach, describe, expect, it, vi } from "vitest";
import { getApiBase, resetApiBaseCache } from "@/lib/runtime-config";

function response(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

describe("runtime backend discovery", () => {
  beforeEach(() => {
    resetApiBaseCache();
    vi.restoreAllMocks();
  });

  it("derives the backend origin from browser host and validated runtime port", async () => {
    global.fetch = vi.fn().mockResolvedValue(response(200, { backend_port: 8123 }));
    await expect(getApiBase(new URL("http://lab-host:3100/mission")))
      .resolves.toBe("http://lab-host:8123");
    const [url, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe("http://lab-host:3100/api/runtime-config");
    expect(init.method).toBe("GET");
    expect(init.cache).toBe("no-store");
  });

  it("caches a valid same-origin runtime response", async () => {
    global.fetch = vi.fn().mockResolvedValue(response(200, { backend_port: 8124 }));
    const browser = new URL("https://lab-host:3100/mission");
    await expect(getApiBase(browser)).resolves.toBe("https://lab-host:8124");
    await expect(getApiBase(browser)).resolves.toBe("https://lab-host:8124");
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  it("rejects malformed runtime responses", async () => {
    global.fetch = vi.fn().mockResolvedValue(response(200, { backend_port: 70000 }));
    await expect(getApiBase(new URL("http://lab-host:3100/mission"))).rejects.toThrow(/backend_port/);
  });

  it("retries discovery after a transient failure while sharing concurrent requests", async () => {
    global.fetch = vi.fn()
      .mockRejectedValueOnce(new Error("temporary network failure"))
      .mockResolvedValue(response(200, { backend_port: 8124 }));
    const browser = new URL("http://lab-host:3100/mission");
    const first = getApiBase(browser);
    expect(getApiBase(browser)).toBe(first);
    await expect(first).rejects.toThrow("temporary network failure");
    await expect(getApiBase(browser)).resolves.toBe("http://lab-host:8124");
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });

  it("does not let an older failure evict a newer discovery", async () => {
    let rejectOld!: (error: Error) => void;
    global.fetch = vi.fn()
      .mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectOld = reject; }))
      .mockResolvedValue(response(200, { backend_port: 8124 }));
    const first = getApiBase(new URL("http://old-host:3100/"));
    const browser = new URL("http://new-host:3100/");
    await expect(getApiBase(browser)).resolves.toBe("http://new-host:8124");
    rejectOld(new Error("old request failed"));
    await expect(first).rejects.toThrow("old request failed");
    await expect(getApiBase(browser)).resolves.toBe("http://new-host:8124");
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });
});
