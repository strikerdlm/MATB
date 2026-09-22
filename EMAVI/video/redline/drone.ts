import {
  BoxGeometry, BufferGeometry, CylinderGeometry, DataTexture, DoubleSide,
  ExtrudeGeometry, Group, LatheGeometry, LinearFilter, LinearMipmapLinearFilter,
  Material, Mesh, MeshPhysicalMaterial, MeshStandardMaterial, Path, RepeatWrapping,
  RGBAFormat, Shape, SphereGeometry, SRGBColorSpace, Texture, TorusGeometry,
  UnsignedByteType, Vector2, Vector3,
} from 'three';
import {
  cable, circleHole, flatPlate, mergeRigidPart, polygonShape, propellerBlade,
  roundedPath, roundedShape, strapArch, type Point3,
} from './model-geometry.js';

/** Illustrative dimensions inferred from the supplied photographs, not measurements. */
export interface DroneParameters {
  wheelbase: number;
  propellerDiameter: number;
  frameLength: number;
  frameWidth: number;
  motorRadius: number;
  radialSegments: number;
}

export const defaultDroneParameters: Readonly<DroneParameters> = Object.freeze({
  wheelbase: 0.235,
  propellerDiameter: 0.127,
  frameLength: 0.170,
  frameWidth: 0.037,
  motorRadius: 0.0144,
  radialSegments: 40,
});

export function validateParameters(p: DroneParameters): void {
  for (const [key, value] of Object.entries(p)) {
    if (!Number.isFinite(value) || value <= 0) throw new RangeError(`${key} must be a finite positive number`);
  }
  if (p.wheelbase < 0.18 || p.wheelbase > 0.34) throw new RangeError('wheelbase must be 0.18–0.34 m');
  if (p.propellerDiameter < 0.08 || p.propellerDiameter > 0.18) throw new RangeError('propellerDiameter must be 0.08–0.18 m');
  if (p.frameLength < 0.162 || p.frameLength > 0.22) throw new RangeError('frameLength must be 0.162–0.22 m to contain the board and mounting pattern');
  if (p.frameWidth < 0.032 || p.frameWidth > 0.053) throw new RangeError('frameWidth must be 0.032–0.053 m');
  if (p.motorRadius < 0.009 || p.motorRadius > 0.019) throw new RangeError('motorRadius must be 0.009–0.019 m');
  if (!Number.isInteger(p.radialSegments) || p.radialSegments < 16 || p.radialSegments > 80) throw new RangeError('radialSegments must be an integer between 16 and 80');
  const motorHalfZ = p.wheelbase / (2 * Math.sqrt(1 + 0.9 ** 2));
  const motorHalfX = motorHalfZ * 0.9;
  if (p.propellerDiameter + 0.004 >= motorHalfX * 2) throw new RangeError('Adjacent propeller discs must have at least 4 mm clearance');
  if (p.propellerDiameter / 2 + p.frameWidth * 0.35 + 0.001 >= motorHalfX) throw new RangeError('Propeller disc intersects the tapered frame end');
  if (p.frameLength > motorHalfZ * 2 + 0.050) throw new RangeError('Frame is too long for the motor layout');
}

export interface DronePart {
  readonly id: string;
  readonly group: Group;
  readonly assembledPosition: Vector3;
  readonly explodeOffset: Vector3;
}

export interface DroneModel {
  root: Group;
  parts: readonly DronePart[];
  rotors: Group[];
  setTime(seconds: number): void;
  setExplode(progress: number): void;
  reset(): void;
  dispose(): void;
}

type Materials = Record<'carbon' | 'edge' | 'red' | 'prop' | 'rubber' | 'fabric' | 'silver' | 'gold' | 'copper' | 'pcb' | 'chip' | 'ceramic' | 'yellow' | 'white' | 'glass' | 'iris' | 'blue' | 'stitch', Material>;

function texture(kind: 'carbon' | 'fabric' | 'roughness'): DataTexture {
  const size = 128;
  const bytes = new Uint8Array(size * size * 4);
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const cx = Math.floor(x / 16);
    const cy = Math.floor(y / 16);
    const diagonal = (cx + cy) % 4 < 2;
    const transverse = diagonal ? y % 16 : x % 16;
    const along = diagonal ? x : y;
    const thread = Math.sin(along * Math.PI / 2) * 5;
    const curvature = Math.sin((transverse + 0.5) / 16 * Math.PI);
    const deterministicGrain = ((x * 17 + y * 41 + x * y * 13) % 31) / 31;
    let value = 38 + curvature * 37 + thread + deterministicGrain * 7;
    if (kind === 'fabric') value = 25 + deterministicGrain * 63 + (Math.sin(x * 2.2) * Math.sin(y * 1.9) + 1) * 12;
    if (kind === 'roughness') value = 115 + curvature * 65 + thread * 2;
    const i = (y * size + x) * 4;
    bytes[i] = bytes[i + 1] = bytes[i + 2] = Math.round(value);
    bytes[i + 3] = 255;
  }
  const map = new DataTexture(bytes, size, size, RGBAFormat, UnsignedByteType);
  map.name = `formula:${kind}`;
  map.wrapS = map.wrapT = RepeatWrapping;
  map.magFilter = LinearFilter;
  map.minFilter = LinearMipmapLinearFilter;
  map.generateMipmaps = true;
  if (kind !== 'roughness') map.colorSpace = SRGBColorSpace;
  map.needsUpdate = true;
  return map;
}

