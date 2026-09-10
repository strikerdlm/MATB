import React from "react";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useSerializedPolling } from "@/lib/serialized-polling";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function Harness({ poll, resetKey = "session-1" }: { poll: () => Promise<string>; resetKey?: string }) {
  const polling = useSerializedPolling({
    enabled: true,
    poll,
    intervalMs: 60_000,
    resetKey,
    errorMessage: (reason) => reason instanceof Error ? reason.message : "poll failed",
  });
  return <>
    <output aria-label="value">{polling.value ?? "empty"}</output>
    <output aria-label="poll-error">{polling.pollingError ?? "none"}</output>
    <button onClick={() => void polling.refresh()}>Refresh</button>
    <button onClick={() => polling.acceptActionValue("action-new")}>Accept action</button>
  </>;
}

describe("useSerializedPolling", () => {
  beforeEach(() => vi.useRealTimers());

  it("serializes refreshes while one request is pending", async () => {
    const pending = deferred<string>();
    const poll = vi.fn(() => pending.promise);
    render(<Harness poll={poll} />);

    await act(async () => undefined);
    await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(poll).toHaveBeenCalledTimes(1);

    await act(async () => pending.resolve("first"));
    expect(screen.getByLabelText("value")).toHaveTextContent("first");
  });

  it("does not let an older poll overwrite a newer action response", async () => {
    const pending = deferred<string>();
    render(<Harness poll={() => pending.promise} />);
    await act(async () => undefined);

    await userEvent.click(screen.getByRole("button", { name: "Accept action" }));
    expect(screen.getByLabelText("value")).toHaveTextContent("action-new");

    await act(async () => pending.resolve("poll-old"));
    expect(screen.getByLabelText("value")).toHaveTextContent("action-new");
  });

  it("clears a polling error after polling succeeds without coupling action state", async () => {
    const poll = vi.fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce("fresh");
    render(<Harness poll={poll} />);

    expect(await screen.findByText("offline")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Accept action" }));
    expect(screen.getByLabelText("poll-error")).toHaveTextContent("offline");

    await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(await screen.findByText("fresh")).toBeInTheDocument();
    expect(screen.getByLabelText("poll-error")).toHaveTextContent("none");
  });
});
