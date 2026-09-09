"use client";
import type { WorldSnapshot, Locale } from "@/types/simulation";
import type { TrafficFrame } from "@/lib/geography/types";
import { displayedTraffic } from "@/lib/geography/coordinates";
import { cycleEntity, type Entity } from "@/lib/simulation/presentation/state";

export function ContactNavigator({ snapshot, traffic, elapsed, locale, focus, disabled, onSelect, category, onCategory }: {
  snapshot: WorldSnapshot; traffic?: TrafficFrame | null; elapsed: number; locale: Locale;
  focus: Entity | null; disabled: boolean; onSelect: (entity: Entity) => void;
  category: Entity["category"]; onCategory: (category: Entity["category"]) => void;
}) {
  const es = locale === "es-CO";
  const observed = displayedTraffic(traffic, elapsed);
  const ids = category === "aircraft" ? Object.keys(snapshot.aircraft) : category === "contact"
    ? Object.values(snapshot.contacts).filter(c => c.position && c.evidence !== "NONE").map(c => c.contact_id)
    : observed.map(t => t.id);
  const labels = es ? { aircraft: "Aeronaves simuladas", contact: "Contactos de tarea", observed: "Aeronaves observadas" }
    : { aircraft: "Simulated aircraft", contact: "Task contacts", observed: "Observed aircraft" };
  const aircraft = focus?.category === "aircraft" ? snapshot.aircraft[focus.id] : null;
  const contact = focus?.category === "contact" ? snapshot.contacts[focus.id] : null;
  const track = focus?.category === "observed" ? observed.find(t => t.id === focus.id) : null;
  return <section className="mission-panel space-y-2 p-3" aria-label={es ? "Navegación de contactos" : "Contact navigation"}>
    <select aria-label={es ? "Categoría" : "Category"} value={category} disabled={disabled} onChange={e => onCategory(e.target.value as Entity["category"])}>
      {Object.entries(labels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
    </select>
    {([-1, 1] as const).map(direction => <button key={direction} type="button" disabled={disabled || !ids.length} onClick={() => {
      const id = cycleEntity(ids, focus?.category === category ? focus.id : null, direction);
      if (id) onSelect({ category, id });
    }}>{direction === -1 ? es ? "Anterior" : "Previous" : es ? "Siguiente" : "Next"}</button>)}
    {focus && (aircraft || contact || track) && <div>
      <strong>{labels[focus.category]} · {focus.id}</strong>
      {aircraft && <p>{es ? "Enlace" : "Link"}: {aircraft.link} · {es ? "Sensor" : "Sensor"}: {aircraft.sensor}</p>}
      {contact && <p>{contact.workflow} · {contact.evidence}</p>}
      {track && <p>{track.source} · {track.callsign} · {es ? "Edad de observación" : "Observation age"}: {track.age_s.toFixed(1)} s</p>}
    </div>}
  </section>;
}
