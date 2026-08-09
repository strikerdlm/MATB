import { z } from "zod";
import type { AircraftClass } from "@fac-isr/safety-kernel";

export type Kilograms = number & { readonly __unit: "kg" };
export type Configuration = "unarmed-isr" | "unarmed-support" | "armed" | "strike";
const id = z.string().trim().min(1);
const utc = z.string().regex(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?Z$/).refine((v) => { const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?Z$/.exec(v); if (!m) return false; const d = new Date(v); return Number.isFinite(d.getTime()) && d.getUTCFullYear() === +m[1] && d.getUTCMonth() + 1 === +m[2] && d.getUTCDate() === +m[3] && d.getUTCHours() === +m[4] && d.getUTCMinutes() === +m[5] && d.getUTCSeconds() === +m[6]; });
const finiteNonnegative = z.number().finite().nonnegative();
const raw = z.record(z.union([z.string(), z.number().finite(), z.boolean()]));

export interface UASSystem { id: string; manufacturer: string; model: string; aircraftClass: AircraftClass; mtowKg: Kilograms; configuration: Configuration; approvedConfigurationId: string; rawManufacturerValues?: Record<string, string | number | boolean> }
export interface CapabilityClaim { id: string; subjectId: string; capability: "vfr" | "ifr" | "vlos" | "evlos" | "bvlos" | "daa" | "c2" | "gnss-integrity" | "payload"; value: string | number | boolean; units?: string; operatingConditions: Record<string, string | number | boolean>; evidenceRefs: string[]; confidence: "verified" | "qualified" | "vendor-claimed" | "research-only"; validFromUtc: string; validToUtc?: string }
export interface Discrepancy { id: string; description: string; severity: "minor" | "major" | "critical"; disposition: "open" | "approved-deferred" | "resolved"; evidenceRefs: readonly string[] }
export interface MaintenanceRelease { aircraftId: string; configurationHash: string; inspectionDueAtUtc: string; openDiscrepancies: readonly Discrepancy[]; minimumEquipmentSatisfied: boolean; batteryRelease: "released" | "restricted" | "quarantined"; payloadRelease: "released" | "restricted" | "removed"; softwareBaseline: string; authorizedBy: string; decision: "released" | "blocked"; signedAtUtc: string }

const UASSchema = z.object({ id, manufacturer: id, model: id, aircraftClass: z.enum(["IA", "IB", "IC", "II", "III"]), mtowKg: finiteNonnegative.positive().transform((v) => v as Kilograms), configuration: z.enum(["unarmed-isr", "unarmed-support", "armed", "strike"]), approvedConfigurationId: id, rawManufacturerValues: raw.optional() }).strict();
const ClaimSchema = z.object({ id, subjectId: id, capability: z.enum(["vfr", "ifr", "vlos", "evlos", "bvlos", "daa", "c2", "gnss-integrity", "payload"]), value: z.union([z.string(), z.number().finite(), z.boolean()]), units: z.string().trim().min(1).optional(), operatingConditions: raw, evidenceRefs: z.array(id), confidence: z.enum(["verified", "qualified", "vendor-claimed", "research-only"]), validFromUtc: utc, validToUtc: utc.optional() }).strict().superRefine((value, ctx) => { if ((value.confidence === "verified" || value.confidence === "qualified") && value.evidenceRefs.length === 0) ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["evidenceRefs"], message: "evidence is required for verified or qualified claims" }); if (value.validToUtc && Date.parse(value.validToUtc) <= Date.parse(value.validFromUtc)) ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["validToUtc"], message: "validity end must be after start" }); });
const DiscrepancySchema = z.object({ id, description: id, severity: z.enum(["minor", "major", "critical"]), disposition: z.enum(["open", "approved-deferred", "resolved"]), evidenceRefs: z.array(id).min(1, "evidence is required") }).strict();
const MaintenanceSchema = z.object({ aircraftId: id, configurationHash: id, inspectionDueAtUtc: utc, openDiscrepancies: z.array(DiscrepancySchema), minimumEquipmentSatisfied: z.boolean(), batteryRelease: z.enum(["released", "restricted", "quarantined"]), payloadRelease: z.enum(["released", "restricted", "removed"]), softwareBaseline: id, authorizedBy: id, decision: z.enum(["released", "blocked"]), signedAtUtc: utc }).strict();
export function parseUASSystem(value: unknown): UASSystem { return UASSchema.parse(value); }
export function parseCapability(value: unknown): CapabilityClaim { return ClaimSchema.parse(value); }
export function parseDiscrepancy(value: unknown): Discrepancy { return DiscrepancySchema.parse(value); }
export function parseMaintenanceRelease(value: unknown): MaintenanceRelease { return MaintenanceSchema.parse(value); }
