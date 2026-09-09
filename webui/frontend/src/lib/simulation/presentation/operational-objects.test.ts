import { describe, expect, it, vi } from "vitest";
import * as THREE from "three";
import { operationalObjects } from "./operational-objects";
import { preflightSnapshot } from "@/components/mission/presentation/MissionPresentation";
import type { WorldSnapshot } from "@/types/simulation";

function fixture(): WorldSnapshot {
  const state = preflightSnapshot("LOW");
  state.aircraft = { one: { aircraft_id: "one", position: { x_mm: 0, y_mm: 0 }, heading_mdeg: 0, route: [{ x_mm: 0, y_mm: 0 }, { x_mm: 10, y_mm: 10 }] } as WorldSnapshot["aircraft"][string] };
  return state;
}
describe("operational scene ownership", () => {
  it("retains aircraft, route and boundary objects while contacts and coverage change", () => {
    const released = vi.fn(), root = new THREE.Group(), fixed = new THREE.Group();
    const objects = operationalObjects(root, fixed, (p, h) => [p.x_mm, h, p.y_mm], () => new THREE.Group(), released);
    const state = fixture(); objects.update(state);
    const aircraft = objects.aircraft.objects.get("one"), route = objects.routes.objects.get("one");
    const changed = structuredClone(state);
    changed.contacts = { c: { contact_id: "c", position: { x_mm: 5, y_mm: 8 }, evidence: "OBSERVED" } as unknown as WorldSnapshot["contacts"][string] };
    changed.coverage.sectors = { sector: { covered_cells: [[1, 2]] } as unknown as WorldSnapshot["coverage"]["sectors"][string] };
    objects.update(changed);
    expect(objects.aircraft.objects.get("one")).toBe(aircraft);
    expect(objects.routes.objects.get("one")).toBe(route);
    expect(objects.metrics()).toMatchObject({ aircraftCreated: 1, aircraftDisposed: 0, boundaryRebuilds: 1, coverageRebuilds: 2 });
    changed.contacts.c.evidence = "NONE"; objects.update(changed);
    expect(objects.contacts.objects.size).toBe(0);
    expect(released).not.toHaveBeenCalledWith(aircraft);
  });
  it("updates only transforms during interpolation and does not mutate input state", () => {
    const objects = operationalObjects(new THREE.Group(), new THREE.Group(), (p, h) => [p.x_mm, h, p.y_mm], () => new THREE.Group(), () => {});
    const state = fixture(); objects.update(state);
    const counts = objects.metrics(); const before = JSON.stringify(state);
    objects.transforms(state, "one");
    expect(objects.metrics()).toEqual(counts);
    expect(JSON.stringify(state)).toBe(before);
    expect(objects.aircraft.objects.get("one")?.visible).toBe(false);
  });
});
