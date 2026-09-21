import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";

/** Bake fixed sibling parts by material; retain named transform anchors for inspection. */
export function batchFixedParts(parent: THREE.Group) {
  const batches = new Map<THREE.Material, THREE.Mesh[]>();
  for (const child of parent.children) {
    if (!(child instanceof THREE.Mesh) || Array.isArray(child.material)) continue;
    const batch = batches.get(child.material) ?? [];
    batch.push(child);
    batches.set(child.material, batch);
  }
  const removed = new Set<THREE.BufferGeometry>();
  for (const [material, parts] of batches) {
    if (parts.length < 2) continue;
    const pieces = parts.map(part => {
      part.updateMatrix();
      const copy = part.geometry.index ? part.geometry.toNonIndexed() : part.geometry.clone();
      return copy.applyMatrix4(part.matrix);
    });
    const merged = mergeGeometries(pieces, false);
    pieces.forEach(piece => piece.dispose());
    if (!merged) throw new Error("Incompatible procedural part attributes");
    const mesh = new THREE.Mesh(merged, material);
    mesh.name = "fixed-parts";
    parent.add(mesh);
    for (const part of parts) {
      const anchor = new THREE.Group();
      anchor.name = part.name;
      anchor.position.copy(part.position);
      anchor.quaternion.copy(part.quaternion);
      anchor.scale.copy(part.scale);
      parent.add(anchor);
      part.removeFromParent();
      removed.add(part.geometry);
    }
  }
  // Siblings can share source geometry with another part (including rotor pivots).
  parent.traverse(object => { if (object instanceof THREE.Mesh) removed.delete(object.geometry); });
  removed.forEach(geometry => geometry.dispose());
}
