import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const require=createRequire(path.join(root,'webui/frontend/package.json'));
const {chromium}=require('playwright');
const browser=await chromium.launch({channel:'chrome',headless:true});
try {
 const page=await browser.newPage({viewport:{width:1920,height:1080}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:3128/video/intro.html');
 await page.waitForFunction(()=>window.ready);
 const check=await page.evaluate(async()=>{
  const s=window.station;s.setPlaying(false);s.setTime(0);
  const m=s.model,poses=m.parts.map(p=>p.group.position.toArray());
  let finite=true;m.root.traverse(o=>{const a=o.geometry?.attributes.position.array;if(a)for(const x of a)if(!Number.isFinite(x))finite=false;});
  for(let i=0;i<10;i++){m.setExplode(1);m.setExplode(.37);m.setExplode(0);}
  const reassemblyExact=m.parts.every((p,i)=>p.group.position.toArray().every((x,j)=>Math.abs(x-poses[i][j])<1e-10));
  s.setTime(7);const rotations=m.rotors.map(p=>p.rotation.y);s.setTime(23);s.setTime(7);
  const deterministic=m.rotors.every((p,i)=>p.rotation.y===rotations[i]);
  const THREE=await import('/video/vendor/three.module.js');
  s.setTime(0);const bounds=new THREE.Box3().setFromObject(m.root).getSize(new THREE.Vector3()).toArray();
  return {finite,reassemblyExact,deterministic,boundsMetres:bounds,assemblies:m.parts.length,rotors:m.rotors.length};
 });
 await page.evaluate(()=>window.station.setTime(15));
 await page.screenshot({path:path.join(root,'EMAVI/revision/redline-exploded.png')});
 await page.evaluate(()=>window.station.dispose());
 check.consoleErrors=errors;check.browser=browser.version();
 fs.writeFileSync(path.join(root,'EMAVI/revision/redline.json'),JSON.stringify(check,null,2));
 console.log(JSON.stringify(check));
 if(!check.finite||!check.reassemblyExact||!check.deterministic||check.assemblies!==17||check.rotors!==4||errors.length)process.exitCode=1;
} finally {await browser.close();}
