import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { PresentationSetup } from "./PresentationSetup";
vi.mock("@/lib/simulation/api", () => ({
  listPresentationScenes: async () => [
    {
      id: "pilot",
      title: "Pilot",
      sha256: "abc",
      origin: { lat: 4, lon: -74 },
    },
  ],
}));
vi.mock("@/lib/geography/api", () => ({ trafficRecordings: async () => [] }));
const config = {
  version: 1 as const,
  scene_id: "pilot",
  scene_sha256: "abc",
  blocks: {},
  camera: "overview" as const,
};
describe("traffic conditions", () => {
  it("offers live traffic only in technical mode", async () => {
    const { rerender } = render(
      <PresentationSetup locale="en" value={config} onChange={() => {}} />,
    );
    await waitFor(() =>
      expect(screen.getByRole("option", { name: "Pilot" })).toBeInTheDocument(),
    );
    expect(screen.queryByRole("option", { name: "Live" })).toBeNull();
    rerender(
      <PresentationSetup
        locale="en"
        value={config}
        onChange={() => {}}
        allowLive
      />,
    );
    expect(screen.getByRole("option", { name: "Live" })).toBeInTheDocument();
  });
});
