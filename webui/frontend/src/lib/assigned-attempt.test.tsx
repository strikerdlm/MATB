import { renderHook, waitFor, act } from "@testing-library/react";
import { it, expect, vi } from "vitest";
import { useAssignedAttempt } from "./assigned-attempt";
const state = vi.hoisted(() => ({ query: "attempt=a" }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(state.query),
}));
vi.mock("./assessments", () => ({ getAttempt: vi.fn() }));
it("tracks same-path attempt navigation and drops stale responses without accepting spoofed identities", async () => {
  const { getAttempt } = await import("./assessments");
  let resolveA!: (value: unknown) => void;
  vi.mocked(getAttempt).mockImplementation((id) =>
    id === "a"
      ? new Promise((resolve) => {
          resolveA = resolve as never;
        })
      : Promise.resolve({ id } as never),
  );
  const hook = renderHook(() => useAssignedAttempt());
  state.query = "attempt=b";
  hook.rerender();
  await waitFor(() => expect(hook.result.current.attempt?.id).toBe("b"));
  await act(async () => resolveA({ id: "a" }));
  expect(hook.result.current.attempt?.id).toBe("b");
  state.query = "attempt=c";
  vi.mocked(getAttempt).mockResolvedValue({ id: "other" } as never);
  hook.rerender();
  await waitFor(() =>
    expect(hook.result.current.error).toMatch(/identity mismatch/),
  );
  expect(hook.result.current.attempt).toBeNull();
});
