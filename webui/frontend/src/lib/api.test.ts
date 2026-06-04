import { describe, it, expect, vi, beforeEach } from "vitest";
import { createParticipant, getTracker, ingestCsv, IngestError, getMetricsLong, getFits, runAnalysis, getLatestAnalysis, runBayes, getBayesStatus } from "@/lib/api";

beforeEach(() => { vi.restoreAllMocks(); });

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response);
}

describe("api client", () => {
  it("getTracker GETs /tracker and returns cells", async () => {
    const cells = [{ participant_id: "P01", visit_ordinal: 1, scheduled_day: 0, workload_level: "LOW", present: true }];
    global.fetch = mockFetch(200, cells);
    const out = await getTracker();
    expect(out).toEqual(cells);
    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining("/tracker"), expect.objectContaining({ method: "GET" }));
  });

  it("createParticipant POSTs JSON body", async () => {
    global.fetch = mockFetch(201, { id: "P01", enrollment_date: "2026-06-01" });
    const p = await createParticipant({ id: "P01", enrollment_date: "2026-06-01" });
    expect(p.id).toBe("P01");
    const [, init] = (global.fetch as any).mock.calls[0];
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toMatchObject({ id: "P01" });
  });

  it("ingestCsv sends multipart form and throws IngestError on 409", async () => {
    global.fetch = mockFetch(409, { detail: "cell already filled: P01 visit 1 LOW" });
    const file = new File([new Uint8Array([1, 2, 3])], "run.csv", { type: "text/csv" });
    await expect(
      ingestCsv(file, { participant_id: "P01", visit_ordinal: 1, workload_level: "LOW" })
    ).rejects.toThrow(IngestError);
  });

  it("ingestCsv builds FormData with the exact backend field names", async () => {
    global.fetch = mockFetch(201, { id: 1, workload_level: "MEDIUM", visit_id: 7 });
    const file = new File([new Uint8Array([1, 2, 3])], "run.csv", { type: "text/csv" });
    await ingestCsv(file, {
      participant_id: "P02", visit_ordinal: 3, workload_level: "MEDIUM", overwrite: true,
    });
    const [url, init] = (global.fetch as any).mock.calls[0];
    expect(url).toContain("/ingest");
    expect(init.method).toBe("POST");
    const form = init.body as FormData;
    expect(form.get("participant_id")).toBe("P02");
    expect(form.get("visit_ordinal")).toBe("3");
    expect(form.get("workload_level")).toBe("MEDIUM");
    expect(form.get("overwrite")).toBe("true");
    expect(form.get("file")).toBeInstanceOf(File);
  });

  it("getMetricsLong hits /metrics/long with optional participant filter", async () => {
    global.fetch = mockFetch(200, []);
    await getMetricsLong();
    expect((global.fetch as any).mock.calls[0][0]).toContain("/metrics/long");
    global.fetch = mockFetch(200, []);
    await getMetricsLong("P02");
    expect((global.fetch as any).mock.calls[0][0]).toContain("participant_id=P02");
  });

  it("getFits hits /fits", async () => {
    global.fetch = mockFetch(200, []);
    await getFits("P01");
    const url = (global.fetch as any).mock.calls[0][0] as string;
    expect(url).toContain("/fits");
    expect(url).toContain("participant_id=P01");
  });

  it("runAnalysis POSTs /analysis/run", async () => {
    global.fetch = mockFetch(200, { cached: false, engine_version: "1.0.0" });
    const art = await runAnalysis();
    expect(art.cached).toBe(false);
    const [url, init] = (global.fetch as any).mock.calls[0];
    expect(url).toContain("/analysis/run");
    expect(init.method).toBe("POST");
  });

  it("getLatestAnalysis returns null on 404", async () => {
    global.fetch = mockFetch(404, { detail: "no analysis has been run yet" });
    expect(await getLatestAnalysis()).toBeNull();
  });

  it("runBayes POSTs /analysis/bayes/run", async () => {
    global.fetch = mockFetch(202, { job_id: 1, status: "queued", cached: false });
    const job = await runBayes();
    expect(job.status).toBe("queued");
    const [url, init] = (global.fetch as any).mock.calls[0];
    expect(url).toContain("/analysis/bayes/run");
    expect(init.method).toBe("POST");
  });

  it("getBayesStatus returns null on 404", async () => {
    global.fetch = mockFetch(404, { detail: "no Bayesian job yet" });
    expect(await getBayesStatus()).toBeNull();
  });
});
