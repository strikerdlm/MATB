/** Stored policy codes are stable; researchers read translated choices. */
const choices: Record<string, [string, string]> = {
  before_baseline: ["Antes de la línea base", "Before baseline"],
  prescribed_later: [
    "Entrenamiento posterior prescrito",
    "Prescribed later training",
  ],
  true: ["Sí", "Yes"],
  false: ["No", "No"],
  explicit: [
    "Selección explícita del investigador",
    "Explicit researcher selection",
  ],
  first_finished: ["Primer intento finalizado", "First finished attempt"],
  latest_finished: ["Último intento finalizado", "Latest finished attempt"],
  assigned: ["Todas las evaluaciones asignadas", "All assigned assessments"],
  started: ["Evaluaciones iniciadas", "Started assessments"],
  finished: ["Evaluaciones finalizadas", "Finished assessments"],
  exclude_outcome: [
    "Excluir solo el resultado faltante",
    "Exclude only the missing outcome",
  ],
  complete_case: ["Usar únicamente casos completos", "Use complete cases only"],
  complete_verified: [
    "Exigir fuente completa y verificada",
    "Require complete verified source",
  ],
  report_status: [
    "Informar estado sin exigir aprobación",
    "Report status without requiring a pass",
  ],
  qualified: ["Exigir calificación física", "Require physical qualification"],
  calibrated: ["Exigir calibración humana", "Require human calibration"],
  prepared: [
    "Exigir preparación del participante",
    "Require participant preparation",
  ],
  valid: ["Exigir elegibilidad del protocolo", "Require protocol eligibility"],
  identical_only: [
    "Agrupar solo configuraciones idénticas",
    "Pool identical configurations only",
  ],
  explicit_review: [
    "Agrupar diferencias con revisión documentada",
    "Pool differences with documented review",
  ],
  retain_available: [
    "Conservar resultados disponibles",
    "Retain available outcomes",
  ],
  exclude_attempt: [
    "Excluir el intento interrumpido",
    "Exclude the interrupted attempt",
  ],
  gte: ["Mayor o igual que (≥)", "Greater than or equal to (≥)"],
  lte: ["Menor o igual que (≤)", "Less than or equal to (≤)"],
  eq: ["Igual a (=)", "Equal to (=)"],
  intentional_repeat: ["Repetición intencional", "Intentional repeat"],
  withdrawal: ["Retiro del participante", "Participant withdrawal"],
  operator_stop: ["Detención por el operador", "Operator stop"],
  hardware_failure: ["Fallo de hardware", "Hardware failure"],
  software_failure: ["Fallo de software", "Software failure"],
  planned_interruption: ["Interrupción planificada", "Planned interruption"],
  unknown: ["Causa desconocida", "Unknown cause"],
  participant_stop: ["Detención por el participante", "Participant stop"],
  technical_failure: ["Fallo técnico registrado", "Recorded technical failure"],
  lost_connection: ["Pérdida de conexión", "Lost connection"],
  other: ["Otra causa registrada", "Other recorded cause"],
  participant: ["Participante", "Participant"],
  visit: ["Visita", "Visit"],
  attempt: ["Intento", "Attempt"],
  individual: ["Resultado individual", "Individual result"],
  mean: ["Media aritmética", "Arithmetic mean"],
  median: ["Mediana", "Median"],
  "comprehension.correct_fraction": [
    "Proporción de respuestas correctas",
    "Fraction of correct answers",
  ],
  "pvt.median_rt_ms": [
    "Mediana del tiempo de reacción PVT (ms)",
    "PVT median reaction time (ms)",
  ],
  "pvt.lapses": ["Lapsos PVT", "PVT lapses"],
  "screen.simple_rt": [
    "Tiempo de reacción simple del cribado",
    "Screen simple reaction time",
  ],
  "sysmon.hit_rate": ["Proporción de detecciones SYSMON", "SYSMON hit rate"],
  "track.rmse_deviation": [
    "Desviación RMSE de seguimiento",
    "Tracking RMSE deviation",
  ],
};
export function policyChoice(
  code: string,
  copy: (es: string, en: string) => string,
) {
  const value = choices[code];
  return value ? copy(...value) : code;
}