function materials(): Materials {
  const weave = texture('carbon');
  const fabric = texture('fabric');
  const rough = texture('roughness');
  const m: Materials = {
    carbon: new MeshPhysicalMaterial({ color: 0xa4a8b0, map: weave, metalness: 0.16, roughness: 0.55, roughnessMap: rough, clearcoat: 0.24, clearcoatRoughness: 0.34 }),
    edge: new MeshStandardMaterial({ color: 0x181b20, metalness: 0.12, roughness: 0.46 }),
    red: new MeshPhysicalMaterial({ color: 0xc9081b, metalness: 0.76, roughness: 0.22, clearcoat: 0.8, clearcoatRoughness: 0.14 }),
    prop: new MeshPhysicalMaterial({ color: 0xed142b, metalness: 0.2, roughness: 0.23, clearcoat: 1, clearcoatRoughness: 0.14, side: DoubleSide }),
    rubber: new MeshStandardMaterial({ color: 0x101318, metalness: 0.04, roughness: 0.57 }),
    fabric: new MeshStandardMaterial({ color: 0x777b82, map: fabric, roughness: 0.96, bumpMap: fabric, bumpScale: 0.00024, side: DoubleSide }),
    silver: new MeshStandardMaterial({ color: 0xbac1cb, metalness: 0.96, roughness: 0.22 }),
    gold: new MeshStandardMaterial({ color: 0xd5a648, metalness: 0.83, roughness: 0.26 }),
    copper: new MeshStandardMaterial({ color: 0xcf651b, metalness: 0.88, roughness: 0.26 }),
    pcb: new MeshStandardMaterial({ color: 0x142327, metalness: 0.14, roughness: 0.43 }),
    chip: new MeshStandardMaterial({ color: 0x11151c, metalness: 0.12, roughness: 0.32 }),
    ceramic: new MeshStandardMaterial({ color: 0xa28f6f, metalness: 0.18, roughness: 0.43 }),
    yellow: new MeshPhysicalMaterial({ color: 0xffb600, roughness: 0.29, clearcoat: 0.4 }),
    white: new MeshStandardMaterial({ color: 0xe4e5d8, roughness: 0.44 }),
    glass: new MeshPhysicalMaterial({ color: 0x223248, metalness: 0.24, roughness: 0.07, clearcoat: 1, clearcoatRoughness: 0.025 }),
    iris: new MeshPhysicalMaterial({ color: 0x382352, metalness: 0.62, roughness: 0.16, clearcoat: 1 }),
    blue: new MeshStandardMaterial({ color: 0x42c4ef, emissive: 0x19c2ff, emissiveIntensity: 1.5, roughness: 0.35 }),
    stitch: new MeshStandardMaterial({ color: 0x727680, roughness: 0.92 }),
  };
  for (const [name, material] of Object.entries(m)) material.name = name;
  return m;
}

function add(group: Group, geometry: BufferGeometry, material: Material, position: Point3 = [0, 0, 0], rotation: Point3 = [0, 0, 0]): Mesh {
  const mesh = new Mesh(geometry, material);
  mesh.position.set(...position);
  mesh.rotation.set(...rotation);
  mesh.castShadow = mesh.receiveShadow = true;
  group.add(mesh);
  return mesh;
}

function box(group: Group, material: Material, size: Point3, position: Point3, rotation: Point3 = [0, 0, 0]): Mesh {
  return add(group, new BoxGeometry(...size), material, position, rotation);
}

function cylinder(group: Group, material: Material, radius: number, height: number, position: Point3, segments = 32, rotation: Point3 = [0, 0, 0]): Mesh {
  return add(group, new CylinderGeometry(radius, radius, height, segments), material, position, rotation);
}

function ring(group: Group, material: Material, radius: number, tube: number, position: Point3, rotation: Point3 = [Math.PI / 2, 0, 0], segments = 40): Mesh {
  return add(group, new TorusGeometry(radius, tube, 8, segments), material, position, rotation);
}

function strut(group: Group, material: Material, from: Point3, to: Point3, radius: number, radialSegments = 10): void {
  const a = new Vector3(...from);
  const b = new Vector3(...to);
  const length = a.distanceTo(b);
  const mesh = cylinder(group, material, radius, length, [...a.clone().add(b).multiplyScalar(0.5).toArray()] as unknown as Point3, radialSegments);
  mesh.quaternion.setFromUnitVectors(new Vector3(0, 1, 0), b.sub(a).normalize());
}

function bolt(group: Group, m: Materials, x: number, y: number, z: number, radius = 0.00165, washer = true): void {
  if (washer) cylinder(group, m.silver, radius * 1.36, 0.00038, [x, y, z], 18);
  cylinder(group, m.silver, radius, 0.0011, [x, y + 0.00055, z], 12);
  // Hex socket is a genuinely open annular head over a dark recess.
  const section = [new Vector2(radius * 0.54, 0), new Vector2(radius, 0), new Vector2(radius, 0.00065), new Vector2(radius * 0.54, 0.00065), new Vector2(radius * 0.54, 0)];
  add(group, new LatheGeometry(section, 6), m.silver, [x, y + 0.001, z]);
  cylinder(group, m.rubber, radius * 0.52, 0.0001, [x, y + 0.00107, z], 6);
}

