import * as THREE from "three";
import { batchFixedParts } from "./batch-parts";

export const RACING_MODEL_VERSION = "racing-quad-v1-scale80" as const;
export interface RacingDimensions { diagonalM: number; propellerM: number }
export const RACING_DIMENSIONS: RacingDimensions = { diagonalM: 0.25, propellerM: 0.127 };
/** Illustrative 5-inch X quad. Metres, Y up, camera faces -Z. All geometry is generated. */
export function racingDrone(dimensions: RacingDimensions = RACING_DIMENSIONS): THREE.Group {
  const { diagonalM: diagonal, propellerM: prop } = dimensions;
  if (![diagonal, prop].every(Number.isFinite) || diagonal < 0.2 || diagonal > 0.5 || prop <= 0 || prop >= diagonal / Math.sqrt(2)) throw new Error("Invalid racing quad dimensions");
  const root = new THREE.Group(); root.name = "racing-quad";
  root.userData.modelVersion = RACING_MODEL_VERSION;
  root.scale.setScalar(80); // Recorded mission-display enlargement, not flight dimensions.
  const detailed = new THREE.Group(); detailed.name = "detail"; root.add(detailed);
  const carbon = new THREE.MeshStandardMaterial({ color: 0x18232b, roughness: 0.72, metalness: 0.25 });
  const metal = new THREE.MeshStandardMaterial({ color: 0x788b99, metalness: 0.75, roughness: 0.3 });
  const accent = new THREE.MeshStandardMaterial({ color: 0x25e6cc, roughness: 0.4 });
  const rubber = new THREE.MeshStandardMaterial({ color: 0x303840, roughness: 0.95 });
  const lens = new THREE.MeshStandardMaterial({ color: 0x19395a, metalness: 0.55, roughness: 0.15 });
  function mesh(name: string, geometry: THREE.BufferGeometry, material: THREE.Material, x=0,y=0,z=0, parent: THREE.Object3D=detailed) {
    const object = new THREE.Mesh(geometry, material); object.name=name; object.position.set(x,y,z); parent.add(object); return object;
  }
  const profile = new THREE.Shape();
  profile.moveTo(-0.019,-0.046); profile.lineTo(0.019,-0.046); profile.lineTo(0.026,-0.032);
  profile.lineTo(0.023,0.038); profile.lineTo(0.014,0.05); profile.lineTo(-0.014,0.05);
  profile.lineTo(-0.023,0.038); profile.lineTo(-0.026,-0.032); profile.closePath();
  const plate = new THREE.ExtrudeGeometry(profile,{depth:0.003,bevelEnabled:false}); plate.rotateX(Math.PI/2);
  mesh("bottom-plate",plate,carbon,0,0.003); mesh("top-plate",plate,carbon,0,0.027);
  const post = new THREE.CylinderGeometry(0.0025,0.0025,0.023,8);
  for(const x of [-0.016,0.016]) for(const z of [-0.03,0.03]) mesh("standoff",post,metal,x,0.014,z);
  mesh("battery",new THREE.BoxGeometry(0.034,0.024,0.068),rubber,0,0.04,0.008);
  const strap = new THREE.BoxGeometry(0.037,0.003,0.009);
  for(const z of [-0.012,0.03]) mesh("battery-strap",strap,accent,0,0.053,z);
  mesh("fpv-camera",new THREE.BoxGeometry(0.019,0.019,0.017),accent,0,0.016,-0.045);
  const glass=mesh("lens",new THREE.CylinderGeometry(0.0065,0.0065,0.006,16),lens,0,0.017,-0.056); glass.rotation.x=Math.PI/2;
  const antenna=mesh("antenna",new THREE.CylinderGeometry(0.0013,0.0013,0.04,8),rubber,0,0.04,0.06); antenna.rotation.x=0.3;
  mesh("antenna-cap",new THREE.SphereGeometry(0.004,8,6),accent,0,0.06,0.066);
  const offset=diagonal/(2*Math.sqrt(2));
  const armGeo=new THREE.BoxGeometry(0.012,0.004,diagonal/2);
  const motorGeo=new THREE.CylinderGeometry(0.013,0.013,0.016,16);
  const shaftGeo=new THREE.CylinderGeometry(0.003,0.003,0.01,8);
  const bladeProfile=new THREE.Shape(); bladeProfile.moveTo(0,0); bladeProfile.quadraticCurveTo(0.014,prop*0.23,0.008,prop/2);
  bladeProfile.lineTo(-0.001,prop/2); bladeProfile.quadraticCurveTo(-0.008,prop*0.2,0,0);
  const bladeGeo=new THREE.ExtrudeGeometry(bladeProfile,{depth:0.001,bevelEnabled:false,curveSegments:6}); bladeGeo.rotateX(Math.PI/2);
  for(const x of [-offset,offset]) for(const z of [-offset,offset]) {
    const arm=mesh(`arm-${x}-${z}`,armGeo,carbon,x/2,0,z/2); arm.rotation.y=Math.atan2(x,z);
    mesh("motor",motorGeo,metal,x,0.009,z);
    const pivot=new THREE.Group(); pivot.name="rotor"; pivot.position.set(x,0.02,z); pivot.userData.direction=x*z>0?1:-1; detailed.add(pivot);
    for(let i=0;i<3;i++) { const blade=mesh("blade",bladeGeo,accent,0,0,0,pivot); blade.rotation.y=i*2*Math.PI/3; }
    mesh("prop-nut",shaftGeo,metal,x,0.023,z);
  }
  const distant=new THREE.Group(); distant.name="distant"; root.add(distant); distant.visible=false;
  const simpleArm=new THREE.BoxGeometry(diagonal,0.005,0.012);
  for(const angle of [-Math.PI/4,Math.PI/4]) mesh("silhouette",simpleArm,accent,0,0,0,distant).rotation.y=angle;
  batchFixedParts(detailed);
  for (const pivot of detailed.children) if (pivot.name === "rotor") batchFixedParts(pivot as THREE.Group);
  batchFixedParts(distant);
  return root;
}
export function poseRacingDrone(root: THREE.Object3D, simulationTimeMs: number, distanceM: number, spinning: boolean) {
  const detailed=root.getObjectByName("detail"), distant=root.getObjectByName("distant");
  if(!detailed || !distant) return;
  detailed.visible=distanceM<1800; distant.visible=!detailed.visible;
  // Decorative 7 Hz phase is seekable, deliberately not claimed as physical RPM.
  for(const child of detailed.children) if(child.name==="rotor") child.rotation.y=spinning ? ((simulationTimeMs/1000*7*Math.PI*2)%(Math.PI*2))*child.userData.direction : 0;
}
