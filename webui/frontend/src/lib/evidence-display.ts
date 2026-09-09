import type { EvidenceMetric } from "./evidence";

const metrics: Record<string, [string, string, string]> = {
  sysmon_dprime_observed_v2: ["SYSMON", "Sensibilidad a señales observadas (d′)", "Observed signal sensitivity (d′)"],
  sysmon_hit_rate: ["SYSMON", "Tasa de aciertos", "Hit rate"],
  sysmon_mean_rt_ms: ["SYSMON", "Tiempo medio de respuesta", "Mean response time"],
  track_rmse_deviation: ["TRACK", "Error de seguimiento (RMSE)", "Tracking error (RMSE)"],
  track_percent_time_in_target: ["TRACK", "Tiempo dentro del objetivo", "Time inside target"],
  resman_mean_absolute_deviation: ["RESMAN", "Desviación absoluta media", "Mean absolute deviation"],
  resman_percent_time_in_tolerance: ["RESMAN", "Tiempo dentro de tolerancia", "Time within tolerance"],
  comm_d_prime: ["COMM", "Sensibilidad de comunicaciones (d′)", "Communication sensitivity (d′)"],
  nasatlx_rtlx_mean_0_100: ["RTLX", "Carga de trabajo sin ponderar", "Unweighted workload"],
  bedford: ["BEDFORD", "Calificación Bedford", "Bedford rating"],
  isa_mean: ["ISA", "Carga de trabajo instantánea media", "Mean instantaneous workload"],
};
export function metricDisplay(metric: EvidenceMetric, es: boolean) {
  const entry = metrics[metric.metric] ?? ["", metric.metric, metric.metric];
  const units: Record<string, string> = { percent: "%", dimensionless: "", score_0_100: "0–100",
    milliseconds: "ms", ms: "ms", proportion: es ? "proporción" : "proportion",
    normalized_cursor_distance: es ? "distancia normalizada" : "normalized distance",
    ordinal_score_1_10: "1–10", tank_level_units: es ? "unidades de nivel" : "level units" };
  return { task: entry[0], name: entry[es ? 1 : 2], unit: units[metric.definition.unit] ?? metric.definition.unit,
    value: metric.value === null ? "—" : new Intl.NumberFormat(es ? "es-CO" : "en", {
      maximumFractionDigits: ["ms", "milliseconds"].includes(metric.definition.unit) ? 1 : 3,
    }).format(metric.value) };
}
const exclusions: Record<string, [string, string]> = {
  physical_audio_onset_not_qualified: ["No se ha cualificado el inicio físico del audio.", "Physical audio onset has not been qualified."],
  metric_definition_not_confirmatory: ["Esta definición solo permite análisis descriptivo.", "This metric definition supports descriptive analysis only."],
  task_or_probe_not_administered: ["Esta tarea o pregunta no se administró en el bloque.", "This task or probe was not administered in this block."],
  missing_opportunity_actor: ["No consta quién respondió a una oportunidad.", "The record does not identify who responded to an opportunity."],
  incomplete_or_automated_opportunities: ["Las oportunidades están incompletas o incluyen respuestas automatizadas.", "Opportunities are incomplete or include automated responses."],
  missing_or_duplicate_software_receipt: ["Falta una observación temporal de recepción o está duplicada.", "A software receipt observation is missing or duplicated."],
  interrupted_or_failed_block: ["El bloque se interrumpió o falló.", "The block was interrupted or failed."],
  provisional_source_provenance: ["La procedencia de adquisición está incompleta.", "Acquisition provenance is incomplete."],
  non_study_capture: ["Esta captura corresponde a práctica o exploración.", "This capture belongs to practice or exploration."],
  missing_or_invalid_metric_inputs: ["Faltan datos requeridos o no son válidos para el cálculo.", "Required metric inputs are missing or invalid."],
  incomplete_or_invalid_questionnaire: ["El cuestionario está incompleto o contiene respuestas no válidas.", "The questionnaire is incomplete or contains invalid responses."],
};
export function exclusionText(code: string, es: boolean): string {
  return exclusions[code]?.[es ? 0 : 1] ?? (es ? "Revise la incidencia en los registros de origen." : "Review this finding in the source records.");
}
