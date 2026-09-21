import * as THREE from "three";
import type { WorldSnapshot, PointMM } from "@/types/simulation";
export const SWARM_COLORS = [0x2ee6c5, 0xffbd69, 0x99aaff, 0xff8cab];
/** Trails come from recorded public snapshots, so seeking never invents a path. */
export function swarmOverlays(parent: THREE.Group, world: (point: PointMM, height: number) => [number, number, number]) {
  const root=new THREE.Group(); root.name="swarm-overlays"; parent.add(root);
  const lines=new Map<string,THREE.Line>(); let lastKey="";
  function line(id: string, points: THREE.Vector3[], color: number, dashed=false, fade=false) {
    let object=lines.get(id);
    if(!object) {
      object=new THREE.Line(new THREE.BufferGeometry(),dashed?new THREE.LineDashedMaterial({color,dashSize:12,gapSize:8,transparent:true,opacity:.65}):new THREE.LineBasicMaterial({color,vertexColors:fade,transparent:true,opacity:.8}));
      lines.set(id,object); root.add(object);
    }
    object.geometry.dispose(); object.geometry=new THREE.BufferGeometry().setFromPoints(points);
    if(fade) { const colors: number[]=[]; points.forEach((_,i)=>{const c=new THREE.Color(color).multiplyScalar(.15+.85*i/Math.max(1,points.length-1)); colors.push(c.r,c.g,c.b);}); object.geometry.setAttribute("color",new THREE.Float32BufferAttribute(colors,3)); }
    if(dashed) object.computeLineDistances();
  }
  function update(state: WorldSnapshot, visible: boolean) {
    root.visible=visible;
    const key=`${state.block_id}:${state.tick}:${state.state_version}`; if(key===lastKey) return; lastKey=key;
    const present=new Set<string>();
    Object.entries(state.swarms??{}).forEach(([gid,group],index)=>{
      const color=SWARM_COLORS[index%SWARM_COLORS.length];
      for(const [id,trail] of Object.entries(group.trails??{})) {
        const aircraft=state.aircraft[id]; if(!aircraft) continue;
        const key=`trail:${gid}:${id}`; present.add(key);
        line(key,trail.map(p=>new THREE.Vector3(...world(p,(aircraft.altitude_mm??120000)/1000))),color,false,true);
      }
      const anchors=group.members.filter(id=>group.slots[id]&&state.aircraft[id]);
      if(anchors.length) {
        const center={x_mm:anchors.reduce((v,id)=>v+state.aircraft[id].position.x_mm-group.slots[id].x_mm,0)/anchors.length,y_mm:anchors.reduce((v,id)=>v+state.aircraft[id].position.y_mm-group.slots[id].y_mm,0)/anchors.length};
        for(const id of anchors) {
          const a=state.aircraft[id], slot=group.slots[id], point={x_mm:center.x_mm+slot.x_mm,y_mm:center.y_mm+slot.y_mm};
          const target=new THREE.Vector3(...world(point,(a.altitude_mm??120000)/1000));
          const key=`slot:${gid}:${id}`; present.add(key);
          line(key,[new THREE.Vector3(...world(a.position,(a.altitude_mm??120000)/1000)),target],color,true);
          const marker=`marker:${gid}:${id}`;present.add(marker);
          line(marker,[target.clone().add(new THREE.Vector3(-8,0,0)),target.clone().add(new THREE.Vector3(8,0,0)),target,target.clone().add(new THREE.Vector3(0,0,-8)),target.clone().add(new THREE.Vector3(0,0,8))],color);
        }
      }
    });
    for(const alert of Object.values(state.alerts)) {
      if(!alert.kind.startsWith("SEPARATION")||alert.closed_sequence!==null) continue;
      const pair=alert.entity_ids.map(id=>state.aircraft[id]).filter(Boolean);
      if(pair.length!==2) continue;
      const key=`alert:${alert.alert_id}`; present.add(key);
      line(key,pair.map(a=>new THREE.Vector3(...world(a.position,(a.altitude_mm??120000)/1000))),0xff526f);
    }
    for(const [id,object] of lines) if(!present.has(id)) { root.remove(object);object.geometry.dispose();(object.material as THREE.Material).dispose();lines.delete(id); }
  }
  return {update,dispose(){for(const object of lines.values()){object.geometry.dispose();(object.material as THREE.Material).dispose();}lines.clear();root.clear();root.removeFromParent();}};
}