function bodyShape(length: number, width: number): Shape {
  const z = length / 2;
  const x = width / 2;
  const s = new Shape();
  s.moveTo(-x * 0.72, -z);
  s.lineTo(x * 0.72, -z);
  s.quadraticCurveTo(x, -z, x, -z + 0.006);
  s.lineTo(x, -0.025);
  s.quadraticCurveTo(x + 0.002, -0.009, x - 0.001, 0.008);
  s.lineTo(x * 0.71, z - 0.005);
  s.quadraticCurveTo(x * 0.7, z, x * 0.45, z);
  s.lineTo(-x * 0.45, z);
  s.quadraticCurveTo(-x * 0.7, z, -x * 0.71, z - 0.005);
  s.lineTo(-x + 0.001, 0.008);
  s.quadraticCurveTo(-x - 0.002, -0.009, -x, -0.025);
  s.lineTo(-x, -z + 0.006);
  s.quadraticCurveTo(-x, -z, -x * 0.72, -z);
  s.closePath();
  return s;
}

function buildBase(group: Group, p: DroneParameters, m: Materials, mx: number, mz: number): void {
  const body = bodyShape(p.frameLength * 0.86, p.frameWidth * 1.15);
  for (const z of [-0.047, 0.044]) for (const x of [-0.014, 0.014]) body.holes.push(circleHole(x, z, 0.0018));
  add(group, flatPlate(body, 0.0037), m.carbon);
  add(group, flatPlate(bodyShape(p.frameLength * 0.82, p.frameWidth * 1.02), 0.001), m.edge, [0, -0.0012, 0]);
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) {
    const shape = new Shape();
    // Cubic outlines preserve the gracefully swept, flat arm profile in the photographs.
    shape.moveTo(sx * 0.013, sz * 0.033);
    shape.bezierCurveTo(sx * 0.029, sz * 0.044, sx * (mx - 0.026), sz * (mz - 0.014), sx * (mx - 0.010), sz * (mz - 0.015));
    shape.quadraticCurveTo(sx * (mx + 0.014), sz * (mz - 0.020), sx * (mx + 0.017), sz * mz);
    shape.quadraticCurveTo(sx * (mx + 0.017), sz * (mz + 0.016), sx * mx, sz * (mz + 0.017));
    shape.quadraticCurveTo(sx * (mx - 0.014), sz * (mz + 0.017), sx * (mx - 0.018), sz * (mz + 0.003));
    shape.bezierCurveTo(sx * (mx - 0.035), sz * (mz - 0.007), sx * 0.027, sz * 0.060, sx * 0.012, sz * 0.052);
    shape.closePath();
    shape.holes.push(circleHole(sx * mx, sz * mz, 0.0034));
    add(group, flatPlate(shape, 0.0044, 0.00045), m.carbon);
    // Visible stacked arm laminations.
    for (const y of [0.0005, 0.00165, 0.0028]) {
      add(group, cable([[sx * 0.020, y, sz * 0.048], [sx * 0.038, y, sz * 0.066], [sx * (mx - 0.016), y, sz * (mz + 0.001)]], 0.00016, 18, 4), m.edge);
    }
    for (let k = -1; k <= 1; k++) {
      const offset = k * 0.0022;
      const points: Point3[] = [[sx * 0.015, 0.011 + k * 0.0003, sz * 0.012], [sx * 0.022, 0.007 + k * 0.0003, sz * 0.042 + offset], [sx * 0.047, 0.007, sz * 0.066 + offset], [sx * (mx - 0.009), 0.0078, sz * mz + offset]];
      add(group, cable(points, 0.0009, 28, 7), m.rubber);
      add(group, cable(points.map(v => [v[0], v[1] + 0.00065, v[2]]), 0.00016, 28, 4), m.edge);
    }
    // Arm cable-retaining rubber band; a strip across the wire bundle and down both sides.
    const band = new Group();
    const bx = sx * 0.048;
    const bz = sz * 0.065;
    box(band, m.rubber, [0.0125, 0.0015, 0.0044], [0, 0.0085, 0]);
    for (const side of [-1, 1]) box(band, m.rubber, [0.0013, 0.0085, 0.0044], [side * 0.006, 0.0043, 0]);
    box(band, m.rubber, [0.0125, 0.0012, 0.0044], [0, 0, 0]);
    band.position.set(bx, 0, bz);
    band.rotation.y = sx * sz * -0.76;
    band.updateMatrix();
    for (const child of [...band.children]) { child.applyMatrix4(band.matrix); group.add(child); }
    for (const x of [-0.0055, 0.0055]) for (const z of [-0.0055, 0.0055]) bolt(group, m, sx * mx + x, 0.0038, sz * mz + z, 0.00115, false);
  }
  // Four low TPU feet beneath the motor mounting pads.
  for (const x of [-mx, mx]) for (const z of [-mz, mz]) cylinder(group, m.rubber, 0.0105, 0.0028, [x, -0.0015, z], 28);
}

