import { describe, it, expect, vi, beforeEach } from "vitest";
import { createParticipant, getTracker, ingestCsv, IngestError } from "@/lib/api";

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
});
