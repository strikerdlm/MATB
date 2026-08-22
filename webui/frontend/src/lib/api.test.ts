import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  createParticipant,
  createStudyContext,
  downloadResearchBundle,
  getBayesStatus,
  getFits,
  getLatestAnalysis,
  getMetricsLong,
  getResearchContext,
  getScreenSummary,
  getStudyContext,
  getStudyProtocol,
  getTracker,
  ingestCsv,
  IngestError,
  postScreen,
  runAnalysis,
  runBayes,
} from "@/lib/api";

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

  it("getStudyProtocol GETs the canonical visit definitions", async () => {
    const protocol = {
      protocol_id: "astra-2026",
      protocol_version: "1.0.0",
      schedule_sha256: "schedule-hash",
      visits: [
        { ordinal: 1, code: "T0", scheduled_day: 0 },
        { ordinal: 2, code: "DM8", scheduled_day: 8 },
        { ordinal: 3, code: "DM15", scheduled_day: 15 },
      ],
    };
    global.fetch = mockFetch(200, protocol);

    const result = await getStudyProtocol();

    expect(result).toEqual(protocol);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/study/protocol"),
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("getStudyContext returns null on 404", async () => {
    global.fetch = mockFetch(404, { detail: "study context not found" });

    expect(await getStudyContext("P01")).toBeNull();
  });

  it("createStudyContext surfaces a second-write conflict", async () => {
    const body = {
      task_sequence: "MATB_LIFTOFF" as const,
      prior_fpv_hours: 12.5,
      gaming_hours_per_week: 3,
    };
    const created = {
      participant_id: "P01",
      protocol_id: "astra-2026",
      ...body,
      created_at: "2026-08-18T00:00:00Z",
    };
    global.fetch = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: async () => created,
      } as Response)
      .mockResolvedValueOnce({
        ok: false,
        status: 409,
        json: async () => ({ detail: "study context already exists" }),
      } as Response);

    expect(await createStudyContext("P01", body)).toEqual(created);
    await expect(createStudyContext("P01", body)).rejects.toMatchObject({ status: 409 });
    const [url, init] = (global.fetch as any).mock.calls[0];
    expect(url).toContain("/participants/P01/study-context");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body)).toEqual(body);
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
    const manifest = new File([JSON.stringify({ manifest_version: 1 })], "run.manifest.json", { type: "application/json" });
    await ingestCsv(file, {
      participant_id: "P02", visit_ordinal: 3, workload_level: "MEDIUM", overwrite: true, manifest,
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
    expect(form.get("manifest")).toBeInstanceOf(File);
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

  it("postScreen POSTs participant_id + payload + overwrite", async () => {
    global.fetch = mockFetch(201, { participant_id: "P01", screen_version: 1, scores: {} });
    const payload = { seed: 1, administered_at: "t", fast_mode: false,
      simple_rt: { trials: [] }, choice_rt: { trials: [] },
      nback: { trials: [], soa_ms: 2500 },
      tracking: { samples: [], n_expected_samples: 0, path_amplitude_px: 0 } } as any;
    await postScreen("P01", payload, true);
    const [url, init] = (global.fetch as any).mock.calls[0];
    expect(url).toContain("/screen");
    expect(init.method).toBe("POST");
    const body = JSON.parse(init.body);
    expect(body.participant_id).toBe("P01");
    expect(body.overwrite).toBe(true);
    expect(body.payload.nback.soa_ms).toBe(2500);
  });

  it("getScreenSummary GETs /screen", async () => {
    global.fetch = mockFetch(200, { n_screened: 0, min_cohort: 3, hcf_active: false, screen_version: 1, screens: [] });
    const s = await getScreenSummary();
    expect(s.hcf_active).toBe(false);
    expect((global.fetch as any).mock.calls[0][0]).toContain("/screen");
  });

  it("getResearchContext GETs the export context", async () => {
    global.fetch = mockFetch(200, { bundle_version: "research-bundle-v1", counts: {} });
    const ctx = await getResearchContext();
    expect(ctx.bundle_version).toBe("research-bundle-v1");
    expect((global.fetch as any).mock.calls[0][0]).toContain("/exports/research-context");
  });

  it("downloadResearchBundle POSTs figure option JSON", async () => {
    const blob = new Blob(["zip"], { type: "application/zip" });
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      blob: async () => blob,
      json: async () => ({}),
    } as Response);
    await downloadResearchBundle([{ name: "q1", option: { xAxis: { type: "value" } } }]);
    const [url, init] = (global.fetch as any).mock.calls[0];
    expect(url).toContain("/exports/research-bundle");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body).figures[0].name).toBe("q1");
  });
});