function buildDeck(group: Group, p: DroneParameters, m: Materials): void {
  const shape = bodyShape(p.frameLength, p.frameWidth);
  const widthScale = p.frameWidth / defaultDroneParameters.frameWidth;
  // Open straps and cooling slots: all holes cut through the plate, not painted marks.
  for (const z of [-0.047, -0.021, 0.012, 0.041, 0.066]) {
    for (const x of [-0.0075, 0.0075]) {
      const length = z === 0.066 ? 0.012 : 0.015;
      shape.holes.push(roundedPath(x * widthScale - 0.0018, z - length / 2, 0.0036, length, 0.0018));
    }
  }
  for (const z of [-0.022, 0.012]) shape.holes.push(roundedPath(-0.0014, z - 0.008, 0.0028, 0.016, 0.0014));
  const triangle = new Path();
  triangle.moveTo(-0.005, -0.067);
  triangle.quadraticCurveTo(-0.006, -0.069, -0.004, -0.071);
  triangle.lineTo(0.0035, -0.071);
  triangle.quadraticCurveTo(0.006, -0.070, 0.0048, -0.067);
  triangle.lineTo(0.0008, -0.061);
  triangle.quadraticCurveTo(0, -0.059, -0.0014, -0.061);
  triangle.closePath();
  shape.holes.push(triangle);
  for (const z of [-0.077, -0.038, 0.053, 0.079]) for (const side of [-1, 1]) {
    const x = side * (z === 0.079 ? 0.009 : 0.013) * widthScale;
    shape.holes.push(circleHole(x, z, 0.00155));
    if (z === -0.038 || z === 0.053) cylinder(group, m.red, 0.0029, 0.0008, [x, 0.0031, z], 24);
    bolt(group, m, x, 0.0033, z, 0.00185, true);
  }
  add(group, flatPlate(shape, 0.0026, 0.00022), m.carbon);
}

function buildStandoffs(group: Group, m: Materials): void {
  for (const [x, z] of [[-0.013, -0.077], [0.013, -0.077], [-0.017, -0.037], [0.017, -0.037], [-0.016, 0.028], [0.016, 0.028], [-0.009, 0.079], [0.009, 0.079]]) {
    cylinder(group, m.red, 0.0022, 0.0265, [x!, 0.0175, z!], 24);
    cylinder(group, m.gold, 0.0024, 0.0037, [x!, 0.0063, z!], 18);
    cylinder(group, m.rubber, 0.0027, 0.0015, [x!, 0.0304, z!], 20);
    for (const y of [0.0061, 0.0292]) ring(group, m.red, 0.0022, 0.0003, [x!, y, z!], undefined, 24);
  }
}

function buildBoard(group: Group, m: Materials, level: number): void {
  const width = 0.036;
  const depth = 0.037;
  const shape = roundedShape(width, depth, 0.002);
  for (const x of [-0.0147, 0.0147]) for (const z of [-0.0147, 0.0147]) shape.holes.push(circleHole(x, z, 0.0016));
  add(group, flatPlate(shape, 0.00105, 0.00008), m.pcb);
  // Exposed gold edge and small plated solder pads surrounding the board.
  for (let i = -5; i <= 5; i++) {
    cylinder(group, m.gold, 0.00054, 0.00009, [i * 0.00265, 0.00119, -0.0175], 10);
    cylinder(group, m.gold, 0.00054, 0.00009, [i * 0.00265, 0.00119, 0.0175], 10);
  }
  for (const x of [-0.0147, 0.0147]) for (const z of [-0.0147, 0.0147]) {
    cylinder(group, m.gold, 0.00235, 0.0023, [x, 0.0003, z], 20);
    cylinder(group, m.rubber, 0.00255, 0.0019, [x, 0.0024, z], 20);
    cylinder(group, m.silver, 0.0013, 0.0023, [x, 0.0032, z], 12);
  }
  const mainChipX = level === 1 ? 0.002 : -0.001;
  const mainChipZ = level === 2 ? -0.001 : 0.001;
  box(group, m.chip, [0.009, 0.00145, 0.009], [mainChipX, 0.0019, mainChipZ], [0, level === 1 ? Math.PI / 4 : 0, 0]);
  for (let j = -5; j <= 5; j++) for (const side of [-1, 1]) {
    box(group, m.silver, [0.00033, 0.00019, 0.0013], [j * 0.00069 + mainChipX, 0.00135, side * 0.0049 + mainChipZ]);
    box(group, m.silver, [0.0013, 0.00019, 0.00033], [side * 0.0049 + mainChipX, 0.00135, j * 0.00069 + mainChipZ]);
  }
  for (let i = 0; i < 34; i++) {
    const side = i % 2 ? 1 : -1;
    const z = -0.012 + Math.floor(i / 2) * 0.00145;
    const x = side * (0.0077 + i % 3 * 0.0026);
    const length = i % 4 === 0 ? 0.0024 : 0.0015;
    box(group, i % 3 ? m.ceramic : m.chip, [length, 0.00085, 0.001], [x, 0.0017, z]);
    for (const end of [-1, 1]) box(group, m.silver, [0.00035, 0.0009, 0.00103], [x + end * length / 2, 0.00168, z]);
  }
  // PCB routing is authored geometry, readable in the macro inspection cameras.
  for (let i = 0; i < 11; i++) {
    const z = -0.011 + i * 0.0022;
    add(group, cable([[-0.012, 0.00113, z], [-0.008, 0.00113, z], [-0.004, 0.00113, z + 0.002]], 0.000075, 4, 3), m.gold);
    add(group, cable([[0.007, 0.00113, z], [0.009, 0.00113, z - 0.0015], [0.015, 0.00113, z - 0.0015]], 0.000075, 4, 3), m.gold);
  }
  // USB shell at right side, with genuine open mouth and white insulating tongue.
  box(group, m.silver, [0.006, 0.00035, 0.0075], [0.0165, 0.002, -0.003]);
  box(group, m.silver, [0.006, 0.00035, 0.0075], [0.0165, 0.0045, -0.003]);
  for (const z of [-0.0066, 0.0006]) box(group, m.silver, [0.006, 0.0027, 0.00035], [0.0165, 0.00325, z]);
  box(group, m.rubber, [0.0005, 0.0022, 0.0065], [0.0143, 0.00325, -0.003]);
  box(group, m.white, [0.0041, 0.0005, 0.0049], [0.0170, 0.00315, -0.003]);
  for (let i = 0; i < 5; i++) box(group, m.gold, [0.003, 0.00012, 0.00028], [0.017, 0.00346, -0.0046 + i * 0.00078]);
  // Opposite white JST socket and individual contact pins.
  box(group, m.white, [0.0039, 0.0025, 0.0078], [-0.0164, 0.0027, 0.006]);
  box(group, m.rubber, [0.00015, 0.0016, 0.0065], [-0.01845, 0.0028, 0.006]);
  for (let i = 0; i < 5; i++) box(group, m.gold, [0.00055, 0.00038, 0.00044], [-0.0187, 0.00275, 0.0036 + i * 0.0012]);
  if (level === 2) {
    box(group, m.silver, [0.0068, 0.0016, 0.0041], [0, 0.0021, 0.012]);
    cylinder(group, m.blue, 0.0006, 0.0004, [0.012, 0.0016, 0.013], 10);
  }
}

