/** Stable, locale-independent concepts used by safety explanations and blockers. */
export const CONCEPT_IDS = Object.freeze({
  configurationOutOfScope: "applicability.configuration.out-of-scope",
  missingOperatorPerAircraft: "operation.operator.per-aircraft.missing",
  swarmResearchNonDispatchable: "operation.swarm.research-only.non-dispatchable",
  autonomousFlightProhibited: "racae94.94-155.autonomous-flight.prohibited",
  supervisedAutomationEvidenceMissing: "racae94.94-155.supervised-automation.evidence-missing",
  ifrEvidenceIncomplete: "flight-rules.ifr.evidence-incomplete",
  policyNotApproved: "policy.approved-package.required",
} as const);

export type ConceptId = typeof CONCEPT_IDS[keyof typeof CONCEPT_IDS];

// Named aliases keep concept IDs stable for callers that do not use the map form.
export const CONCEPT_CONFIGURATION_OUT_OF_SCOPE = CONCEPT_IDS.configurationOutOfScope;
export const CONCEPT_MISSING_OPERATOR_PER_AIRCRAFT = CONCEPT_IDS.missingOperatorPerAircraft;
export const CONCEPT_SWARM_RESEARCH_NON_DISPATCHABLE = CONCEPT_IDS.swarmResearchNonDispatchable;
export const CONCEPT_AUTONOMOUS_FLIGHT_PROHIBITED = CONCEPT_IDS.autonomousFlightProhibited;
export const CONCEPT_IFR_EVIDENCE_INCOMPLETE = CONCEPT_IDS.ifrEvidenceIncomplete;

export const CONCEPT_LABELS: Readonly<Record<ConceptId, Readonly<{ es: string; en: string }>>> = Object.freeze({
  [CONCEPT_IDS.configurationOutOfScope]: { es: "Configuración fuera de alcance", en: "Configuration outside scope" },
  [CONCEPT_IDS.missingOperatorPerAircraft]: { es: "Falta operador por aeronave", en: "Operator missing per aircraft" },
  [CONCEPT_IDS.swarmResearchNonDispatchable]: { es: "Enjambre solo de investigación; no despachable", en: "Research-only swarm; non-dispatchable" },
  [CONCEPT_IDS.autonomousFlightProhibited]: { es: "Vuelo autónomo prohibido", en: "Autonomous flight prohibited" },
  [CONCEPT_IDS.supervisedAutomationEvidenceMissing]: { es: "Falta evidencia de automatización supervisada", en: "Supervised automation evidence missing" },
  [CONCEPT_IDS.ifrEvidenceIncomplete]: { es: "Evidencia IFR incompleta", en: "IFR evidence incomplete" },
  [CONCEPT_IDS.policyNotApproved]: { es: "Se requiere paquete de política aprobado", en: "Approved policy package required" },
});

export function explainConcept(conceptId: ConceptId, locale: "es" | "en"): string {
  return CONCEPT_LABELS[conceptId][locale];
}
