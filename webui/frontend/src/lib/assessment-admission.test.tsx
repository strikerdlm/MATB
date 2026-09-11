import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { useAssessmentAdmission } from "./assessment-admission";
import { startAttempt, getAttempt, interruptAttempt } from "./assessments";
vi.mock("./assessments", () => ({
  startAttempt: vi.fn(),
  getAttempt: vi.fn(),
  interruptAttempt: vi.fn().mockResolvedValue({}),
}));
beforeEach(() => vi.clearAllMocks());
it("does not admit browser timing until the actual server start resolves", async () => {
  let resolve!: (value: Awaited<ReturnType<typeof startAttempt>>) => void;
  vi.mocked(startAttempt).mockImplementation(
    () =>
      new Promise((r) => {
        resolve = r;
      }),
  );
  const { result, unmount } = renderHook(() =>
    useAssessmentAdmission({ attemptId: "a" }),
  );
  let pending!: Promise<unknown>;
  act(() => {
    pending = result.current.admit();
  });
  expect(result.current.pending).toBe(true);
  expect(result.current.admitted).toBeNull();
  await act(async () => {
    resolve({ id: "a" } as Awaited<ReturnType<typeof startAttempt>>);
    await pending;
  });
  expect(result.current.admitted?.attemptId).toBe("a");
  unmount();
  expect(interruptAttempt).toHaveBeenCalledWith("a", "unknown");
});
it("runtime setup reads identity and leaves timed admission to the authoritative controller", async () => {
  vi.mocked(getAttempt).mockResolvedValue({ id: "a" } as Awaited<
    ReturnType<typeof getAttempt>
  >);
  const { result, unmount } = renderHook(() =>
    useAssessmentAdmission({ attemptId: "a" }, { runtime: true }),
  );
  await act(async () => {
    await result.current.admit();
  });
  expect(getAttempt).toHaveBeenCalledWith("a");
  expect(startAttempt).not.toHaveBeenCalled();
  unmount();
  expect(interruptAttempt).not.toHaveBeenCalled();
});
it("denied admission leaves browser collection unavailable", async () => {
  vi.mocked(startAttempt).mockRejectedValue(new Error("Heavy worker active"));
  const { result } = renderHook(() =>
    useAssessmentAdmission({ attemptId: "a" }),
  );
  await act(async () => {
    await expect(result.current.admit()).rejects.toThrow("Heavy worker active");
  });
  expect(result.current.admitted).toBeNull();
  expect(result.current.pending).toBe(false);
});