function buildMotor(group: Group, p: DroneParameters, m: Materials): void {
  const r = p.motorRadius;
  const n = p.radialSegments;
  cylinder(group, m.red, r * 0.69, 0.0024, [0, 0.0015, 0], n);
  cylinder(group, m.rubber, r * 0.65, 0.0007, [0, 0.003, 0], n);
  // The bell is a thin open annulus: windings remain visible through its open top.
  const profile = [[r * 0.86, 0.003], [r * 0.97, 0.003], [r, 0.0038], [r, 0.0158], [r * 0.98, 0.0165], [r * 0.89, 0.0165], [r * 0.89, 0.0156], [r * 0.88, 0.004], [r * 0.86, 0.003]].map(v => new Vector2(v[0], v[1]));
  add(group, new LatheGeometry(profile, n), m.edge);
  ring(group, m.silver, r * 0.98, 0.00023, [0, 0.0163, 0], undefined, n);
  ring(group, m.red, r * 0.88, 0.00065, [0, 0.0153, 0], undefined, n);
  cylinder(group, m.edge, r * 0.27, 0.014, [0, 0.0105, 0], n);
  cylinder(group, m.silver, 0.0024, 0.023, [0, 0.013, 0], 20);
  // Twelve visible wound stator teeth, each represented by a helical copper winding.
  for (let i = 0; i < 12; i++) {
    const a = i / 12 * Math.PI * 2;
    const ca = Math.cos(a), sa = Math.sin(a);
    const centre = r * 0.65;
    box(group, m.chip, [r * 0.29, 0.008, 0.0031], [ca * centre, 0.010, sa * centre], [0, -a, 0]);
    const points: Point3[] = [];
    const turns = 6;
    const samples = turns * 12;
    for (let j = 0; j <= samples; j++) {
      const t = j / samples;
      const turn = t * turns * Math.PI * 2;
      const radial = r * (0.52 + 0.27 * t);
      const across = Math.cos(turn) * 0.00185;
      points.push([ca * radial - sa * across, 0.0105 + Math.sin(turn) * 0.004, sa * radial + ca * across]);
    }
    add(group, cable(points, 0.000235, samples, 4), m.copper);
    // Sparse red spokes leave open windows between the hub and bell rim.
    if (i % 2 === 0) strut(group, m.red, [ca * r * 0.23, 0.0190, sa * r * 0.23], [ca * r * 0.91, 0.0156, sa * r * 0.91], 0.00095, 8);
  }
  cylinder(group, m.red, r * 0.29, 0.0048, [0, 0.018, 0], n);
  for (let i = 0; i < 4; i++) {
    const a = i * Math.PI / 2 + Math.PI / 4;
    cylinder(group, m.rubber, 0.0020, 0.0027, [Math.cos(a) * r * 0.58, 0.001, Math.sin(a) * r * 0.58], 14);
  }
}

