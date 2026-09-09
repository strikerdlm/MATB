import * as THREE from "three";
import {
  elevationAt,
  missionToWorld,
  headingRadians,
  type SceneAssets,
} from "@/lib/simulation/presentation/contracts";
import { toLocal, displayedTraffic } from "@/lib/geography/coordinates";
import type { GeographyLayer, TrafficFrame } from "@/lib/geography/types";
export function geographicLayers(assets: SceneAssets) {
  const root = new THREE.Group();
  const groups = new Map<string, THREE.Group>();
  for (const feature of assets.overlays?.features ?? []) {
    const name = String(feature.properties?.layer ?? "");
    if (!groups.has(name)) {
      const group = new THREE.Group();
      groups.set(name, group);
      root.add(group);
    }
    const parent = groups.get(name)!;
    const point = (p: GeoJSON.Position) => {
      const local = toLocal(p[0], p[1], assets.manifest.origin),
        b = assets.elevation.bounds_m;
      const bounded = {
        x_mm: Math.max(b[0] * 1000, Math.min(b[2] * 1000, local.x_mm)),
        y_mm: Math.max(b[1] * 1000, Math.min(b[3] * 1000, local.y_mm)),
      };
      return new THREE.Vector3(
        ...missionToWorld(local, elevationAt(assets.elevation, bounded) + 8),
      );
    };
    const geometry = feature.geometry;
    const colors: Record<string, number> = {
      roads: 0xc4b49a,
      rivers: 0x55aaff,
      boundaries: 0xb392dd,
      settlements: 0xe8eee6,
      airports: 0xffbb66,
    };
    if (geometry.type === "Point") {
      const mesh = new THREE.Mesh(
        new THREE.OctahedronGeometry(name === "airports" ? 45 : 20),
        new THREE.MeshBasicMaterial({ color: colors[name] ?? 0xffffff }),
      );
      mesh.position.copy(point(geometry.coordinates));
      parent.add(mesh);
    } else {
      const lines =
        geometry.type === "LineString"
          ? [geometry.coordinates]
          : geometry.type === "MultiLineString"
            ? geometry.coordinates
            : [];
      for (const line of lines)
        parent.add(
          new THREE.Line(
            new THREE.BufferGeometry().setFromPoints(line.map(point)),
            new THREE.LineBasicMaterial({
              color: colors[name] ?? 0xffffff,
              transparent: true,
              opacity: 0.75,
            }),
          ),
        );
    }
  }
  // Batch static overlay primitives by layer to keep draw calls bounded.
  groups.forEach((group) => {
    const vertices: number[] = [],
      points: number[] = [];
    let lineMaterial: THREE.LineBasicMaterial | undefined,
      pointColor = 0xffffff;
    for (const object of [...group.children]) {
      if (object instanceof THREE.Line) {
        const a = object.geometry.getAttribute("position");
        for (let i = 1; i < a.count; i++)
          vertices.push(
            a.getX(i - 1),
            a.getY(i - 1),
            a.getZ(i - 1),
            a.getX(i),
            a.getY(i),
            a.getZ(i),
          );
        lineMaterial ??= (object.material as THREE.LineBasicMaterial).clone();
      }
      if (object instanceof THREE.Mesh) {
        points.push(...object.position.toArray());
        pointColor = (
          object.material as THREE.MeshBasicMaterial
        ).color.getHex();
      }
      if (object instanceof THREE.Mesh || object instanceof THREE.Line) {
        object.geometry.dispose();
        (object.material as THREE.Material).dispose();
      }
      group.remove(object);
    }
    if (vertices.length) {
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
      group.add(new THREE.LineSegments(g, lineMaterial));
    }
    if (points.length) {
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(points, 3));
      group.add(
        new THREE.Points(
          g,
          new THREE.PointsMaterial({
            color: pointColor,
            size: 6,
            sizeAttenuation: false,
          }),
        ),
      );
    }
  });
  return {
    root,
    update: (layers: GeographyLayer[]) =>
      groups.forEach((group, name) => {
        group.visible = layers.includes(name as GeographyLayer);
      }),
  };
}
export function observedTrafficLayer(assets: SceneAssets) {
  const root = new THREE.Group(),
    markers = new Map<string, THREE.Group>();
  const histories = new Map<string, THREE.Vector3[]>();
  let lastFrame = "",
    lastTime = -1;
  function update(
    frame: TrafficFrame | null | undefined,
    elapsed: number,
    selected: string | null | undefined,
  ) {
    const tracks = displayedTraffic(frame, elapsed).filter(
      (t) =>
        t.orthometric_altitude_m !== null &&
        t.orthometric_altitude_m !== undefined,
    );
    const ids = new Set(tracks.map((t) => t.id));
    for (const [id, group] of markers)
      if (!ids.has(id)) {
        root.remove(group);
        group.traverse((obj) => {
          if (obj instanceof THREE.Mesh || obj instanceof THREE.Line) {
            obj.geometry.dispose();
            (obj.material as THREE.Material).dispose();
          }
        });
        markers.delete(id);
        histories.delete(id);
      }
    if (
      (frame?.discontinuity && frame.frame_id !== lastFrame) ||
      (frame?.simulation_time_ms ?? 0) < lastTime
    )
      histories.clear();
    lastTime = frame?.simulation_time_ms ?? 0;
    for (const track of tracks) {
      let group = markers.get(track.id);
      if (!group) {
        group = new THREE.Group();
        group.userData.trafficId = track.id;
        const geometry = new THREE.ConeGeometry(35, 110, 3);
        geometry.rotateX(-Math.PI / 2);
        group.add(
          new THREE.Mesh(
            geometry,
            new THREE.MeshBasicMaterial({ color: 0xffb15c, transparent: true }),
          ),
        );
        group.add(
          new THREE.Line(
            new THREE.BufferGeometry().setAttribute(
              "position",
              new THREE.Float32BufferAttribute(new Float32Array(30 * 3), 3),
            ),
            new THREE.LineBasicMaterial({
              color: 0xffb15c,
              transparent: true,
              opacity: 0.5,
            }),
          ),
        );
        root.add(group);
        markers.set(track.id, group);
      }
      const position = toLocal(track.lon, track.lat, assets.manifest.origin);
      const p = new THREE.Vector3(
        ...missionToWorld(position, track.orthometric_altitude_m!),
      );
      group.position.copy(p);
      const mesh = group.children[0] as THREE.Mesh<
        THREE.BufferGeometry,
        THREE.MeshBasicMaterial
      >;
      mesh.rotation.y = headingRadians((track.track_deg ?? 0) * 1000);
      mesh.material.color.setHex(track.id === selected ? 0xffffff : 0xffb15c);
      mesh.material.opacity = track.stale ? 0.45 : 1;
      if (frame?.frame_id !== lastFrame) {
        const history = histories.get(track.id) ?? [];
        history.push(p.clone());
        if (history.length > 30) history.shift();
        histories.set(track.id, history);
      }
      const trail = group.children[1] as THREE.Line;
      const points = histories.get(track.id) ?? [];
      const attribute = trail.geometry.getAttribute(
        "position",
      ) as THREE.BufferAttribute;
      points.forEach((v, i) =>
        attribute.setXYZ(i, v.x - p.x, v.y - p.y, v.z - p.z),
      );
      attribute.needsUpdate = true;
      trail.geometry.setDrawRange(0, points.length);
      trail.frustumCulled = false;
    }
    lastFrame = frame?.frame_id ?? "";
  }
  return { root, update };
}
