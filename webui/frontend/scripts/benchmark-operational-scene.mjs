// CPU object-lifecycle benchmark; no WebGL, GPU completion or physical onset.
// Run after npm ci: node scripts/benchmark-operational-scene.mjs <report.json>
import ts from "typescript";
import * as THREE from "three";
import { writeFileSync, readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const moduleSource = `
import * as THREE from 'three';
import { operationalObjects } from './src/lib/simulation/presentation/operational-objects';
import { drone, disposeTree } from './src/lib/simulation/presentation/scene';
function stats(values) { const ordered=[...values].sort((a,b)=>a-b); return {n:values.length,p50:ordered[Math.floor(values.length*.5)],p95:ordered[Math.floor(values.length*.95)],p99:ordered[Math.floor(values.length*.99)],max:ordered.at(-1)}; }
function run(aircraftCount, contactCount, frames, mode) {
  const dynamic=new THREE.Group(), fixed=new THREE.Group();
  const state={block_id:'BENCHMARK',scenario_sha256:'synthetic',aircraft:{},contacts:{},sectors:{},restricted_zones:{},coverage:{origin:{x_mm:0,y_mm:0},grid_cell_mm:100000,sectors:{}}};
  for(let i=0;i<aircraftCount;i++) state.aircraft['a'+i]={aircraft_id:'a'+i,position:{x_mm:i*1000,y_mm:i*2000},heading_mdeg:0,route:[]};
  for(let i=0;i<contactCount;i++) state.contacts['c'+i]={contact_id:'c'+i,position:{x_mm:i*1000,y_mm:i*2000},evidence:'OBSERVED'};
  const current=operationalObjects(dynamic,fixed,(p,h)=>[p.x_mm/1000,h,p.y_mm/1000],drone,disposeTree);
  const times=[]; let created=0;
  for(let frame=0;frame<frames+10;frame++) {
    state.contacts.c0.position.x_mm=frame;
    state.aircraft.a0.position.x_mm=frame;
    const start=performance.now();
    if(mode==='keyed') current.update(state);
    else {
      // Pinned pre-change pattern: a changed serialized contact key disposes
      // the complete dynamic group. Geometry/model construction is identical.
      const key=JSON.stringify([state.block_id,Object.keys(state.aircraft),state.contacts]);
      if(dynamic.userData.key!==key) { disposeTree(dynamic); dynamic.clear(); dynamic.userData.key=key;
        for(const a of Object.values(state.aircraft)) { const object=drone(); object.name=a.aircraft_id; object.position.set(a.position.x_mm/1000,120,a.position.y_mm/1000); dynamic.add(object); created++; }
        for(const c of Object.values(state.contacts)) { const object=new THREE.Mesh(new THREE.OctahedronGeometry(35),new THREE.MeshBasicMaterial({color:0xffd166,depthTest:false})); object.position.set(c.position.x_mm/1000,45,c.position.y_mm/1000); dynamic.add(object); }
      }
    }
    if(frame>=10) times.push(performance.now()-start);
  }
  const position=(mode==='keyed'?current.aircraft.objects.get('a0'):dynamic.getObjectByName('a0')).position.toArray();
  const result={mode,aircraftCount,contactCount,frames,warmup:10,cpu_update_ms:stats(times),aircraftCreated:mode==='keyed'?current.metrics().aircraftCreated:created,finalAircraftPosition:position};
  disposeTree(dynamic); disposeTree(fixed); return result;
}
const cases=[];
for(const [a,c] of [[12,40],[40,400],[80,1000]]) {
  const baseline=run(a,c,120,'legacy-rebuild'),keyed=run(a,c,120,'keyed');
  if(JSON.stringify(baseline.finalAircraftPosition)!==JSON.stringify(keyed.finalAircraftPosition)) throw new Error('transform mismatch');
  cases.push({baseline,keyed});
}
globalThis.__sceneBenchmark={schema_version:'1.0',synthetic_only:true,baseline_source_commit:'dcb3df934e86c3d834aa6a0409ec5fd5feb2f7e3',cases,gpu_completion_ms:null,physical_display_onset_ms:null,scope:'CPU dynamic object updates with identical schematic models; excludes renderer, label layout, terrain, transport and physical display'};
`;
const sceneSource = readFileSync(path.join(root,"src/lib/simulation/presentation/scene.ts"),"utf8");
const models = sceneSource.slice(sceneSource.indexOf("export function drone"),sceneSource.indexOf("export interface SceneOptions"));
const operational = readFileSync(path.join(root,"src/lib/simulation/presentation/operational-objects.ts"),"utf8");
const contracts = readFileSync(path.join(root,"src/lib/simulation/presentation/contracts.ts"),"utf8");
const heading = contracts.match(/export function headingRadians[\s\S]*?\n}/)?.[0];
if (!heading || !models) throw new Error("Benchmark source boundary changed");
const source = [heading,models,operational,moduleSource].join("\n").replace(/^import .*$/gm,"").replace(/^export /gm,"");
const compiled = ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.None}});
// Execute only the checked local model/update functions and benchmark above.
Function("THREE", compiled.outputText)(THREE);
const report = { ...globalThis.__sceneBenchmark, node: process.version,
  source_commit: execFileSync("git", ["-C", root, "rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
  implementation_sha256: createHash("sha256").update(readFileSync(path.join(root,"src/lib/simulation/presentation/operational-objects.ts"))).digest("hex") };
writeFileSync(process.argv[2] || path.join(root,"scene-benchmark.json"), JSON.stringify(report,null,2)+"\n");
console.log(JSON.stringify(report));
