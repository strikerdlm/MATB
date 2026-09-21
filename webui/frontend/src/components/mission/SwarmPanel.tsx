"use client";
import React, {useState} from "react";
import type {WorldSnapshot, Locale, CommandKind} from "@/types/simulation";
export function SwarmPanel({snapshot,locale,disabled,onCommand}:{snapshot:WorldSnapshot;locale:Locale;disabled:boolean;onCommand:(kind:CommandKind,payload:Record<string,unknown>)=>void}) {
  const [selected,setSelected]=useState(""); const [sector,setSector]=useState(""); const [formation,setFormation]=useState("line");
  const [x,setX]=useState("3500"),[y,setY]=useState("4000");
  const groups=snapshot.swarms??{}, id=groups[selected]?selected:Object.keys(groups)[0],group=groups[id];
  if(!group) return null;
  const es=locale==="es-CO", target=snapshot.sectors[sector]?sector:Object.keys(snapshot.sectors)[0];
  const task=(action:string)=>onCommand("SWARM_TASK",{group_id:id,action,target_id:action==="SEARCH"?target:""});
  const xM=Number(x),yM=Number(y),bounds=snapshot.terrain.bounds;
  const valid=x.trim()!==""&&y.trim()!==""&&Number.isFinite(xM)&&Number.isFinite(yM)&&xM*1000>=bounds.min_x_mm&&xM*1000<=bounds.max_x_mm&&yM*1000>=bounds.min_y_mm&&yM*1000<=bounds.max_y_mm;
  return <section className="mission-panel space-y-3 p-3" aria-label={es?"Control del enjambre":"Swarm control"}>
    <h2 className="text-sm font-semibold">{es?"Supervisión de enjambre":"Swarm supervision"}</h2>
    <label className="block text-xs">{es?"Grupo de mando":"Command group"} <select className="bg-background p-1" value={id} onChange={e=>setSelected(e.target.value)} disabled={disabled}>{Object.keys(groups).map(g=><option key={g}>{g}</option>)}</select></label>
    <p className="font-mono text-xs">{group.members.length} {es?"miembros":"members"} · {group.status} · {group.activity ?? group.task}</p>
    <p className="text-xs">{es?"Error de formación":"Formation error"}: {group.formation_error_mm===null?"—":`${(group.formation_error_mm/1000).toFixed(1)} m`} · {es?"Órdenes":"Commands"}: {group.command_count}</p>
    {group.last_response_ms!==null&&<p className="text-xs">{es?"Respuesta a falla":"Fault response"}: {(group.last_response_ms/1000).toFixed(1)} s</p>}
    <fieldset disabled={disabled} className="space-y-2">
      <legend className="text-xs">{es?"Asignar tarea al grupo":"Assign group task"}</legend>
      <label className="block text-xs">{es?"Sector":"Sector"} <select className="bg-background p-1" value={target} onChange={e=>setSector(e.target.value)}>{Object.keys(snapshot.sectors).map(s=><option key={s}>{s}</option>)}</select></label>
      <button className="rounded border px-2 py-1 text-xs" disabled={!group.members.length} onClick={()=>task("SEARCH")}>{es?"Búsqueda cooperativa":"Cooperative search"}</button>
      <div className="flex flex-wrap gap-2">{(["HOLD","RESUME","RETURN"] as const).map(action=><button className="rounded border px-2 py-1 text-xs" disabled={!group.members.length} key={action} onClick={()=>task(action)}>{es?{HOLD:"Mantener",RESUME:"Reanudar",RETURN:"Regresar"}[action]:{HOLD:"Hold",RESUME:"Resume",RETURN:"Return"}[action]}</button>)}</div>
      <label className="block text-xs">{es?"Formación":"Formation"} <select className="bg-background p-1" value={formation} onChange={e=>setFormation(e.target.value)}><option value="line">{es?"Línea":"Line"}</option><option value="wedge">{es?"Cuña":"Wedge"}</option></select></label>
      <div className="flex gap-2">{[["X",x,setX],["Y",y,setY]].map(([name,value,setter])=><label key={name as string} className="text-xs">{name as string} (m)<input aria-label={`${name} (m)`} className="block w-20 rounded border bg-background p-1" type="number" value={value as string} onChange={e=>(setter as (v:string)=>void)(e.target.value)}/></label>)}</div>
      <button className="rounded border px-2 py-1 text-xs" disabled={!valid||!group.members.length} onClick={()=>onCommand("SWARM_WAYPOINT",{group_id:id,waypoint:{x_mm:Math.round(xM*1000),y_mm:Math.round(yM*1000)},formation})}>{es?"Tránsito en formación":"Formation transit"}</button>
      <details><summary className="cursor-pointer text-xs">{es ? "Miembros y control individual" : "Members and individual control"}</summary><div className="space-y-1">{Object.keys(snapshot.aircraft).sort().map(a=>{const member=group.members.includes(a),other=Object.values(groups).some(g=>g.members.includes(a));return <div key={a} className="flex justify-between text-xs"><span>{a}</span><button className="underline" disabled={!member&&other} onClick={()=>onCommand("SWARM_MEMBERSHIP",{group_id:id,aircraft_id:a,action:member?"DETACH":"JOIN"})}>{member?(es?"Separar":"Detach"):(es?"Incorporar":"Join")}</button></div>;})}</div></details>
    </fieldset>
    <p className="text-[11px] text-muted-foreground">{es?"Separe un miembro para control individual. Mantenga el grupo y la aeronave antes de incorporar. Ranuras y líneas discontinuas: formación prevista, no enlaces de radio.":"Detach a member for individual control. Hold group and aircraft before joining. Slots and dashed lines show planned formation, not radio links."}</p>
  </section>;
}