function buildPropeller(group: Group, p: DroneParameters, m: Materials, direction: number): void {
  const r = p.propellerDiameter / 2;
  for (let i = 0; i < 3; i++) add(group, propellerBlade(r, direction), m.prop, [0, 0, 0], [0, i * Math.PI * 2 / 3, 0]);
  const hub = [[0.0025, -0.0012], [0.0063, -0.0012], [0.0065, 0.0008], [0.0057, 0.0027], [0.0025, 0.0027], [0.0025, -0.0012]].map(v => new Vector2(v[0], v[1]));
  add(group, new LatheGeometry(hub, 32), m.red);
  cylinder(group, m.silver, 0.004, 0.00055, [0, 0.003, 0], 24);
  cylinder(group, m.edge, 0.00355, 0.0033, [0, 0.0048, 0], 6);
  cylinder(group, m.silver, 0.00225, 0.00115, [0, 0.00645, 0], 20);
  ring(group, m.silver, 0.00343, 0.0002, [0, 0.0061, 0], undefined, 6);
  cylinder(group, m.rubber, 0.00135, 0.0001, [0, 0.00705, 0], 6);
}

function cageSide(): Shape {
  const shape = polygonShape([[-0.008, -0.017], [0.013, -0.017], [0.016, 0.010], [0.009, 0.017], [-0.011, 0.013]]);
  const hole = new Path();
  hole.moveTo(-0.004, -0.009);
  hole.lineTo(0.009, -0.008);
  hole.quadraticCurveTo(0.012, -0.008, 0.010, -0.005);
  hole.lineTo(0.002, 0.008);
  hole.quadraticCurveTo(0, 0.011, -0.002, 0.007);
  hole.lineTo(-0.005, -0.006);
  hole.closePath();
  shape.holes.push(hole);
  return shape;
}

function buildCamera(group: Group, m: Materials): void {
  // Camera faces -Z. Side plate's 2-D X coordinate becomes Z on either side.
  for (const side of [-1, 1]) {
    const sideGeo = new ExtrudeGeometry(cageSide(), { depth: 0.0025, bevelEnabled: true, bevelSegments: 2, bevelSize: 0.0003, bevelThickness: 0.0003, curveSegments: 8 });
    sideGeo.rotateY(Math.PI / 2);
    const uv = sideGeo.getAttribute('uv');
    for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) * 105, uv.getY(i) * 105);
    add(group, sideGeo, m.carbon, [side < 0 ? -0.015 : 0.0125, 0, 0]);
    // Red edge rails are routed along the open side profile rather than filling the cutout.
    add(group, cable([[side * 0.0151, -0.017, 0.008], [side * 0.0151, -0.017, -0.013], [side * 0.0151, 0.010, -0.016], [side * 0.0151, 0.017, -0.009], [side * 0.0151, 0.013, 0.011]], 0.00105, 24, 8), m.red);
    for (const [y, z] of [[-0.010, 0.004], [0.009, -0.009], [-0.010, -0.008]]) {
      const boltGeo = new CylinderGeometry(0.00185, 0.00185, 0.0009, 12);
      add(group, boltGeo, m.silver, [side * 0.0164, y!, z!], [0, 0, Math.PI / 2]);
      add(group, new CylinderGeometry(0.0007, 0.0007, 0.00105, 6), m.rubber, [side * 0.0168, y!, z!], [0, 0, Math.PI / 2]);
    }
  }
  const housing = roundedShape(0.025, 0.024, 0.004);
  add(group, new ExtrudeGeometry(housing, { depth: 0.012, bevelEnabled: true, bevelSize: 0.0011, bevelThickness: 0.0011, bevelSegments: 3 }), m.red, [0, 0, -0.007]);
  // Substantial open front lower crossmember.
  box(group, m.edge, [0.029, 0.003, 0.005], [0, -0.017, -0.011]);
  box(group, m.silver, [0.008, 0.0008, 0.003], [0, -0.0152, -0.012]);
  // Forward axis of the lens is -Z; stack annular lens barrels and recessed coated glass.
  for (const [radius, thickness, z] of [[0.0105, 0.0041, -0.010], [0.0092, 0.0035, -0.0137], [0.0083, 0.0025, -0.0166]]) {
    const section = [[radius! * 0.75, -thickness! / 2], [radius!, -thickness! / 2], [radius!, thickness! / 2], [radius! * 0.75, thickness! / 2], [radius! * 0.75, -thickness! / 2]].map(v => new Vector2(v[0], v[1]));
    add(group, new LatheGeometry(section, 48), m.edge, [0, 0, z!], [Math.PI / 2, 0, 0]);
    ring(group, m.rubber, radius! * 0.98, 0.00018, [0, 0, z! - thickness! / 2], [0, 0, 0], 48);
  }
  for (let i = 0; i < 40; i++) {
    const a = i / 40 * Math.PI * 2;
    box(group, m.rubber, [0.00042, 0.0015, 0.0034], [Math.sin(a) * 0.0105, Math.cos(a) * 0.0105, -0.0103], [0, 0, -a]);
  }
  const lens = add(group, new SphereGeometry(0.0065, 48, 24), m.glass, [0, 0, -0.0168]);
  lens.scale.z = 0.25;
  ring(group, m.iris, 0.00465, 0.00028, [0, 0, -0.0184], [0, 0, 0], 40);
  const iris = add(group, new SphereGeometry(0.0028, 32, 16), m.iris, [0, 0, -0.01855]);
  iris.scale.z = 0.075;
  const pupil = add(group, new SphereGeometry(0.00155, 24, 12), m.rubber, [0, 0, -0.01876]);
  pupil.scale.z = 0.1;
  add(group, new SphereGeometry(0.00035, 12, 8), m.blue, [-0.00105, 0.00115, -0.01895]);
  // Camera wiring exits rear into the electronics bay.
  for (let k = 0; k < 3; k++) add(group, cable([[0.005 + k * 0.0014, -0.003, 0.008], [0.009 + k * 0.001, -0.005, 0.020], [0.006 + k * 0.001, -0.008, 0.035]], 0.0006, 18, 6), k === 0 ? m.red : m.rubber);
}

