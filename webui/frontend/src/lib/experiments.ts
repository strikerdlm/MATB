export type ExperimentId = "openmatb" | "suas" | "liftoff" | "screen" | "pvt" | "physiology";
export type ExecutionPurpose = "practice" | "study";
type Bilingual = readonly [string, string];
export interface ExperimentInfo {
  id: ExperimentId; route: string; title: Bilingual; summary: Bilingual;
  actions: Bilingual; duration: Bilingual; equipment: Bilingual; results: Bilingual;
}
export const EXPERIMENTS: readonly ExperimentInfo[] = [
  { id: "openmatb", route: "/openmatb/setup", title: ["OpenMATB · Cuatro tareas", "OpenMATB · Four tasks"],
    summary: ["Atención y coordinación al realizar varias tareas a la vez.", "Attention and coordination while performing several tasks at once."],
    actions: ["Mantenga un cursor en su objetivo, escuche mensajes, detecte fallas y controle bombas. La Batería de Tareas Múltiples (MATB) le enseña cada control antes de comenzar.", "Keep a cursor on target, listen to messages, detect faults, and operate pumps. The Multi-Attribute Task Battery (MATB) introduces each control before you begin."],
    duration: ["Perfil estándar: 3 min de práctica + tres bloques de 15 min y cuestionarios. Revise el perfil antes de iniciar.", "Standard profile: 3-minute practice + three 15-minute blocks and questionnaires. Review the profile before starting."],
    equipment: ["Computador con OpenMATB, pantalla, audio y mouse o joystick.", "Computer with OpenMATB, display, audio, and mouse or joystick."],
    results: ["Aciertos, tiempo de respuesta, error de seguimiento y carga percibida por bloque. Cada tarea conserva sus propias medidas.", "Accuracy, response time, tracking error, and perceived workload for each block. Each task retains its own measures."] },
  { id: "suas", route: "/mission/setup", title: ["Misión sUAS · Supervisión", "sUAS mission · Supervision"],
    summary: ["Supervisión de pequeñas aeronaves no tripuladas en una misión sintética.", "Supervision of small unmanned aircraft systems in a synthetic mission."],
    actions: ["Seleccione aeronaves, asigne sectores, atienda alertas y reporte contactos. Practique primero con el mapa y los controles.", "Select aircraft, assign sectors, respond to alerts, and report contacts. First practice using the map and controls."],
    duration: ["Depende del escenario y del perfil; se muestra al preparar. El estudio requiere KSS y PVT antes de la misión.", "Depends on the scenario and profile; shown during preparation. Study sessions require KSS and PVT before the mission."],
    equipment: ["Computador, navegador, teclado y mouse. La misión utiliza aeronaves simuladas.", "Computer, browser, keyboard, and mouse. The mission uses simulated aircraft."],
    results: ["Cobertura, contactos, respuesta a alertas y cuestionarios. Los valores describen esta misión simulada.", "Coverage, contacts, alert responses, and questionnaires. Values describe this simulated mission."] },
  { id: "liftoff", route: "/liftoff/setup", title: ["Liftoff · Vuelo simulado", "Liftoff · Simulated flight"],
    summary: ["Desempeño de vuelo en primera persona (FPV) dentro del simulador.", "First-person view (FPV) flight performance within the simulator."],
    actions: ["Siga el circuito con su controlador. La consola lo guía por la línea basal, el vuelo y la recuperación; después se registran los resultados visibles.", "Fly the course using your controller. The console guides baseline, flight, and recovery; visible results are then recorded."],
    duration: ["Según el protocolo y circuito seleccionados, con línea basal y recuperación.", "According to the selected protocol and course, including baseline and recovery."],
    equipment: ["Liftoff instalado, controlador configurado y telemetría activa. Polar H10 es opcional cuando se declara desempeño sin fisiología.", "Installed Liftoff, configured controller, and active telemetry. Polar H10 is optional when performance-only collection is declared."],
    results: ["Tiempos de vuelta, vueltas completadas y medidas de telemetría con sus unidades disponibles.", "Lap times, completed laps, and telemetry measures with their available units."] },
  { id: "screen", route: "/screen", title: ["Batería cognitiva · Cuatro pruebas", "Cognitive battery · Four tests"],
    summary: ["Reacción simple, elección de respuesta, memoria de trabajo y seguimiento.", "Simple reaction, response choice, working memory, and tracking."],
    actions: ["Pulse al ver un círculo, elija la dirección de una flecha, detecte letras repetidas dos posiciones atrás y siga un punto con el mouse. Cada prueba incluye instrucciones y práctica.", "Respond to a circle, choose an arrow’s direction, detect letters repeated two positions earlier, and follow a point with the mouse. Each test includes instructions and practice."],
    duration: ["Aproximadamente 6–8 min; depende del ritmo de respuesta y lectura.", "Approximately 6–8 minutes, depending on response and reading time."],
    equipment: ["Computador, teclado con flechas y barra espaciadora, y mouse.", "Computer, keyboard with arrow keys and space bar, and mouse."],
    results: ["Tiempo de reacción en milisegundos, precisión, sensibilidad de detección y error de seguimiento. Son medidas de investigación, sin diagnóstico automático.", "Reaction time in milliseconds, accuracy, detection sensitivity, and tracking error. These are research measures without automatic diagnosis."] },
  { id: "pvt", route: "/pvt", title: ["KSS + PVT · Somnolencia y vigilancia", "KSS + PVT · Sleepiness and vigilance"],
    summary: ["Somnolencia percibida y rapidez para responder a una señal visual.", "Perceived sleepiness and speed of response to a visual signal."],
    actions: ["Primero responda la Escala de Somnolencia de Karolinska (KSS). Después pulse la barra espaciadora al aparecer el contador del Test de Vigilancia Psicomotora (PVT).", "First answer the Karolinska Sleepiness Scale (KSS). Then press the space bar when the counter appears in the Psychomotor Vigilance Test (PVT)."],
    duration: ["Estudio: 10 min de PVT, más KSS e instrucciones. Práctica: 1 min de familiarización.", "Study: 10-minute PVT, plus KSS and instructions. Practice: 1-minute familiarization."],
    equipment: ["Navegador en primer plano, teclado o área de respuesta en pantalla.", "Foreground browser, keyboard or on-screen response area."],
    results: ["Mediana del tiempo de reacción, lapsos de 500 ms o más, anticipaciones y respuestas ausentes. Las interrupciones se indican en el resultado.", "Median reaction time, lapses of 500 ms or longer, false starts, and missing responses. Interruptions are indicated in the result."] },
  { id: "physiology", route: "/physiology/polar-h10", title: ["Polar H10 · Registro fisiológico", "Polar H10 · Physiology recording"],
    summary: ["Registro de señales cardiacas y movimiento durante reposo o tareas.", "Recording of cardiac signals and movement during rest or tasks."],
    actions: ["Coloque la banda, conecte el sensor y revise la señal. Para la línea basal, permanezca quieto durante el registro y espere la confirmación de guardado.", "Fit the chest strap, connect the sensor, and check the signal. For baseline recording, remain still and wait for saving confirmation."],
    duration: ["Al menos 5 min de señal útil por ventana de análisis basal.", "At least 5 minutes of usable signal per baseline analysis window."],
    equipment: ["Banda Polar H10, Bluetooth y componente de fisiología instalado.", "Polar H10 chest strap, Bluetooth, and installed physiology component."],
    results: ["Frecuencia cardiaca, variabilidad de intervalos entre latidos y calidad de señal. Si falta evidencia suficiente, se explica por qué no se calcula una medida.", "Heart rate, beat-to-beat interval variability, and signal quality. When evidence is insufficient, the reason a measure cannot be calculated is explained."] },
];
export function experimentForRoute(path: string): ExperimentInfo | undefined {
  return EXPERIMENTS.find((item) => path === item.route || path.startsWith(item.route.split("/setup")[0] + "/")
    || (item.id === "suas" && path.startsWith("/mission")) || (item.id === "openmatb" && path.startsWith("/openmatb")));
}
export interface CatalogEntry {
  id: ExperimentId; route: string; component_id: string | null; component_available: boolean;
  supported_modes: ExecutionPurpose[]; readiness_url: string | null; configuration_url: string | null;
  profiles: string[]; duration_seconds: number | null; study_prerequisites: string[];
  unavailable_reason: string | null;
}
