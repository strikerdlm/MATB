import {describe,it,expect,vi} from "vitest";
import * as THREE from "three";
import {racingDrone,poseRacingDrone,RACING_MODEL_VERSION} from "./racing-drone";
import {disposeTree} from "./scene";
import {initialPresentation,resolveExposure} from "./state";
describe("procedural racing quad",()=>{
  it("has four independent rotors, twelve blades and finite geometry",()=>{
    const model=racingDrone(); let rotors=0,blades=0;
    model.traverse(object=>{if(object.name==="rotor")rotors++;if(object.name==="blade")blades++;if(object instanceof THREE.Mesh){const p=object.geometry.getAttribute("position");expect(Array.from(p.array).every(Number.isFinite)).toBe(true);}});
    expect(rotors).toBe(4);expect(blades).toBe(12);expect(model.userData.modelVersion).toBe(RACING_MODEL_VERSION);
    expect(model.getObjectByName("lens")!.position.z).toBeLessThan(0);
    expect(model.scale.x).toBe(80);disposeTree(model);
  });
  it("batches fixed parts and releases each remaining resource once",()=>{
    const model=racingDrone(),geometries=new Set<THREE.BufferGeometry>(),materials=new Set<THREE.Material>();
    let draws=0;
    model.traverseVisible(o=>{if(o instanceof THREE.Mesh)draws++;});
    expect(draws).toBeLessThanOrEqual(9);
    model.traverse(o=>{if(o instanceof THREE.Mesh){geometries.add(o.geometry);materials.add(o.material as THREE.Material);}});
    const disposals=[...geometries,...materials].map(resource=>vi.spyOn(resource,"dispose"));
    disposeTree(model);
    disposals.forEach(spy=>expect(spy).toHaveBeenCalledTimes(1));
  });
  it("rejects intersecting propellers and replays absolute rotor phase",()=>{
    expect(()=>racingDrone({diagonalM:.25,propellerM:.3})).toThrow();
    const model=racingDrone();poseRacingDrone(model,1234,100,true);const first=model.getObjectByName("rotor")!.rotation.y;
    poseRacingDrone(model,8000,3000,true);expect(model.getObjectByName("distant")!.visible).toBe(true);
    poseRacingDrone(model,1234,100,true);expect(model.getObjectByName("rotor")!.rotation.y).toBe(first);
    disposeTree(model);
  });
  it("keeps legacy models and reconstructs v3 group focus without blending targets",()=>{
    const legacy=initialPresentation(undefined,"LOW");expect(legacy.model_version).toBe("schematic-drone-v1-scale12");
    const state=initialPresentation({version:3,camera:"swarm",blocks:{LOW:"3d"},scene_id:null,scene_sha256:null},"LOW");
    expect(state).toMatchObject({version:3,inset:true,model_version:RACING_MODEL_VERSION});
    const a={...state,group_id:"A",pose:{camera_position:[0,0,0] as [number,number,number],camera_quaternion:[0,0,0,1] as [number,number,number,number]}};
    const b={...a,group_id:"B",pose:{...a.pose,camera_position:[100,0,0] as [number,number,number]}};
    const events=[{version:3,block_id:"LOW",simulation_time_ms:0,resolved:a},{version:3,block_id:"LOW",simulation_time_ms:1000,kind:"render",resolved:b}];
    expect(resolveExposure(events,"LOW",500)?.pose?.camera_position).toEqual([0,0,0]);
    expect(resolveExposure(events,"LOW",1000)?.group_id).toBe("B");
    expect(resolveExposure(events,"LOW",0)?.group_id).toBe("A");
  });
});