function buildStrap(group: Group, m: Materials): void {
  add(group, strapArch(0.045, 0.023, 0.018, 0.0014), m.fabric);
  // Longitudinal stitch dashes run along both cloth edges, following the physical arch.
  for (const z of [-0.0082, 0.0082]) for (let i = 1; i < 35; i++) {
    const a = i / 36 * Math.PI;
    const b = (i + 0.45) / 36 * Math.PI;
    strut(group, m.stitch, [-Math.cos(a) * 0.0231, Math.sin(a) * 0.0237, z], [-Math.cos(b) * 0.0231, Math.sin(b) * 0.0237, z], 0.00009, 4);
  }
  // Two red rectangular strap loops, no battery added to the reference configuration.
  for (const side of [-1, 1]) {
    const x = side * 0.0225;
    add(group, cable([[x, 0.003, -0.0105], [x + side * 0.002, 0.003, -0.0105], [x + side * 0.002, 0.003, 0.0105], [x, 0.003, 0.0105]], 0.0009, 20, 8), m.red);
  }
  box(group, m.rubber, [0.0028, 0.0052, 0.020], [0.0233, 0.0075, 0]);
}

function buildAntennae(group: Group, m: Materials): void {
  // Twin rear receiver whips splay laterally and aft, with distinct red end caps.
  for (const side of [-1, 1]) {
    const base: Point3 = [side * 0.012, 0.005, 0.075];
    const joint: Point3 = [side * 0.018, 0.031, 0.082];
    const top: Point3 = [side * 0.049, 0.117, 0.115];
    const end: Point3 = [side * 0.054, 0.133, 0.121];
    strut(group, m.rubber, base, joint, 0.0031, 20);
    strut(group, m.edge, joint, top, 0.00185, 20);
    strut(group, m.red, top, end, 0.0038, 28);
    const cap = add(group, new SphereGeometry(0.0038, 24, 12), m.red, end);
    cap.scale.y = 0.5;
    strut(group, m.silver, [side * 0.014, 0.015, 0.078], [side * 0.0148, 0.018, 0.079], 0.0031, 18);
  }
  // Central short VTX antenna's cylindrical red radome and brass RF connector.
  cylinder(group, m.gold, 0.0034, 0.006, [0, 0.035, 0.080], 24);
  cylinder(group, m.red, 0.0075, 0.0026, [0, 0.0386, 0.080], 36);
  cylinder(group, m.red, 0.0096, 0.012, [0, 0.047, 0.080], 40);
  ring(group, m.red, 0.0091, 0.0007, [0, 0.053, 0.080], undefined, 40);
  cylinder(group, m.red, 0.0089, 0.0005, [0, 0.0536, 0.080], 36);
  // Red and black power leads terminate in a recognisable XT60-style connector.
  add(group, cable([[0.010, 0.010, 0.032], [0.019, 0.016, 0.070], [0.029, 0.029, 0.102], [0.037, 0.040, 0.116]], 0.0021, 30, 10), m.red);
  add(group, cable([[0.014, 0.010, 0.031], [0.022, 0.017, 0.070], [0.033, 0.032, 0.102], [0.041, 0.043, 0.116]], 0.0021, 30, 10), m.rubber);
  const connector = roundedShape(0.013, 0.0085, 0.0013);
  for (const x of [-0.0034, 0.0034]) connector.holes.push(circleHole(x, 0, 0.0018));
  add(group, new ExtrudeGeometry(connector, { depth: 0.012, bevelEnabled: true, bevelSize: 0.00055, bevelThickness: 0.00055, bevelSegments: 2 }), m.yellow, [0.039, 0.044, 0.115], [-0.32, 0.18, -0.24]);
  for (const x of [0.0357, 0.0423]) add(group, cable([[x, 0.0415, 0.112], [x, 0.043, 0.117]], 0.0027, 5, 12), m.rubber);
  // RF coax routed to the raised rear antenna assembly.
  add(group, cable([[-0.010, 0.026, 0.015], [-0.009, 0.025, 0.052], [0, 0.025, 0.068], [0, 0.033, 0.080]], 0.00065, 22, 7), m.rubber);
}

