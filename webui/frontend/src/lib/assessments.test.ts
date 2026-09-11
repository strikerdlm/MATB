import { afterEach, expect, it, vi } from "vitest";
import {
  createOccasion,
  createAttempt,
  startAttempt,
  repeatAttempt,
  getAttemptRaw,
  interruptAttempt,
} from "./assessments";

afterEach(() => vi.unstubAllGlobals());
it("preserves explicit occasion, repeat and raw evidence identities across requests", async () => {
  const calls: { path: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, options: RequestInit) => {
      calls.push({
        path,
        body: options?.body ? JSON.parse(String(options.body)) : null,
      });
      return new Response(JSON.stringify({ id: "opaque-id" }), { status: 200 });
    }),
  );
  await createOccasion({
    participant_id: "P01",
    visit_id: 7,
    instrument: "screen",
    phase: "post",
    order: 3,
  });
  await createAttempt("occasion-A", "study");
  await startAttempt("attempt-A");
  await repeatAttempt("attempt-A", "study", "interruption reviewed");
  await getAttemptRaw("attempt-B");
  expect(calls.map((c) => c.path.split("/assessments")[1])).toEqual([
    "/occasions",
    "/occasions/occasion-A/attempts",
    "/attempts/attempt-A/start",
    "/attempts/attempt-A/repeat",
    "/attempts/attempt-B/raw",
  ]);
  expect(calls[0].body).toEqual({
    participant_id: "P01",
    visit_id: 7,
    instrument: "screen",
    phase: "post",
    order: 3,
  });
  expect(calls[3].body).toEqual({
    execution_purpose: "study",
    reason: "interruption reviewed",
  });
});

it("keeps the bounded unknown-interruption write alive across browser navigation", async () => {
  const fetcher = vi.fn(
    async () =>
      new Response(JSON.stringify({ id: "attempt-A" }), { status: 200 }),
  );
  vi.stubGlobal("fetch", fetcher);
  await interruptAttempt("attempt-A", "unknown");
  expect(fetcher).toHaveBeenCalledWith(
    expect.stringContaining("/attempts/attempt-A/interrupt"),
    expect.objectContaining({
      method: "POST",
      keepalive: true,
      body: JSON.stringify({ category: "unknown" }),
    }),
  );
});
