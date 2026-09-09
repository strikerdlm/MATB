import { operationalObjects } from "./operational-objects";
import { renderScheduler } from "./render-scheduler";
import { CameraController } from "./camera-controller";
import type { Entity } from "./state";
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
export function drone(): THREE.Group {
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
export function disposeTree(root: THREE.Object3D) {
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
  transitionMs?: number;
  focus?: Entity | null;
  onCameraEvent?: (kind: string, pose: CameraPose, mode: CameraMode) => void;
  onTargetLost?: () => void;
  onViewport?: (viewport: { width: number; height: number; dpr: number }) => void;
  frozen: boolean;
  onFailure: () => void;
  onRender?: (elapsed: number, pose: CameraPose) => void;
  replayPose?: CameraPose;
  initialPose?: CameraPose;
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
  const motion = new CameraController();
  let motionFrame = 0;
  const pose = (): CameraPose => ({ camera_position: camera.position.toArray(), camera_quaternion: camera.quaternion.toArray(), fov: camera.fov, aspect: camera.aspect, controls_target: controls.target.toArray() });
  const applyPose = (value: CameraPose) => { camera.position.fromArray(value.camera_position); camera.quaternion.fromArray(value.camera_quaternion); camera.fov = value.fov ?? 55; if (value.controls_target) controls.target.fromArray(value.controls_target); camera.updateProjectionMatrix(); };
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
    disposed = false;
  const labels = new Map<string, HTMLButtonElement>();
  const renderTimes: number[] = [];
  const submission = renderScheduler(submitFrame);
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
  if (initial.initialPose && initial.cameraMode === "overview") {
    applyPose(initial.initialPose);
    options.onCameraEvent?.("camera", pose(), initial.cameraMode);
  }
  const operational = operationalObjects(dynamic, staticLayer,
    (point, height) => missionToWorld(point, elevationAt(grid, point) + height), drone, disposeTree);
  const hiddenAircraft = () => options.cameraMode === "drone"
    ? options.selectedAircraftId ?? Object.keys(options.snapshot.aircraft)[0] : null;
  function rebuild() { operational.update(options.snapshot, options.layers, hiddenAircraft()); }
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
  function render() { submission.request(); }
  function submitFrame() {
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
      fov: camera.fov, aspect: camera.aspect,
      controls_target: controls.target.toArray(),
    });
  }
  function follow() {
    if (options.cameraMode === "overview") return;
    if (options.focus?.category === "observed") {
      const marker = observed.root.children.find(child => child.userData.trafficId === options.focus?.id);
      if (!marker) { options = { ...options, cameraMode: "overview", focus: null }; motion.cancel(); options.onTargetLost?.(); return; }
      camera.position.copy(marker.position).add(new THREE.Vector3(0, 350, 500));
      camera.lookAt(marker.position);
      return;
    }
    if (options.focus?.category === "contact") return;
    const id = options.focus?.id ?? options.selectedAircraftId;
    const aircraft = id
      ? options.snapshot.aircraft[id]
      : Object.values(options.snapshot.aircraft)[0];
    if (!aircraft) { if (id) { options = { ...options, cameraMode: "overview", focus: null }; motion.cancel(); options.onTargetLost?.(); } return; }
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
  function stopMotion(kind = "transition_cancel") {
    cancelAnimationFrame(motionFrame);
    if (motion.cancel()) options.onCameraEvent?.(kind, pose(), options.cameraMode);
  }
  function animateMotion(now: number) {
    if (disposed || options.frozen || options.replayPose) { stopMotion(); return; }
    const value = motion.sample(now);
    if (value) { applyPose(value); render(); }
    if (motion.owner === "transition") motionFrame = requestAnimationFrame(animateMotion);
    else options.onCameraEvent?.("transition_end", pose(), options.cameraMode);
  }
  function update(next: SceneOptions) {
    const changed = options.cameraMode !== next.cameraMode || (next.cameraMode !== "overview" && JSON.stringify(options.focus) !== JSON.stringify(next.focus));
    const from = pose();
    options = next;
    controls.enabled = !options.frozen && !options.replayPose;
    rebuild();
    geography.update(options.geographicLayers ?? []);
    observed.update(options.traffic, observedElapsed(options.snapshot), options.selectedTrafficId);
    if (options.replayPose) { stopMotion(); motion.cancel("replay"); applyPose(options.replayPose); render(); return; }
    if (options.frozen) { stopMotion(); render(); return; }
    if (changed) {
      stopMotion();
      if (options.cameraMode === "overview") reset(); else follow();
      const to = pose();
      motion.begin(from, to, performance.now(), options.transitionMs ?? 0, options.cameraMode === "overview" ? "manual" : options.cameraMode);
      if (motion.owner === "transition") {
        applyPose(from);
        options.onCameraEvent?.("transition_start", from, options.cameraMode);
        motionFrame = requestAnimationFrame(animateMotion);
      } else options.onCameraEvent?.("transition_end", to, options.cameraMode);
    } else if (motion.owner !== "transition") follow();
    render();
  }
  const manual = () => {
    if (options.frozen || options.replayPose) return;
    const automated = options.cameraMode !== "overview" || motion.owner === "transition";
    stopMotion();
    options = { ...options, cameraMode: "overview" };
    motion.cancel("manual");
    if (automated) {
      const distance = Math.max(100, camera.position.distanceTo(controls.target));
      controls.target.copy(camera.position).add(new THREE.Vector3(0, 0, -distance).applyQuaternion(camera.quaternion));
      options.onCameraEvent?.("transition_cancel", pose(), "overview");
    }
  };
  const manualEnd = () => {
    if (!options.frozen && !options.replayPose) options.onCameraEvent?.("camera", pose(), options.cameraMode);
  };
  const raycaster = new THREE.Raycaster();
  let down: [number, number] | null = null;
  const pointerDown = (e: PointerEvent) => {
    manual();
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
      .find((h) => {
        if (!(h.object instanceof THREE.Mesh)) return false;
        for (let object: THREE.Object3D | null = h.object; object; object = object.parent) if (!object.visible) return false;
        return true;
      });
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
    if (options.frozen || options.replayPose) return;
    if (!["0", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "+", "=", "-"].includes(event.key)) return;
    manual();
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
    manualEnd();
  };
  const lost = (event: Event) => {
    event.preventDefault();
    stopMotion();
    options.onFailure();
  };
  const resize = new ResizeObserver(() => {
    const width = Math.max(1, host.clientWidth),
      height = Math.max(1, host.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    renderer.setSize(width, height);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    options.onViewport?.({ width, height, dpr: renderer.getPixelRatio() });
    render();
  });
  resize.observe(host);
  controls.addEventListener("change", render);
  controls.addEventListener("end", manualEnd);
  renderer.domElement.addEventListener("wheel", manual, { capture: true });
  renderer.domElement.addEventListener("pointerdown", pointerDown);
  renderer.domElement.addEventListener("click", click);
  renderer.domElement.addEventListener("keydown", key);
  renderer.domElement.addEventListener("webglcontextlost", lost);
  update(initial);
  submission.flush(); // Readiness requires one completed CPU submission.
  function observedElapsed(snapshot: SceneOptions["snapshot"]) {
    return options.traffic ? Math.max(0, snapshot.simulation_time_ms - (options.traffic.simulation_time_ms ?? snapshot.simulation_time_ms)) : options.trafficElapsedMs ?? 0;
  }
  return {
    update,
    updateInterpolatedSnapshot: (snapshot: SceneOptions["snapshot"]) => {
      if (disposed || options.frozen || options.replayPose || snapshot.block_id !== options.snapshot.block_id || snapshot.state_version !== options.snapshot.state_version) return;
      options = { ...options, snapshot };
      operational.transforms(snapshot, hiddenAircraft());
      observed.update(options.traffic, observedElapsed(snapshot), options.selectedTrafficId);
      if (motion.owner !== "transition") { follow(); render(); }
    },
    reset: () => {
      stopMotion();
      reset();
      render();
      manualEnd();
    },
    metrics: () => ({
      calls: renderer.info.render.calls,
      triangles: renderer.info.render.triangles,
      memory: { ...renderer.info.memory },
      renderCount,
      objectLifecycle: operational.metrics(),
      gpuCompletionMs: null,
      physicalDisplayOnsetMs: null,
      device,
      dpr: renderer.getPixelRatio(),
      cpuRenderP95Ms:
        [...renderTimes].sort((a, b) => a - b)[
          Math.floor(renderTimes.length * 0.95)
        ] ?? 0,
    }),
    dispose: () => {
      stopMotion();
      disposed = true;
      submission.dispose();
      resize.disconnect();
      controls.removeEventListener("change", render);
      controls.removeEventListener("end", manualEnd);
      renderer.domElement.removeEventListener("wheel", manual, { capture: true });
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
