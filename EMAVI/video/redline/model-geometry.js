import { BufferGeometry, CatmullRomCurve3, ExtrudeGeometry, Float32BufferAttribute, Mesh, Path, Shape, TubeGeometry, Vector3, } from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
export function roundedPath(x, y, width, height, radius) {
    const p = new Path();
    const r = Math.min(radius, width / 2, height / 2);
    p.moveTo(x + r, y);
    p.lineTo(x + width - r, y);
    p.quadraticCurveTo(x + width, y, x + width, y + r);
    p.lineTo(x + width, y + height - r);
    p.quadraticCurveTo(x + width, y + height, x + width - r, y + height);
    p.lineTo(x + r, y + height);
    p.quadraticCurveTo(x, y + height, x, y + height - r);
    p.lineTo(x, y + r);
    p.quadraticCurveTo(x, y, x + r, y);
    p.closePath();
    return p;
}
export function roundedShape(width, height, radius) {
    return new Shape(roundedPath(-width / 2, -height / 2, width, height, radius).getPoints(8));
}
export function polygonShape(points) {
    const shape = new Shape();
    points.forEach(([x, y], i) => i === 0 ? shape.moveTo(x, y) : shape.lineTo(x, y));
    shape.closePath();
    return shape;
}
export function circleHole(x, y, radius) {
    const hole = new Path();
    hole.absarc(x, y, radius, 0, Math.PI * 2, true);
    return hole;
}
/** Flat plate in XZ; bottom at y=0. Real holes are Shape holes. */
export function flatPlate(shape, thickness, bevel = 0.0003) {
    const geometry = new ExtrudeGeometry(shape, {
        depth: thickness, bevelEnabled: bevel > 0, bevelSegments: 2,
        steps: 1, bevelSize: bevel, bevelThickness: bevel, curveSegments: 10,
    });
    geometry.rotateX(Math.PI / 2);
    geometry.translate(0, thickness, 0);
    // Consistent physical carbon-fibre density across individually authored plates.
    const p = geometry.getAttribute('position');
    const uv = geometry.getAttribute('uv');
    for (let i = 0; i < p.count; i++)
        uv.setXY(i, p.getX(i) * 105, p.getZ(i) * 105);
    uv.needsUpdate = true;
    return geometry;
}
export function cable(points, radius, segments = 24, radialSegments = 7) {
    return new TubeGeometry(new CatmullRomCurve3(points.map(p => new Vector3(...p)), false, 'centripetal'), segments, radius, radialSegments, false);
}
/** Swept airfoil with camber, radial twist and a rounded tip. No stored mesh data. */
export function propellerBlade(radius, handedness) {
    const positions = [];
    const uvs = [];
    const indices = [];
    const radialSteps = 30;
    const sectionSteps = 16;
    for (let i = 0; i <= radialSteps; i++) {
        const t = i / radialSteps;
        const radial = radius * (0.102 + 0.898 * t);
        const tipTaper = Math.sqrt(Math.max(0.002, 1 - Math.pow(t, 5)));
        const chord = radius * (0.065 + 0.225 * Math.sin(Math.PI * Math.pow(t, 0.83))) * tipTaper;
        const sweep = radius * (0.028 * t + 0.105 * t * t) * handedness;
        const pitch = handedness * (0.45 * (1 - t) + 0.12);
        for (let j = 0; j <= sectionSteps; j++) {
            const a = j / sectionSteps * Math.PI * 2;
            const chordPosition = Math.cos(a) * chord * 0.5;
            const thickness = Math.sin(a) * (0.00036 + 0.00034 * (1 - t)) * Math.sin(Math.PI * (0.03 + t * 0.94));
            const camber = (1 - Math.cos(a) ** 2) * chord * 0.045;
            positions.push(radial, chordPosition * Math.sin(pitch) + (thickness + camber) * Math.cos(pitch), sweep + chordPosition * Math.cos(pitch) - (thickness + camber) * Math.sin(pitch));
            uvs.push(t, j / sectionSteps);
            if (i < radialSteps && j < sectionSteps) {
                const k = i * (sectionSteps + 1) + j;
                indices.push(k, k + sectionSteps + 1, k + 1, k + 1, k + sectionSteps + 1, k + sectionSteps + 2);
            }
        }
    }
    // Close the tiny root and tip rings with computed fan triangles.
    for (const i of [0, radialSteps]) {
        const ring = i * (sectionSteps + 1);
        for (let j = 1; j < sectionSteps - 1; j++) {
            if (i === 0)
                indices.push(ring, ring + j + 1, ring + j);
            else
                indices.push(ring, ring + j, ring + j + 1);
        }
    }
    const geometry = new BufferGeometry();
    geometry.setAttribute('position', new Float32BufferAttribute(positions, 3));
    geometry.setAttribute('uv', new Float32BufferAttribute(uvs, 2));
    geometry.setIndex(indices);
    geometry.computeVertexNormals();
    geometry.computeBoundingSphere();
    return geometry;
}
/** Wide flat fabric arch, with a physical inner surface and edge faces. */
export function strapArch(width, rise, depth, thickness) {
    const positions = [];
    const uvs = [];
    const indices = [];
    const segments = 40;
    // Perimeter of each rectangular ribbon section is independently connected.
    for (let i = 0; i <= segments; i++) {
        const t = i / segments * Math.PI;
        const x = -Math.cos(t) * width / 2;
        const y = Math.sin(t) * rise;
        const tangentX = Math.sin(t) * width / 2;
        const tangentY = Math.cos(t) * rise;
        const norm = Math.hypot(tangentX, tangentY);
        const nx = -tangentY / norm;
        const ny = tangentX / norm;
        for (const [side, z] of [[-1, -depth / 2], [-1, depth / 2], [1, depth / 2], [1, -depth / 2]]) {
            positions.push(x + nx * thickness / 2 * side, y + ny * thickness / 2 * side, z);
            uvs.push(i / segments * 3.3, (z / depth + 0.5) * 1.6);
        }
        if (i < segments)
            for (let j = 0; j < 4; j++) {
                const k = i * 4 + j;
                const next = i * 4 + (j + 1) % 4;
                indices.push(k, k + 4, next, next, k + 4, next + 4);
            }
    }
    indices.push(0, 2, 1, 0, 3, 2);
    const end = segments * 4;
    indices.push(end, end + 1, end + 2, end, end + 2, end + 3);
    const geometry = new BufferGeometry();
    geometry.setAttribute('position', new Float32BufferAttribute(positions, 3));
    geometry.setAttribute('uv', new Float32BufferAttribute(uvs, 2));
    geometry.setIndex(indices);
    geometry.computeVertexNormals();
    return geometry;
}
/** One draw call per material per rigid part. Never merges across moving pivots. */
export function mergeRigidPart(group) {
    group.updateMatrixWorld(true);
    const geometries = new Map();
    const originals = [];
    for (const child of group.children) {
        if (!(child instanceof Mesh) || Array.isArray(child.material))
            continue;
        child.updateMatrix();
        let geometry = child.geometry.clone();
        geometry.applyMatrix4(child.matrix);
        if (geometry.index) {
            const source = geometry;
            geometry = source.toNonIndexed();
            source.dispose();
        }
        geometry.clearGroups();
        if (!geometry.getAttribute('uv'))
            geometry.setAttribute('uv', new Float32BufferAttribute(new Float32Array(geometry.getAttribute('position').count * 2), 2));
        const bucket = geometries.get(child.material) ?? [];
        bucket.push(geometry);
        geometries.set(child.material, bucket);
        originals.push(child);
    }
    for (const [material, geometriesForMaterial] of geometries) {
        const merged = mergeGeometries(geometriesForMaterial, false);
        if (!merged)
            throw new Error(`Cannot consolidate ${group.name}`);
        merged.computeBoundingBox();
        merged.computeBoundingSphere();
        const mesh = new Mesh(merged, material);
        mesh.name = `${group.name}:${material.name}`;
        mesh.castShadow = true;
        mesh.receiveShadow = true;
        group.add(mesh);
        geometriesForMaterial.forEach(geometry => geometry.dispose());
    }
    originals.forEach(mesh => { group.remove(mesh); mesh.geometry.dispose(); });
}