/** Build a reference-faithful red/carbon quad using only runtime geometry. Y-up; front -Z. */
export function createDrone(parameters: Partial<DroneParameters> = {}): DroneModel {
  const p: DroneParameters = { ...defaultDroneParameters, ...parameters };
  validateParameters(p);
  const root = new Group();
  root.name = 'REDLINE / reference racing quad';
  const m = materials();
  const parts: DronePart[] = [];
  const rotors: Group[] = [];
  const phaseOffsets: number[] = [];
  const directions: number[] = [];
  const mx = p.wheelbase / (2 * Math.sqrt(1 + 0.9 ** 2)) * 0.9;
  const mz = mx / 0.9;
  const part = (id: string, assembled: Point3, offset: Point3): Group => {
    const group = new Group();
    group.name = id;
    group.position.set(...assembled);
    root.add(group);
    parts.push({ id, group, assembledPosition: new Vector3(...assembled), explodeOffset: new Vector3(...offset) });
    return group;
  };
  buildBase(part('carbon-frame-and-wiring', [0, 0, 0], [0, -0.042, 0]), p, m, mx, mz);
  buildDeck(part('slotted-carbon-top-deck', [0, 0.031, 0], [0, 0.105, 0]), p, m);
  buildStandoffs(part('anodized-frame-standoffs', [0, 0, 0], [0, 0.008, 0]), m);
  for (let i = 0; i < 3; i++) buildBoard(part(['esc-power-board', 'flight-controller-board', 'video-transmitter-board'][i]!, [0, 0.007 + i * 0.0067, -0.006], [0, 0.024 + i * 0.022, 0]), m, i);
  buildCamera(part('fpv-camera-and-open-cage', [0, 0.0175, -0.081], [0, 0.014, -0.083]), m);
  buildStrap(part('empty-velcro-battery-strap', [0, 0.035, 0.009], [0, 0.135, 0]), m);
  buildAntennae(part('receiver-vtx-and-xt60', [0, 0, 0], [0, 0.040, 0.075]), m);
  let i = 0;
  for (const sz of [-1, 1]) for (const sx of [-1, 1]) {
    const label = `${sz < 0 ? 'front' : 'rear'}-${sx < 0 ? 'left' : 'right'}`;
    const x = sx * mx;
    const z = sz * mz;
    buildMotor(part(`${label}-brushless-motor`, [x, 0.0052, z], [sx * 0.028, 0.012, sz * 0.030]), p, m);
    const rotorPlacement = part(`${label}-three-blade-propeller`, [x, 0.027, z], [sx * 0.028, 0.071, sz * 0.030]);
    const pivot = new Group();
    pivot.name = `${label}-rotor-pivot`;
    rotorPlacement.add(pivot);
    const direction = sx * sz;
    buildPropeller(pivot, p, m, direction);
    mergeRigidPart(pivot);
    rotors.push(pivot);
    directions.push(direction);
    phaseOffsets.push(0.35 + i++ * 0.61);
  }
  parts.forEach(({ group }) => mergeRigidPart(group));
  root.updateMatrixWorld(true);
  // Private rest transforms cannot drift when callers inspect the public part metadata.
  const rest = parts.map(({ group, assembledPosition, explodeOffset }) => ({
    group, position: assembledPosition.clone(), offset: explodeOffset.clone(),
    quaternion: group.quaternion.clone(), scale: group.scale.clone(),
  }));
  root.userData = {
    units: 'metres', up: '+Y', front: '-Z', dimensions: { ...p },
    provenance: 'Procedural reconstruction of six user-supplied photographs. Dimensions are inferred, not measured.',
    battery: 'No battery: the empty strap matches the photographs.',
  };
  let disposed = false;
  const api: DroneModel = {
    root,
    parts,
    rotors,
    setTime(seconds: number): void {
      if (!Number.isFinite(seconds)) throw new RangeError('Time must be finite');
      const phase = (seconds * 575) % (Math.PI * 2);
      rotors.forEach((rotor, index) => { rotor.rotation.y = phaseOffsets[index]! + directions[index]! * phase; });
    },
    setExplode(progress: number): void {
      if (!Number.isFinite(progress)) throw new RangeError('Explosion progress must be finite');
      const amount = Math.min(1, Math.max(0, progress));
      rest.forEach(({ group, position, offset, quaternion, scale }) => {
        group.position.copy(position).addScaledVector(offset, amount);
        group.quaternion.copy(quaternion);
        group.scale.copy(scale);
      });
    },
    reset(): void { api.setTime(0); api.setExplode(0); },
    dispose(): void {
      if (disposed) return;
      disposed = true;
      const geometrySet = new Set<BufferGeometry>();
      const materialSet = new Set<Material>();
      const textureSet = new Set<Texture>();
      root.traverse(object => {
        if (object instanceof Mesh) {
          geometrySet.add(object.geometry);
          const materialList = Array.isArray(object.material) ? object.material : [object.material];
          materialList.forEach(material => materialSet.add(material));
        }
      });
      Object.values(m).forEach(material => materialSet.add(material));
      materialSet.forEach(material => {
        for (const value of Object.values(material)) if (value instanceof Texture) textureSet.add(value);
        material.dispose();
      });
      geometrySet.forEach(geometry => geometry.dispose());
      textureSet.forEach(map => map.dispose());
      root.removeFromParent();
    },
  };
  api.reset();
  return api;
}

export default defaultDroneParameters;
