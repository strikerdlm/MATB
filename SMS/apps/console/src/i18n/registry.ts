export type Locale = "en" | "es";

const labels = {
  en: {
    overview: "Mission overview",
    safetyReview: "Safety review",
    hazards: "Hazards",
    controls: "Controls",
    risk: "Risk assessment",
    profile: "Flight profile",
    telemetry: "Telemetry",
    evidence: "Evidence log",
    reports: "Reports",
    documents: "Documents",
    notes: "Crew notes",
    configuration: "Configuration",
    research: "Research",
    missionStrip: "Mission safety strip",
    highestBlocker: "Highest blocker",
    unclassified: "Unclassified · controlled safety metadata · do not export",
    mapCurrent: "Map package current",
    readOnlyTelemetry: "Read-only telemetry",
    evidenceLatest: "Evidence (latest)",
    notesSafety: "Notes (safety)",
    local: "Local",
    offline: "Offline",
    mapWorkspace: "Offline map workspace",
    statusNominal: "Nominal",
    networkDisconnected: "Disconnected",
    verified: "Verified",
    gateMaintenance: "Maintenance",
    gateOperator: "Operator",
    gateSafety: "Safety",
    gateCommander: "Commander",
    blocker: "Blocker",
    pending: "Pending",
    pass: "Pass",
  },
  es: {
    overview: "Resumen de misión",
    safetyReview: "Revisión de seguridad",
    hazards: "Peligros",
    controls: "Controles",
    risk: "Evaluación de riesgo",
    profile: "Perfil de vuelo",
    telemetry: "Telemetría",
    evidence: "Registro de evidencia",
    reports: "Informes",
    documents: "Documentos",
    notes: "Notas de tripulación",
    configuration: "Configuración",
    research: "Investigación",
    missionStrip: "Franja de seguridad de misión",
    highestBlocker: "Bloqueador principal",
    unclassified: "No clasificado · metadatos controlados de seguridad · no exportar",
    mapCurrent: "Paquete cartográfico vigente",
    readOnlyTelemetry: "Telemetría de solo lectura",
    evidenceLatest: "Evidencia (última)",
    notesSafety: "Notas (seguridad)",
    local: "Local",
    offline: "Sin conexión",
    mapWorkspace: "Espacio cartográfico sin conexión",
    statusNominal: "Nominal",
    networkDisconnected: "Desconectada",
    verified: "Verificada",
    gateMaintenance: "Mantenimiento",
    gateOperator: "Operador",
    gateSafety: "Seguridad",
    gateCommander: "Comandante",
    blocker: "Bloqueador",
    pending: "Pendiente",
    pass: "Aprobado",
  },
} as const;

export type Labels = (typeof labels)[Locale];

export function getLabels(locale: Locale): Labels {
  return labels[locale];
}

export function useLocale(locale: Locale): { locale: Locale; labels: Labels } {
  return { locale, labels: getLabels(locale) };
}

export function renderConcepts(locale: Locale): string[] {
  const current = getLabels(locale);
  return [current.missionStrip, current.gateMaintenance, current.gateOperator, current.gateSafety, current.gateCommander];
}
