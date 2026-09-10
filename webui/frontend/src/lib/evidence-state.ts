type Copy = (spanish: string, english: string) => string;
const labels: Record<string, [string, string]> = {
  study: ["Estudio", "Study"], practice: ["Práctica", "Practice"], exploration: ["Exploración", "Exploration"],
  pending: ["Pendiente", "Pending"], processing_failed: ["Error de procesamiento", "Processing failed"],
  partially_excluded: ["Procesada; resultados con exclusiones", "Processed; results have exclusions"],
  reconciled: ["Procesada", "Processed"], not_qualified: ["Sin cualificar", "Not qualified"],
  linked_evidence: ["Informe vinculado; revisar alcance", "Linked report; review scope"],
  not_assessed: ["Sin evaluar", "Not assessed"],
};
export function evidenceStateLabel(state: string, copy: Copy): string {
  return labels[state] ? copy(...labels[state]) : copy("Estado sin confirmar", "Status unconfirmed");
}
