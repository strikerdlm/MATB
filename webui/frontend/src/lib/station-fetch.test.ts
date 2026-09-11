import { expect, it, vi, afterEach } from "vitest";
import { stationFetch } from "./station-fetch";
afterEach(() => vi.unstubAllGlobals());
it("does not present a queued heavy request as a scientific result", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ job_id: "job-A" }), {
          status: 202,
          headers: { "X-MATB-Station-Job": "job-A" },
        }),
      ),
  );
  await expect(stationFetch("/analysis/run")).rejects.toThrow("job-A");
  await expect(stationFetch("/analysis/run")).rejects.toThrow("/station");
});
it("preserves ordinary instrument 202 status responses", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ status: "pending" }), { status: 202 }),
      ),
  );
  expect((await stationFetch("/instrument")).status).toBe(202);
});
