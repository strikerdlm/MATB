import { Quaternion, Vector3 } from "three";
import type { CameraPose } from "./contracts";

export type CameraOwner = "manual" | "transition" | "follow" | "drone" | "replay";
export function interpolatePose(from: CameraPose, to: CameraPose, fraction: number): CameraPose {
  const t = Math.min(1, Math.max(0, fraction));
  const eased = t * t * (3 - 2 * t);
  return {
    camera_position: new Vector3().fromArray(from.camera_position).lerp(new Vector3().fromArray(to.camera_position), eased).toArray(),
    camera_quaternion: new Quaternion().fromArray(from.camera_quaternion).slerp(new Quaternion().fromArray(to.camera_quaternion), eased).toArray(),
    fov: (from.fov ?? 55) + ((to.fov ?? 55) - (from.fov ?? 55)) * eased,
    aspect: to.aspect ?? from.aspect,
    controls_target: to.controls_target ?? from.controls_target,
  };
}
/** Pure ownership/timing; the renderer owns requestAnimationFrame and disposal. */
export class CameraController {
  owner: CameraOwner = "manual";
  private motion: { from: CameraPose; to: CameraPose; start: number; duration: number; after: CameraOwner } | null = null;
  begin(from: CameraPose, to: CameraPose, now: number, duration: number, after: CameraOwner) {
    this.motion = duration > 0 ? { from, to, start: now, duration, after } : null;
    this.owner = this.motion ? "transition" : after;
  }
  cancel(owner: CameraOwner = "manual") { const active = this.motion !== null; this.motion = null; this.owner = owner; return active; }
  sample(now: number): CameraPose | null {
    if (!this.motion) return null;
    const m = this.motion, fraction = Math.min(1, (now - m.start) / m.duration);
    const pose = interpolatePose(m.from, m.to, fraction);
    if (fraction >= 1) { this.motion = null; this.owner = m.after; }
    return pose;
  }
}
