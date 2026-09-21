import React from "react";
import type { Locale, WorldSnapshot, PointMM } from "@/types/simulation";
export function SwarmInset({snapshot,locale}:{snapshot:WorldSnapshot;locale:Locale}) {
  const b=snapshot.terrain.bounds, width=Math.max(1,b.max_x_mm-b.min_x_mm),height=Math.max(1,b.max_y_mm-b.min_y_mm);
  const x=(p:PointMM)=>(p.x_mm-b.min_x_mm)/width*240, y=(p:PointMM)=>160-(p.y_mm-b.min_y_mm)/height*160;
  return <figure className="pointer-events-none absolute bottom-3 right-3 w-60 rounded border border-cyan-300/40 bg-slate-950/95 p-2 text-cyan-100" aria-label={locale==="en"?"North-up swarm overview":"Vista del enjambre orientada al norte"}>
    <figcaption className="text-[10px] uppercase tracking-widest">N ↑ · {locale==="en"?"Mission overview":"Vista de misión"}</figcaption>
    <svg viewBox="0 0 240 160" role="img" aria-label={locale==="en"?"Aircraft positions and coverage":"Posiciones y cobertura"}>
      {Object.entries(snapshot.coverage.sectors).map(([id,s])=><g key={id}>{s.covered_cells.map(([cx,cy])=>{const p={x_mm:snapshot.coverage.origin.x_mm+cx*snapshot.coverage.grid_cell_mm,y_mm:snapshot.coverage.origin.y_mm+cy*snapshot.coverage.grid_cell_mm};return <rect key={`${cx}:${cy}`} x={x(p)} y={y(p)-snapshot.coverage.grid_cell_mm/height*160} width={snapshot.coverage.grid_cell_mm/width*240} height={snapshot.coverage.grid_cell_mm/height*160} fill="#34d399" opacity=".35"/>;})}</g>)}
      {Object.entries(snapshot.sectors).map(([id,ps])=><polygon key={id} points={ps.map(p=>`${x(p)},${y(p)}`).join(" ")} fill="none" stroke="#286773" strokeWidth=".7"/>)}
      {Object.entries(snapshot.restricted_zones).map(([id,ps])=><polygon key={id} points={ps.map(p=>`${x(p)},${y(p)}`).join(" ")} fill="#ff526f" opacity=".3" stroke="#ff526f"/>)}
      {Object.values(snapshot.aircraft).map(a=><g key={a.aircraft_id}><circle cx={x(a.position)} cy={y(a.position)} r="2.5" fill={a.link==="LOST"?"#ff526f":"#2ee6c5"}/><text x={x(a.position)+4} y={y(a.position)-4} fontSize="7" fill="white">{a.aircraft_id}</text></g>)}
    </svg>
  </figure>;
}
