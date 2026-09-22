import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {RoomEnvironment} from 'three/addons/environments/RoomEnvironment.js';
import {createDrone} from './redline/drone.js';

/** REDLINE source dimensions: metres, +Y up, aircraft nose -Z. */
export function createDroneViewer(host:HTMLElement){
 const scene=new THREE.Scene();scene.background=new THREE.Color('#07111f');
 const camera=new THREE.PerspectiveCamera(34,1,.005,12);
 const renderer=new THREE.WebGLRenderer({antialias:true});
 renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));renderer.outputColorSpace=THREE.SRGBColorSpace;
 renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.05;host.append(renderer.domElement);
 const room=new RoomEnvironment(),pmrem=new THREE.PMREMGenerator(renderer),environment=pmrem.fromScene(room,.03);
 scene.environment=environment.texture;scene.environmentIntensity=.85;room.dispose();pmrem.dispose();
 scene.add(new THREE.HemisphereLight(0xe4f2ff,0x243247,2.3));
 for(const [color,intensity,x,y,z] of [[0xffefdb,3.3,.6,.9,-.7],[0x75cfff,1.2,-.7,.3,.5],[0xffffff,2,0,.5,.8]]){
  const light=new THREE.DirectionalLight(color,intensity);light.position.set(x,y,z);scene.add(light);
 }
 const model=createDrone();scene.add(model.root);
 const grid=new THREE.GridHelper(1.3,26,0x254e61,0x102332);grid.position.y=-.05;scene.add(grid);
 const ring=new THREE.Mesh(new THREE.TorusGeometry(.25,.001,8,128),new THREE.MeshStandardMaterial({color:0xe6bb69,metalness:.4,roughness:.4}));
 ring.rotation.x=-Math.PI/2;ring.position.y=-.049;scene.add(ring);
 const controls=new OrbitControls(camera,renderer.domElement);controls.target.set(0,.035,0);controls.minDistance=.24;controls.maxDistance=1.5;controls.maxPolarAngle=Math.PI*.49;
 let raf=0,last=0,time=0,playing=false,disposed=false;
 const intervals:number[]=[];
 function render(){if(!disposed)renderer.render(scene,camera);}
 function setTime(seconds:number){
  if(!Number.isFinite(seconds))throw Error('Time must be finite');
  time=seconds;
  const t=seconds%32;
  const smooth=(v:number)=>{v=THREE.MathUtils.clamp(v,0,1);return v*v*(3-2*v);};
  const explosion=.7*smooth((t-8)/4)*(1-smooth((t-19)/4));
  model.setExplode(explosion);model.setTime(t*.026);
  model.root.position.y=Math.sin(t*.6)*.008;
  model.root.rotation.y=t*.065;
  const angle=-.60+Math.sin(t*.12)*.27;
  camera.position.set(Math.sin(angle)*.65,.31+explosion*.18,-Math.cos(angle)*.65);
  controls.target.set(0,.035+explosion*.07,0);controls.update();render();
 }
 function resize(){const box=host.getBoundingClientRect();renderer.setSize(box.width,box.height);camera.aspect=box.width/Math.max(1,box.height);camera.updateProjectionMatrix();render();}
 function tick(now:number){if(disposed)return;if(last){const dt=Math.min((now-last)/1000,.05);if(intervals.length<1000)intervals.push(now-last);setTime(time+dt);}last=now;raf=playing&&!document.hidden?requestAnimationFrame(tick):0;}
 function setPlaying(value:boolean){playing=value;last=0;cancelAnimationFrame(raf);if(value&&!document.hidden)raf=requestAnimationFrame(tick);}
 const visibility=()=>setPlaying(playing);document.addEventListener('visibilitychange',visibility);
 const observer=new ResizeObserver(resize);observer.observe(host);controls.addEventListener('change',render);
 setTime(0);resize();setPlaying(!matchMedia('(prefers-reduced-motion: reduce)').matches);
 return {setTime,setPlaying,model,
  metrics(){const sorted=[...intervals].sort((a,b)=>a-b);return{three:THREE.REVISION,assemblies:model.parts.length,rotors:model.rotors.length,drawCalls:renderer.info.render.calls,triangles:renderer.info.render.triangles,frames:sorted.length,medianMs:sorted[Math.floor(sorted.length*.5)],p95Ms:sorted[Math.floor(sorted.length*.95)],dpr:renderer.getPixelRatio(),viewport:[host.clientWidth,host.clientHeight]};},
  dispose(){disposed=true;setPlaying(false);observer.disconnect();document.removeEventListener('visibilitychange',visibility);controls.dispose();model.dispose();environment.dispose();grid.geometry.dispose();(grid.material as THREE.Material).dispose();ring.geometry.dispose();ring.material.dispose();renderer.dispose();renderer.domElement.remove();}
 };
}
