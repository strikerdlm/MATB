import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { SourceRegister } from "@fac-isr/evidence";
import type { SourceRecord } from "@fac-isr/evidence";
import { describe, expect, it } from "vitest";
import {
  buildControlledTranslation,
  normalizeRequirement,
  validateRequirementCitations,
} from "../src/normalize.js";
import type { NormalizationInput, ReviewedNormalizedRequirement } from "../src/normalize.js";

const extractionSha = "77cc55931dd862884751fc2510ef4d16def1546e8712195fff2500f2ea482a69";
const root = resolve(process.cwd(), "../..");

function source(overrides: Partial<SourceRecord> = {}): SourceRecord {
  return {
    sourceId: "racae-94-enm2" as never,
    title: "RACAE 94 Enmienda 2",
    authority: "AAAES",
    authorityRank: 1,
    canonicalUri: "https://aaaes.fac.mil.co/racae94.pdf",
    localPath: "docs/regulations/original/racae94.pdf",
    mediaType: "application/pdf",
    language: "es",
    retrievedAtUtc: "2026-08-08T17:54:59Z",
    sha256: "312458744b5e4f5097492d4b1c58b0e05229cc5e738058c757d4464e0f155976",
    extractionSha256: extractionSha,
    extractionPath: "docs/regulations/extracted/racae_94_enm2.txt",
    sensitivity: "unclassified-controlled",
    licenseOrRestriction: "Official public source",
    review: "accepted",
    reviewerId: "qualified-reviewer",
    reviewSignature: "test-signature",
    reviewedAtUtc: "2026-08-08T18:00:00Z",
    validFromUtc: "2025-06-16T05:00:00Z",
    validUntilUtc: "2030-01-01T00:00:00Z",
    ...overrides,
  };
}

function input(overrides: Partial<NormalizationInput> = {}): NormalizationInput {
  return {
    sourceRefs: [{
      evidenceId: "racae94-94.155-a" as never,
      sourceId: "racae-94-enm2" as never,
      edition: "Enmienda 2",
      locator: { section: "94.155", page: 38, paragraph: "(a)" },
      quoteLanguage: "es",
      extractionSha256: extractionSha,
      reviewState: "accepted",
    }],
    Spanish: "La operación en modo de vuelo autónomo o con aeronaves autónomas está prohibida.",
    EnglishControlled: "Autonomous flight is prohibited.",
    applicabilityExpression: "state_aviation && uas_rpas_operation",
    severity: "hard",
    evidenceRequired: true,
    effectiveFromUtc: "2025-06-16T05:00:00Z",
    interpretationStatus: "qualified-review",
    predicate: "fac.racae94.autonomous-flight.prohibited",
    sourceLanguageReview: { status: "qualified-review", reviewerRole: "Spanish reviewer", reviewerId: "pending-review", rationale: "Pending qualified review." },
    applicabilityReview: { status: "pending", reviewerRole: "Operational authority", reviewerId: "pending-operational-review", rationale: "Pending operational review." },
    ...overrides,
  };
}

function register(record = source()): SourceRegister {
  const result = new SourceRegister();
  result.append(record);
  return result;
}

