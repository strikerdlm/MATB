import type { InstrumentDefinition, InstrumentResponse } from "./types.js";

export type ControlledInstrumentName = Exclude<InstrumentDefinition["name"], "custom">;

interface NumericRange { readonly min: number; readonly max: number }

const CONTROLLED_RANGES: Readonly<Record<ControlledInstrumentName, Readonly<Record<string, NumericRange>>>> = {
  SAGAT: {
    response: { min: 0, max: 100 },
    responseAccuracy: { min: 0, max: 100 },
    accuracy: { min: 0, max: 100 },
    correct: { min: 0, max: 1 },
  },
  "NASA-TLX": {
    mentalDemand: { min: 0, max: 100 },
    physicalDemand: { min: 0, max: 100 },
    temporalDemand: { min: 0, max: 100 },
    performance: { min: 0, max: 100 },
    effort: { min: 0, max: 100 },
    frustration: { min: 0, max: 100 },
    workload: { min: 0, max: 100 },
    overallWorkload: { min: 0, max: 100 },
  },
  ISA: {
    level: { min: 1, max: 5 },
    isa: { min: 1, max: 5 },
    overall: { min: 1, max: 5 },
  },
  Bedford: {
    rating: { min: 1, max: 7 },
    bedford: { min: 1, max: 7 },
    workload: { min: 1, max: 7 },
  },
  SART: {
    situationAwareness: { min: 0, max: 9 },
    understanding: { min: 0, max: 9 },
    demand: { min: 0, max: 9 },
    supply: { min: 0, max: 9 },
    score: { min: 0, max: 9 },
    rating: { min: 0, max: 9 },
  },
};

const definitions = new Map<string, InstrumentDefinition>();
const ranges = new Map<string, Readonly<Record<string, NumericRange>>>();

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function requiredText(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "") throw new TypeError(`${field} is required`);
  return value.trim();
}

function utc(value: unknown, field: string): string {
  const text = requiredText(value, field);
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(text) || !Number.isFinite(Date.parse(text))) {
    throw new TypeError(`${field} must be UTC`);
  }
  return text;
}

function strictKeys(value: Record<string, unknown>, allowed: readonly string[]): void {
  const unknown = Object.keys(value).find((key) => !allowed.includes(key));
  if (unknown !== undefined) throw new TypeError(`research separation boundary rejects field: ${unknown}`);
}

function freeze<T>(value: T): T {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const child of Object.values(value as Record<string, unknown>)) freeze(child);
  }
  return value;
}

function makeDefinition(name: ControlledInstrumentName): InstrumentDefinition {
  const fieldRanges = CONTROLLED_RANGES[name];
  const responseSchema = {
    fields: Object.keys(fieldRanges),
    ranges: fieldRanges,
    missingAllowed: true,
    administration: "single-session-research-response",
  };
  const definition: InstrumentDefinition = {
    id: name,
    name,
    version: "1.0.0",
    responseSchema,
    status: "approved-template",
  };
  return freeze(definition);
}

for (const name of Object.keys(CONTROLLED_RANGES) as ControlledInstrumentName[]) {
  definitions.set(name, makeDefinition(name));
  ranges.set(name, CONTROLLED_RANGES[name]);
}

export function getInstrument(name: string): InstrumentDefinition {
  const instrument = definitions.get(requiredText(name, "instrument"));
  if (instrument === undefined) throw new RangeError(`unknown research instrument: ${name}`);
  return instrument;
}

function parseCustomRanges(responseSchema: Record<string, unknown>): Readonly<Record<string, NumericRange>> {
  const rangeInput = responseSchema.ranges;
  if (!isRecord(rangeInput)) throw new TypeError("responseSchema.ranges is required");
  const parsed: Record<string, NumericRange> = {};
  for (const [field, range] of Object.entries(rangeInput)) {
    if (!isRecord(range) || typeof range.min !== "number" || typeof range.max !== "number" || !Number.isFinite(range.min) || !Number.isFinite(range.max) || range.min > range.max) {
      throw new TypeError(`responseSchema range is invalid for ${field}`);
    }
    parsed[requiredText(field, "responseSchema field")] = { min: range.min, max: range.max };
  }
  if (Object.keys(parsed).length === 0) throw new TypeError("responseSchema.ranges is required");
  return freeze(parsed);
}

