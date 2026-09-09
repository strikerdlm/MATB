import {
  geographicLayers,
  observedTrafficLayer,
} from "@/lib/geography/scene-layers";
import type { GeographyLayer, TrafficFrame } from "@/lib/geography/types";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import type { MissionMapProps } from "@/components/mission/map/MissionMap";
import {
  elevationAt,
  headingRadians,
  missionToWorld,
  worldToMission,
  type CameraMode,
  type CameraPose,
  type SceneAssets,
} from "./contracts";

/** Meshes are schematic, generated in metres; no imported aircraft models. */
function drone(): THREE.Group {
  const root = new THREE.Group();
  const body = new THREE.Mesh(
    new THREE.BoxGeometry(2, 0.6, 3),
    new THREE.MeshStandardMaterial({ color: 0xe0efec }),
  );
  root.add(body);
  for (const x of [-2, 2])
    for (const z of [-2, 2]) {
      const rotor = new THREE.Mesh(
        new THREE.CylinderGeometry(1.1, 1.1, 0.12, 12),
        body.material,
      );
      rotor.position.set(x, 0.5, z);
      root.add(rotor);
      const arm = new THREE.Mesh(
        new THREE.BoxGeometry(0.3, 0.3, 3),
        body.material,
      );
      arm.position.set(x / 2, 0, z / 2);
      arm.rotation.y = x * z > 0 ? Math.PI / 4 : -Math.PI / 4;
      root.add(arm);
    }
  root.scale.setScalar(12); // Explicit display enlargement, not physical aircraft dimensions.
  return root;
}
function disposeTree(root: THREE.Object3D) {
  const geometries = new Set<THREE.BufferGeometry>(),
    materials = new Set<THREE.Material>();
  root.traverse((object) => {
    if (
      object instanceof THREE.Mesh ||
      object instanceof THREE.Line ||
      object instanceof THREE.Points
    ) {
      geometries.add(object.geometry);
      for (const material of Array.isArray(object.material)
        ? object.material
        : [object.material])
        materials.add(material);
    }
  });
  geometries.forEach((g) => g.dispose());
  materials.forEach((m) => m.dispose());
}
export interface SceneOptions extends MissionMapProps {
  traffic?: TrafficFrame | null;
  trafficElapsedMs?: number;
  selectedTrafficId?: string | null;
  onSelectTraffic?: (id: string) => void;
  geographicLayers?: GeographyLayer[];
  cameraMode: CameraMode;
  frozen: boolean;
  onFailure: () => void;
  onRender?: (elapsed: number, pose: CameraPose) => void;
  replayPose?: CameraPose;
  layers?: { routes: boolean; coverage: boolean; contacts: boolean };
}
export async function createMissionScene(
  host: HTMLDivElement,
  assets: SceneAssets,
  initial: SceneOptions,
) {
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.domElement.tabIndex = 0;
  renderer.domElement.setAttribute(
    "aria-label",
    initial.locale === "en" ? "3D mission view" : "Vista de misión 3D",
  );
  host.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x101d2b);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x778866, 2));
  const sun = new THREE.DirectionalLight(0xffffff, 2);
  sun.position.set(4000, 10000, 2000);
  scene.add(sun);
  const camera = new THREE.PerspectiveCamera(55, 1, 1, 70000);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = false;
  controls.maxPolarAngle = Math.PI * 0.48;
  controls.minDistance = 100;
  controls.maxDistance = 26000;
  const { elevation: grid } = assets;
  const geometry = new THREE.BufferGeometry(),
    vertices: number[] = [],
    indices: number[] = [],
    uv: number[] = [];
  for (let y = 0; y < grid.height; y++)
    for (let x = 0; x < grid.width; x++) {
      vertices.push(
        -8000 + (x / (grid.width - 1)) * 16000,
        grid.values[y * grid.width + x],
        6000 - (y / (grid.height - 1)) * 12000,
      );
      uv.push(x / (grid.width - 1), y / (grid.height - 1));
      if (x < grid.width - 1 && y < grid.height - 1) {
        const i = y * grid.width + x;
        indices.push(
          i,
          i + 1,
          i + grid.width,
          i + 1,
          i + grid.width + 1,
          i + grid.width,
        );
      }
    }
  geometry.setAttribute(
    "position",
    new THREE.Float32BufferAttribute(vertices, 3),
  );
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  const texture = new THREE.Texture();
  texture.colorSpace = THREE.SRGBColorSpace;
  const terrain = new THREE.Mesh(
    geometry,
    new THREE.MeshStandardMaterial({
      map: texture,
      roughness: 1,
      alphaTest: 0.5,
    }),
  );
  scene.add(terrain);
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(assets.imagery, {
      imageOrientation: "flipY",
    });
    texture.image = bitmap;
    texture.needsUpdate = true;
  } catch (error) {
    controls.dispose();
    disposeTree(scene);
    texture.dispose();
    renderer.dispose();
    renderer.domElement.remove();
    throw error;
  }
  const geography = geographicLayers(assets),
    observed = observedTrafficLayer(assets);
  scene.add(geography.root, observed.root);
  const staticLayer = new THREE.Group(),
    dynamic = new THREE.Group();
  scene.add(staticLayer, dynamic);
  let options = initial,
    disposed = false,
    revision = "",
    animation = 0;
  const labels = new Map<string, HTMLButtonElement>();
  const renderTimes: number[] = [];
  let renderCount = 0;
  const gl = renderer.getContext(),
    debug = gl.getExtension("WEBGL_debug_renderer_info");
  const device = debug
    ? String(gl.getParameter(debug.UNMASKED_RENDERER_WEBGL))
    : String(gl.getParameter(gl.RENDERER));
  const center = new THREE.Vector3(
    0,
    elevationAt(grid, { x_mm: 6000000, y_mm: 4000000 }),
    0,
  );
  function reset() {
    camera.position.copy(center).add(new THREE.Vector3(0, 10500, 8000));
    controls.target.copy(center);
    controls.update();
  }
  reset();
  function polyline(
    points: { x_mm: number; y_mm: number }[],
    color: number,
    parent: THREE.Group,
    closed = false,
  ) {
    const coords = points.map(
      (p) => new THREE.Vector3(...missionToWorld(p, elevationAt(grid, p) + 12)),
    );
    if (closed && coords.length) coords.push(coords[0]);
    if (coords.length < 2) return;
    parent.add(
      new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(coords),
        new THREE.LineBasicMaterial({ color, depthTest: false }),
      ),
    );
  }
  function rebuild() {
    const objectKey = JSON.stringify([
      options.snapshot.block_id,
      Object.keys(options.snapshot.aircraft),
      options.snapshot.contacts,
    ]);
    const rebuildObjects = dynamic.userData.key !== objectKey;
    if (rebuildObjects) {
      disposeTree(dynamic);
      dynamic.clear();
      dynamic.userData.key = objectKey;
    }
    const state = options.snapshot;
    for (const aircraft of Object.values(state.aircraft)) {
      const mesh = dynamic.getObjectByName(aircraft.aircraft_id) ?? drone();
      mesh.name = aircraft.aircraft_id;
      mesh.userData = { aircraftId: aircraft.aircraft_id };
      mesh.position.set(
        ...missionToWorld(
          aircraft.position,
          elevationAt(grid, aircraft.position) +
            (aircraft.altitude_mm ?? 120000) / 1000,
        ),
      );
      mesh.rotation.y = headingRadians(aircraft.heading_mdeg);
      mesh.visible =
        options.cameraMode !== "drone" ||
        aircraft.aircraft_id !==
          (options.selectedAircraftId ?? Object.keys(state.aircraft)[0]);
      dynamic.add(mesh);
    }
    if (rebuildObjects)
      for (const contact of Object.values(state.contacts)) {
        if (!contact.position || contact.evidence === "NONE") continue;
        const marker = new THREE.Mesh(
          new THREE.OctahedronGeometry(35),
          new THREE.MeshBasicMaterial({ color: 0xffd166, depthTest: false }),
        );
        marker.userData = { contactId: contact.contact_id };
        marker.position.set(
          ...missionToWorld(
            contact.position,
            elevationAt(grid, contact.position) + 45,
          ),
        );
        dynamic.add(marker);
      }
    for (const item of dynamic.children)
      if (item.userData.contactId)
        item.visible = options.layers?.contacts !== false;
    const key = JSON.stringify([
      state.scenario_sha256,
      state.block_id,
      state.coverage,
      options.layers,
      Object.values(state.aircraft).map((a) => a.route),
    ]);
    if (key !== revision) {
      revision = key;
      disposeTree(staticLayer);
      staticLayer.clear();
      if (options.layers?.routes !== false)
        for (const aircraft of Object.values(state.aircraft))
          polyline(aircraft.route, 0x71e2ed, staticLayer);
      for (const points of Object.values(state.sectors))
        polyline(points, 0x55ddbb, staticLayer, true);
      for (const points of Object.values(state.restricted_zones))
        polyline(points, 0xff6688, staticLayer, true);
      if (options.layers?.coverage !== false) {
        const points: THREE.Vector3[] = [];
        for (const sector of Object.values(state.coverage.sectors))
          for (const [x, y] of sector.covered_cells) {
            const p = {
              x_mm:
                state.coverage.origin.x_mm +
                (x + 0.5) * state.coverage.grid_cell_mm,
              y_mm:
                state.coverage.origin.y_mm +
                (y + 0.5) * state.coverage.grid_cell_mm,
            };
            points.push(
              new THREE.Vector3(...missionToWorld(p, elevationAt(grid, p) + 8)),
            );
          }
        if (points.length) {
          const dots = new THREE.Points(
            new THREE.BufferGeometry().setFromPoints(points),
            new THREE.PointsMaterial({ color: 0x55ffaa, size: 20 }),
          );
          staticLayer.add(dots);
        }
      }
    }
  }
  function updateLabels() {
    const ids = new Set<string>();
    Object.values(options.snapshot.aircraft).forEach((aircraft, index) => {
      const id = aircraft.aircraft_id;
      ids.add(id);
      let label = labels.get(id);
      if (!label) {
        label = document.createElement("button");
        label.type = "button";
        label.textContent = id;
        label.style.cssText =
          "position:absolute;z-index:2;padding:3px 5px;border:1px solid #71e2ed;background:#071218;color:#b9f5ff;font:11px monospace;transform:translate(-50%,-100%);";
        label.addEventListener("click", () => options.onSelectAircraft?.(id));
        labels.set(id, label);
        host.appendChild(label);
      }
      const mesh = dynamic.getObjectByName(id);
      if (!mesh) return;
      const projected = mesh.position.clone().project(camera);
      label.style.display =
        options.cameraMode === "drone" ||
        Math.abs(projected.x) > 1 ||
        Math.abs(projected.y) > 1 ||
        projected.z > 1
          ? "none"
          : "block";
      label.style.left = `${((projected.x + 1) / 2) * host.clientWidth}px`;
      label.style.top = `${((1 - projected.y) / 2) * host.clientHeight - 8 - (index % 4) * 19}px`;
      label.style.borderColor =
        id === options.selectedAircraftId ? "#ffdd66" : "#71e2ed";
      label.disabled = options.frozen;
      label.setAttribute(
        "aria-pressed",
        String(id === options.selectedAircraftId),
      );
    });
    for (const [id, label] of labels)
      if (!ids.has(id)) {
        label.remove();
        labels.delete(id);
      }
  }
  function render() {
    if (disposed) return;
    const started = performance.now();
    renderer.render(scene, camera);
    updateLabels();
    renderCount++;
    renderTimes.push(performance.now() - started);
    if (renderTimes.length > 512) renderTimes.shift();
    options.onRender?.(performance.now() - started, {
      camera_position: camera.position.toArray(),
      camera_quaternion: camera.quaternion.toArray(),
    });
  }
  function follow() {
    if (options.cameraMode === "overview") return;
    const aircraft = options.selectedAircraftId
      ? options.snapshot.aircraft[options.selectedAircraftId]
      : Object.values(options.snapshot.aircraft)[0];
    if (!aircraft) return;
    const target = new THREE.Vector3(
      ...missionToWorld(
        aircraft.position,
        elevationAt(grid, aircraft.position) +
          (aircraft.altitude_mm ?? 120000) / 1000,
      ),
    );
    const yaw = headingRadians(aircraft.heading_mdeg),
      direction = new THREE.Vector3(0, 0, -1).applyAxisAngle(
        new THREE.Vector3(0, 1, 0),
        yaw,
      );
    if (options.cameraMode === "drone") {
      camera.position.copy(target);
      camera.lookAt(
        target
          .clone()
          .addScaledVector(direction, 160)
          .add(new THREE.Vector3(0, -100, 0)),
      );
    } else {
      camera.position
        .copy(target)
        .addScaledVector(direction, -500)
        .add(new THREE.Vector3(0, 350, 0));
      camera.lookAt(target);
    }
  }
  function update(next: SceneOptions) {
    const changed = options.cameraMode !== next.cameraMode;
    options = next;
    controls.enabled = options.cameraMode === "overview" && !options.frozen;
    if (changed && options.cameraMode === "overview") reset();
    rebuild();
    geography.update(options.geographicLayers ?? []);
    observed.update(
      options.traffic,
      options.trafficElapsedMs ?? 0,
      options.selectedTrafficId,
    );
    follow();
    if (options.replayPose) {
      camera.position.fromArray(options.replayPose.camera_position);
      camera.quaternion.fromArray(options.replayPose.camera_quaternion);
    }
    render();
  }
  const raycaster = new THREE.Raycaster();
  let down: [number, number] | null = null;
  const pointerDown = (e: PointerEvent) => {
    down = [e.clientX, e.clientY];
  };
  const click = (e: MouseEvent) => {
    if (
      !down ||
      Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 5 ||
      options.frozen
    )
      return;
    const rect = renderer.domElement.getBoundingClientRect();
    raycaster.setFromCamera(
      new THREE.Vector2(
        ((e.clientX - rect.left) / rect.width) * 2 - 1,
        (-(e.clientY - rect.top) / rect.height) * 2 + 1,
      ),
      camera,
    );
    const hit = raycaster
      .intersectObjects([...dynamic.children, ...observed.root.children], true)
      .find((h) => h.object instanceof THREE.Mesh);
    if (hit) {
      let obj: THREE.Object3D | null = hit.object;
      while (
        obj &&
        !obj.userData.aircraftId &&
        !obj.userData.contactId &&
        !obj.userData.trafficId
      )
        obj = obj.parent;
      if (obj?.userData.trafficId) {
        options.onSelectTraffic?.(obj.userData.trafficId);
        return;
      }
      if (obj?.userData.aircraftId) {
        options.onSelectAircraft?.(obj.userData.aircraftId);
        return;
      }
      if (obj?.userData.contactId) {
        options.onSelectContact?.(obj.userData.contactId);
        return;
      }
    }
    if (options.readOnly || !options.waypointAircraftId) return;
    const ground = raycaster.intersectObject(terrain)[0];
    if (!ground) return;
    const point = worldToMission(
      ground.point.x,
      ground.point.z,
      options.snapshot.terrain.bounds,
    );
    if (point) options.onSetWaypoint?.(options.waypointAircraftId, point);
  };
  const key = (event: KeyboardEvent) => {
    if (options.frozen || options.cameraMode !== "overview") return;
    if (event.key === "0") reset();
    else if (
      ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)
    ) {
      const dx =
        event.key === "ArrowLeft" ? -200 : event.key === "ArrowRight" ? 200 : 0;
      const dz =
        event.key === "ArrowUp" ? -200 : event.key === "ArrowDown" ? 200 : 0;
      camera.position.x += dx;
      camera.position.z += dz;
      controls.target.x += dx;
      controls.target.z += dz;
    } else if (["+", "=", "-"].includes(event.key))
      camera.position
        .sub(controls.target)
        .multiplyScalar(event.key === "-" ? 1.1 : 0.9)
        .add(controls.target);
    else return;
    event.preventDefault();
    controls.update();
    render();
  };
  const lost = (event: Event) => {
    event.preventDefault();
    options.onFailure();
  };
  const resize = new ResizeObserver(() => {
    const width = Math.max(1, host.clientWidth),
      height = Math.max(1, host.clientHeight);
    renderer.setSize(width, height);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    render();
  });
  resize.observe(host);
  controls.addEventListener("change", render);
  renderer.domElement.addEventListener("pointerdown", pointerDown);
  renderer.domElement.addEventListener("click", click);
  renderer.domElement.addEventListener("keydown", key);
  renderer.domElement.addEventListener("webglcontextlost", lost);
  update(initial);
  animation = requestAnimationFrame(render);
  return {
    update,
    reset: () => {
      reset();
      render();
    },
    metrics: () => ({
      calls: renderer.info.render.calls,
      triangles: renderer.info.render.triangles,
      memory: { ...renderer.info.memory },
      renderCount,
      device,
      dpr: renderer.getPixelRatio(),
      cpuRenderP95Ms:
        [...renderTimes].sort((a, b) => a - b)[
          Math.floor(renderTimes.length * 0.95)
        ] ?? 0,
    }),
    dispose: () => {
      disposed = true;
      cancelAnimationFrame(animation);
      resize.disconnect();
      controls.removeEventListener("change", render);
      controls.dispose();
      renderer.domElement.removeEventListener("pointerdown", pointerDown);
      renderer.domElement.removeEventListener("click", click);
      renderer.domElement.removeEventListener("keydown", key);
      renderer.domElement.removeEventListener("webglcontextlost", lost);
      labels.forEach((label) => label.remove());
      labels.clear();
      disposeTree(scene);
      bitmap.close();
      texture.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    },
  };
}
