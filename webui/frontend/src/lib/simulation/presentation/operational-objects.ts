import * as THREE from "three";
import type { WorldSnapshot, PointMM } from "@/types/simulation";
import { headingRadians } from "./contracts";

type WorldPosition = (point: PointMM, height: number) => [number, number, number];
type Layers = { routes?: boolean; contacts?: boolean; coverage?: boolean };

/** Each object owns its resources. Removing a contact cannot dispose an aircraft. */
export class ObjectRegistry {
  readonly objects = new Map<string, THREE.Object3D>();
  created = 0;
  disposed = 0;
  constructor(readonly root: THREE.Group, private readonly release: (object: THREE.Object3D) => void) {}
  sync<T>(rows: T[], id: (row: T) => string, create: (row: T) => THREE.Object3D, update: (object: THREE.Object3D, row: T) => void) {
    const present = new Set<string>();
    for (const row of rows) {
      const key = id(row); present.add(key);
      let object = this.objects.get(key);
      if (!object) {
        object = create(row); this.objects.set(key, object); this.root.add(object); this.created++;
      }
      update(object, row);
    }
    for (const [key, object] of this.objects) if (!present.has(key)) {
      this.root.remove(object); this.release(object); this.objects.delete(key); this.disposed++;
    }
  }
}

export function operationalObjects(dynamic: THREE.Group, fixed: THREE.Group,
  world: WorldPosition, makeAircraft: () => THREE.Group, release: (object: THREE.Object3D) => void) {
  const aircraftRoot = new THREE.Group(), contactRoot = new THREE.Group(), routesRoot = new THREE.Group();
  const boundaries = new THREE.Group(), coverage = new THREE.Group();
  dynamic.add(aircraftRoot, contactRoot); fixed.add(routesRoot, boundaries, coverage);
  const aircraft = new ObjectRegistry(aircraftRoot, release), contacts = new ObjectRegistry(contactRoot, release);
  const routes = new ObjectRegistry(routesRoot, release);
  let boundaryKey = "", coverageKey = "", boundaryRebuilds = 0, coverageRebuilds = 0;
  function line(points: PointMM[], color: number, closed = false) {
    const coords = points.map(p => new THREE.Vector3(...world(p, 12)));
    if (closed && coords.length) coords.push(coords[0]);
    return new THREE.Line(new THREE.BufferGeometry().setFromPoints(coords), new THREE.LineBasicMaterial({ color, depthTest: false }));
  }
  function transforms(state: WorldSnapshot, hiddenAircraft?: string | null) {
    for (const item of Object.values(state.aircraft)) {
      const object = aircraft.objects.get(item.aircraft_id);
      if (!object) continue;
      object.position.set(...world(item.position, (item.altitude_mm ?? 120000) / 1000));
      object.rotation.y = headingRadians(item.heading_mdeg);
      object.visible = item.aircraft_id !== hiddenAircraft;
    }
  }
  function update(state: WorldSnapshot, layers: Layers = {}, hiddenAircraft?: string | null) {
    aircraft.sync(Object.values(state.aircraft), a => a.aircraft_id, a => {
      const object = makeAircraft(); object.name = a.aircraft_id; object.userData = { aircraftId: a.aircraft_id }; return object;
    }, () => {});
    transforms(state, hiddenAircraft);
    contacts.sync(Object.values(state.contacts).filter(c => c.position && c.evidence !== "NONE"), c => c.contact_id,
      c => { const marker = new THREE.Mesh(new THREE.OctahedronGeometry(35), new THREE.MeshBasicMaterial({ color: 0xffd166, depthTest: false }));
        marker.userData = { contactId: c.contact_id }; return marker; },
      (marker, c) => { marker.position.set(...world(c.position!, 45)); });
    contactRoot.visible = layers.contacts !== false;
    routesRoot.visible = layers.routes !== false;
    routes.sync(Object.values(state.aircraft), a => a.aircraft_id, a => line(a.route, 0x71e2ed), (object, a) => {
      const key = JSON.stringify(a.route);
      if (object.userData.route === key) return;
      const route = object as THREE.Line;
      route.geometry.dispose(); route.geometry = new THREE.BufferGeometry().setFromPoints(a.route.map(p => new THREE.Vector3(...world(p, 12))));
      object.userData.route = key;
    });
    const nextBoundaries = JSON.stringify([state.scenario_sha256, state.sectors, state.restricted_zones]);
    if (boundaryKey !== nextBoundaries) {
      boundaryKey = nextBoundaries; release(boundaries); boundaries.clear(); boundaryRebuilds++;
      for (const points of Object.values(state.sectors)) boundaries.add(line(points, 0x55ddbb, true));
      for (const points of Object.values(state.restricted_zones)) boundaries.add(line(points, 0xff6688, true));
    }
    coverage.visible = layers.coverage !== false;
    const nextCoverage = JSON.stringify(state.coverage);
    if (coverageKey !== nextCoverage) {
      coverageKey = nextCoverage; release(coverage); coverage.clear(); coverageRebuilds++;
      const points: THREE.Vector3[] = [];
      for (const sector of Object.values(state.coverage.sectors)) for (const [x, y] of sector.covered_cells) {
        const point = { x_mm: state.coverage.origin.x_mm + (x + .5) * state.coverage.grid_cell_mm,
          y_mm: state.coverage.origin.y_mm + (y + .5) * state.coverage.grid_cell_mm };
        points.push(new THREE.Vector3(...world(point, 8)));
      }
      if (points.length) coverage.add(new THREE.Points(new THREE.BufferGeometry().setFromPoints(points), new THREE.PointsMaterial({ color: 0x55ffaa, size: 20 })));
    }
  }
  return { update, transforms, aircraft, contacts, routes,
    metrics: () => ({ aircraftCreated: aircraft.created, aircraftDisposed: aircraft.disposed,
      contactsCreated: contacts.created, contactsDisposed: contacts.disposed, boundaryRebuilds, coverageRebuilds }) };
}