export function registerCustomInstrument(input: unknown): InstrumentDefinition {
  if (!isRecord(input)) throw new TypeError("instrument must be an object");
  strictKeys(input, ["id", "name", "version", "responseSchema", "status"]);
  const id = requiredText(input.id, "id");
  if (definitions.has(id)) throw new TypeError(`instrument already exists: ${id}`);
  if (input.name !== "custom") throw new TypeError("custom instrument name is required");
  const version = requiredText(input.version, "version");
  if (!isRecord(input.responseSchema)) throw new TypeError("responseSchema is required");
  const fieldRanges = parseCustomRanges(input.responseSchema);
  const status = input.status === undefined ? "protocol-specific" : input.status as "protocol-specific" | "approved-template";
  if (status !== "protocol-specific" && status !== "approved-template") throw new TypeError("custom instrument status is invalid");
  const definition = freeze({
    id,
    name: "custom" as const,
    version,
    responseSchema: { ...input.responseSchema, ranges: fieldRanges, fields: Object.keys(fieldRanges) },
    status,
  });
  definitions.set(id, definition);
  ranges.set(id, fieldRanges);
  return definition;
}

/** Alias kept for callers that treat all instrument definitions as registrable. */
export const registerInstrument = registerCustomInstrument;

export function recordInstrumentResponse(input: unknown): InstrumentResponse {
  if (!isRecord(input)) throw new TypeError("instrument response must be an object");
  strictKeys(input, ["sessionId", "instrumentId", "administeredAtUtc", "values", "missingReason", "instrumentVersion"]);
  const sessionId = requiredText(input.sessionId, "sessionId");
  const instrumentId = requiredText(input.instrumentId, "instrumentId");
  const definition = definitions.get(instrumentId);
  if (definition === undefined) throw new RangeError(`unknown research instrument: ${instrumentId}`);
  const instrumentVersion = input.instrumentVersion === undefined ? undefined : requiredText(input.instrumentVersion, "instrumentVersion");
  if (instrumentVersion !== undefined && instrumentVersion !== definition.version) throw new TypeError("instrument version is not approved");
  const administeredAtUtc = utc(input.administeredAtUtc, "administeredAtUtc");
  if (!isRecord(input.values)) throw new TypeError("values must be an object");
  const valueEntries = Object.entries(input.values);
  const missingReason = input.missingReason === undefined ? undefined : requiredText(input.missingReason, "missingReason");
  if (valueEntries.length === 0 && missingReason === undefined) throw new TypeError("missingReason is required when no responses are recorded");
  const fieldRanges = ranges.get(instrumentId) ?? {};
  const values: Record<string, number | string | null> = {};
  let hasMissingValue = false;
  for (const [field, value] of valueEntries) {
    const range = fieldRanges[field];
    if (range === undefined) throw new TypeError(`instrument field is not approved: ${field}`);
    if (value === null) {
      hasMissingValue = true;
      values[field] = null;
      continue;
    }
    if (typeof value === "number") {
      if (!Number.isFinite(value) || value < range.min || value > range.max) throw new RangeError(`${field} is outside the approved range`);
      values[field] = value;
      continue;
    }
    if (typeof value !== "string" || value.trim() === "") throw new TypeError(`${field} must be numeric, text, or null`);
    values[field] = value;
  }
  if (hasMissingValue && missingReason === undefined) throw new TypeError("missingReason is required for missing responses");
  return freeze({
    sessionId,
    instrumentId,
    administeredAtUtc,
    values,
    ...(missingReason === undefined ? {} : { missingReason }),
    ...(instrumentVersion === undefined ? {} : { instrumentVersion }),
  });
}