describe("RACAE 94 normalized evidence", () => {
  it("contains the six checksum-linked golden controls with exact section/page locators", async () => {
    const raw = await readFile(resolve(root, "docs/regulations/normalized/racae94-amendment-2.json"), "utf8");
    const artifact = JSON.parse(raw) as { source: { extractionSha256: string }; requirements: Array<ReviewedNormalizedRequirement & { sourceTextSpanish: string }> };
    expect(artifact.source.extractionSha256).toBe(extractionSha);
    const expected = new Map([
      ["94.155", 38], ["94.201", 39], ["94.250", 42], ["94.705", 66], ["94.710", 68], ["94.715", 69],
    ]);
    expect(artifact.requirements).toHaveLength(7);
    const expectedExcerptBySection: Record<string, string> = {
      "94.155": "(a) La operación en modo de vuelo autónomo o con aeronaves autónomas está prohibida.\n\n(b) El vuelo en modo automatizado supervisado, se permitirá en el empleo de UAS/RPAS en misiones de aspersión aérea de cultivos y/o vigilancia, registro fotográfico, verificación y monitoreo de terrenos y zonas de interés militar y/o policiales específicos, según los roles, misiones y capacidades distintivas de cada EAE. Sin embargo, en todo momento el operador o piloto de UAS/RPAS estará supervisando y monitoreando el vuelo y estará en la capacidad de realizar un cambio en el patrón de vuelo inminente, en el evento que se identifique cualquier riesgo, emergencia o a instrucciones del ATC.",
      "94.201": "(a) Un Piloto Remoto y/u Operador, no podrá comandar más de un UAS/RPAS al mismo tiempo, es decir, cada aeronave desde su encendido hasta su aterrizaje y con motores apagados, estará bajo el mando de un operador o piloto.",
      "94.250": "94.250 Operación de UAS/RPAS en enjambre\n[Reservado]",
      "94.705": "(a) La autorización que emita cada EAE para la operación de sus UAS/RPAS en una ubicación geográfica determinada, debe obedecer a la medición efectiva de la tolerabilidad del riesgo, producto de la estructuración de la Matriz de Gestión de Riesgos, para tal efecto, debe establecer la Identificación de peligros específicos en la operación de UAS y RPAS, Evaluación de riesgos mediante matrices de probabilidad y severidad, Definición de niveles aceptables de seguridad operacional (NASO) específicos para la operación y Políticas de seguridad operacional, alineadas con la misionalidad de cada Ente de Aviación de Estado.\n\n(b) Cada EAE debe implementar un formato de medición de riesgo, que permita tomar oportunamente acciones de mitigación para los riesgos asociados al factor técnico, operacional y humano y que se aplicará antes del cumplimiento de cada misión.\n\n(c) Siempre que el Sistema cuente con la opción de descarga de la telemetría de vuelo, el EAE debe implementar un programa de supervisión de las operaciones, mediante la revisión periódica y aleatoria de los datos registrados, con el fin de identificar oportunamente desviaciones a los procedimientos estandarizados y cualquier debilidad que pueda identificarse oportunamente, en especial en lo relacionado con factores humanos.\n\n(d) Las telemetrías y/o datos de vuelo registrados automáticamente en la memoria de los UAS/RPAS, deben almacenarse para facilitar la supervisión operacional. Para los UAS/RPA, las telemetrías e imágenes/videos obtenidos de la carga útil, deben descargarse después de cada vuelo y/o almacenarse cronológicamente por un período mínimo de un (01) año.",
      "94.710": "(k) Cada EAE deberá contar con un Plan de Respuesta a Emergencias (ERP) diseñado específicamente para la gestión de contingencias relacionadas con el uso de Sistemas de Aeronaves No Tripuladas (UAS/RPAS). Este plan debe contemplar al menos los siguientes cinco aspectos fundamentales:\n\n(1) Se deben establecer procedimientos claros para actuar ante la pérdida parcial o total del control o del enlace de comunicaciones con el UAS/RPAS con el fin de reducir los riesgos asociados.\n\n(2) El plan debe establecer procedimientos en caso de fallo en sistemas críticos cuya falla comprometa la seguridad y prever protocolos para ejecutar aterrizajes de forma segura y controlada.\n\n(3) Deben contemplarse acciones ante eventos como la intrusión no autorizada de UAS/RPAS en espacios aéreos restringidos o controlados. El ERP debe incluir medidas de coordinación con autoridades civiles y militares para la respuesta oportuna y eficaz ante este tipo de incidentes.\n\n(4) El plan debe establecer procedimientos para la detección, identificación y neutralización segura de UAS/RPAS que representen una amenaza en zonas protegidas o de alto valor estratégico.\n\n(5) El plan debe establecer un procedimiento de contingencia para aterrizaje con armamento fallido o caliente.\n\n(6) Cada Ente de Aviación de Estado deberá garantizar la revisión de su Plan de Respuesta a Emergencias (PRE) con una periodicidad mínima anual, así como la ejecución de ejercicios de validación, ya sea mediante simulacros de mesa o ejercicios funcionales, al menos una vez por año. Adicionalmente, deberá realizar simulacros integrales o completos cada dos (2) años, con el fin de verificar la efectividad del plan.",
      "94.715": "(a) Los EAE cumplirán con lo establecido en el numeral 91.695 del RACAE 91 Reglas de vuelo y operación y sus Enmiendas, para garantizar la operación segura de los UAS/RPAS, además de los tiempos contemplados en la Tabla 1-5, Tiempos de vuelo autorizados para tripulaciones de UAS/RPAS.\n\n(2) Normas generales para el descanso: tiempo máximo de disponibilidad y comisión, descanso por tiempo de disponibilidad o comisión operativa y mecanismos de control de la fatiga. El Tiempo máximo de vuelo diario para la tripulación remota y exposición a las pantallas, para Operadores y Pilotos Remotos, se específica en la tabla 1-5 Tiempos de vuelo autorizados para tripulaciones de UAS/RPAS.",
    };
    const expectedRestPolicyExcerpt = "(b) Cada EAE publicará un documento donde se reglamente el tiempo de descanso de las tripulaciones de UAS/RPAS, de acuerdo con su clasificación, y en el cual se contemple:\n\n(1) Definiciones y conceptos: asignación y programación de vuelo, comisión del servicio, disponibilidad de vuelo, período de descanso, tiempo de descanso estándar, tiempo de operatividad, tiempo de servicio para vuelo, tripulación (mínima, aumentada, entre otros).\n\n(3) Restricciones: limitaciones generales para la designación de tripulaciones, extensión del tiempo máximo de servicio o de vuelo, excepciones al cumplimiento de las políticas de descanso, entre otras.\n\n(4) Procedimientos: Proceso de evaluación, consideraciones especiales, autoridades, niveles de mando y mecanismos de control para las excepciones.";
    const expectedLocators: Record<string, Array<[number, string | undefined]>> = {
      "fac.racae94.autonomous-flight.prohibited": [[38, "(a)"], [38, "(b)"]],
      "fac.racae94.one-pilot-one-uas": [[39, "(a)"]],
      "fac.racae94.swarm-reserved": [[42, undefined]],
      "fac.racae94.risk-telemetry-retention": [[66, "(a)"], [66, "(b)"], [66, "(c)"], [66, "(d)"]],
      "fac.racae94.emergency-response-plan": [[68, "(k)"], [69, "(k)(1)"], [69, "(k)(2)"], [69, "(k)(3)"], [69, "(k)(4)"], [69, "(k)(5)"], [69, "(k)(6)"]],
      "fac.racae94.rest-policy-document": [[69, "(b)"], [69, "(b)(1)"], [69, "(b)(3)"], [69, "(b)(4)"]],
      "fac.racae94.fatigue-screen-exposure": [[69, "(a)"], [69, "(b)(2)"]],
    };
    for (const requirement of artifact.requirements) {
      const first = requirement.sourceRefs[0];
      expect(first.extractionSha256).toBe(extractionSha);
      expect(first.quoteLanguage).toBe("es");
      expect(first.locator.section).toMatch(/^94\.\d{3}$/);
      expect(first.locator.page).toBe(expected.get(first.locator.section!));
      expect(requirement.sourceRefs.map((reference) => [reference.locator.page, reference.locator.paragraph])).toEqual(expectedLocators[requirement.predicate]);
      expect(requirement.sourceRefs.every((reference) => reference.extractionSha256 === extractionSha)).toBe(true);
      const expectedExcerpt = requirement.predicate === "fac.racae94.rest-policy-document"
        ? expectedRestPolicyExcerpt
        : expectedExcerptBySection[first.locator.section!];
      expect(requirement.sourceTextSpanish).toBe(expectedExcerpt);
      expect(requirement.interpretationStatus).not.toBe("approved");
      const regenerated = normalizeRequirement({
        sourceRefs: requirement.sourceRefs,
        Spanish: requirement.Spanish,
        EnglishControlled: requirement.EnglishControlled,
        applicabilityExpression: requirement.applicabilityExpression,
        severity: requirement.severity,
        evidenceRequired: requirement.evidenceRequired,
        effectiveFromUtc: requirement.effectiveFromUtc,
        interpretationStatus: requirement.interpretationStatus,
        reviewerIds: requirement.reviewerIds,
        predicate: requirement.predicate,
        sourceLanguageReview: requirement.sourceLanguageReview,
        applicabilityReview: requirement.applicabilityReview,
        ...(requirement.unresolvedRationale === undefined ? {} : { unresolvedRationale: requirement.unresolvedRationale }),
      });
      expect(regenerated.requirementId).toBe(requirement.requirementId);
    }
    expect(artifact.requirements.find((item) => item.predicate === "fac.racae94.rest-policy-document")?.Spanish).toContain("publicar");
    expect(artifact.requirements.find((item) => item.predicate === "fac.racae94.autonomous-flight.prohibited")?.Spanish).toContain("aspersión aérea de cultivos");
    expect(artifact.requirements.find((item) => item.sourceRefs[0].locator.section === "94.250")?.unresolvedRationale).toContain("Reserved");
    expect(artifact.requirements.find((item) => item.predicate === "fac.racae94.emergency-response-plan")?.requirementId).toBe("req-1e538e91a9efe63d824b");
  });

  it("keeps RACAE 219 explicitly blocked and free of invented controls", async () => {
    const artifact = JSON.parse(await readFile(resolve(root, "docs/regulations/normalized/racae219-sms.json"), "utf8")) as { artifactStatus: string; requirements: unknown[]; claims: unknown[]; reason: string };
    expect(artifact.artifactStatus).toBe("blocked");
    expect(artifact.requirements).toEqual([]);
    expect(artifact.claims).toEqual([]);
    expect(artifact.reason).toContain("not available");
  });

  it("validates citations against the immutable register without requiring production review promotion", () => {
    const requirement = normalizeRequirement(input());
    expect(() => validateRequirementCitations([requirement], register())).not.toThrow();
  });

  it("validates checked-in qualified-review citations against the checked-in in-review register", async () => {
    const artifact = JSON.parse(await readFile(resolve(root, "docs/regulations/normalized/racae94-amendment-2.json"), "utf8")) as { requirements: ReviewedNormalizedRequirement[] };
    const sourceRegister = SourceRegister.fromJsonl(await readFile(resolve(root, "docs/source-register/sources.jsonl"), "utf8"));
    expect(() => validateRequirementCitations(artifact.requirements, sourceRegister)).not.toThrow();
    const tampered = normalizeRequirement(input({ sourceRefs: [{ ...input().sourceRefs[0], extractionSha256: "b".repeat(64) }] }));
    expect(() => validateRequirementCitations([tampered], sourceRegister)).toThrow("extraction hash does not match");
  });

  it("rejects malformed locators and mismatched extraction hashes", () => {
    expect(() => normalizeRequirement(input({ sourceRefs: [{ ...input().sourceRefs[0], locator: { section: "94.15", page: 0 } }] }))).toThrow("malformed section locator");
    const requirement = normalizeRequirement(input());
    expect(() => validateRequirementCitations([requirement], register(source({ extractionSha256: "a".repeat(64) })))).toThrow("extraction hash does not match");
  });

  it("requires deterministic current signed provenance before a hard rule can be approved", () => {
    const accepted = { status: "accepted", reviewerRole: "qualified authority", reviewerId: "qualified-reviewer", reviewedAtUtc: "2026-08-08T18:00:00Z", rationale: "Accepted." } as const;
    const requirement = normalizeRequirement(input({ interpretationStatus: "approved", sourceLanguageReview: accepted, applicabilityReview: accepted }));
    const asOfUtc = "2026-08-09T00:00:00Z";
    expect(() => validateRequirementCitations([requirement], register(source({ review: "in-review" })), asOfUtc)).toThrow("current signed source evidence");
    expect(() => validateRequirementCitations([requirement], register(source()), asOfUtc)).not.toThrow();
    expect(() => validateRequirementCitations([requirement], register(source()))).toThrow("asOfUtc");
    expect(() => validateRequirementCitations([requirement], register(source()), "2026-02-30T00:00:00Z")).toThrow("asOfUtc");
    expect(() => validateRequirementCitations([requirement], register(source({ reviewSignature: undefined })), asOfUtc)).toThrow("current signed source evidence");
    expect(() => validateRequirementCitations([requirement], register(source({ validFromUtc: undefined })), asOfUtc)).toThrow("current signed source evidence");
    expect(() => validateRequirementCitations([requirement], register(source({ validUntilUtc: "2026-08-08T00:00:00Z" })), asOfUtc)).toThrow("current signed source evidence");
    expect(() => validateRequirementCitations([requirement], register(source({ supersededBy: "racae-94-replacement" as never })), asOfUtc)).toThrow("current signed source evidence");
    const reviewsWithoutTimestamps = normalizeRequirement(input({ interpretationStatus: "approved", sourceLanguageReview: { ...accepted, reviewedAtUtc: undefined }, applicabilityReview: accepted }));
    expect(() => validateRequirementCitations([reviewsWithoutTimestamps], register(source()), asOfUtc)).toThrow("accepted timestamped review");
  });

  it("rejects English-only authority and preserves IDs/predicates across locale changes", () => {
    const english = normalizeRequirement(input({ sourceRefs: [{ ...input().sourceRefs[0], sourceId: "english-source" as never, quoteLanguage: "en" }] }));
    expect(() => validateRequirementCitations([english], register(source({ sourceId: "english-source" as never, language: "en" })))).toThrow("Spanish-language authority");
    const first = normalizeRequirement(input());
    const priorLocale = process.env.LANG;
    process.env.LANG = "en_US.UTF-8";
    const second = normalizeRequirement(input());
    process.env.LANG = priorLocale;
    expect(second.requirementId).toBe(first.requirementId);
    expect(second.predicate).toBe(first.predicate);
  });

  it("builds only Spanish-evidence-backed controlled translations", () => {
    const evidence = { requirementId: "req-test", sourceRef: input().sourceRefs[0], sourceLanguageReview: input().sourceLanguageReview };
    expect(buildControlledTranslation("Texto fuente", "Source text", evidence)).toMatchObject({ sourceLanguage: "es", targetLanguage: "en", translationStatus: "draft" });
    expect(() => buildControlledTranslation("Texto", "Text", { ...evidence, sourceRef: { ...evidence.sourceRef, quoteLanguage: "en" } })).toThrow("Spanish source evidence");
  });
});
