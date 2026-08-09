import {
  assertSignedPackageManifest,
  rejectDowngrade,
  verifyPackage,
} from "@fac-isr/evidence";
import type { VerificationReport } from "@fac-isr/evidence";
import { parseGeoPackageManifest } from "./types.js";
import type { GeoPackageManifest } from "./types.js";

export interface GeoPackageVerificationOptions {
  /** Explicit UTC time used for effective/expiry checks. */
  asOfUtc?: string;
  availableDependencies?: readonly GeoPackageManifest[];
}

export type GeoPackageVerificationInput = GeoPackageVerificationOptions | string;

const SUPPORTED_HORIZONTAL_DATUMS = new Set(["EPSG:4326", "EPSG:3116"]);
const EXACT_UTC = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?Z$/;

function packageId(value: unknown): string {
  return value !== null && typeof value === "object" && "packageId" in value && typeof value.packageId === "string"
    ? value.packageId
    : "unknown";
}

function invalidReport(value: unknown, reason: string): VerificationReport {
  return {
    ok: false,
    checks: [{ id: "manifest-shape", status: "fail", reason }],
    packageId: packageId(value),
  };
}

function isExactUtc(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const match = EXACT_UTC.exec(value);
  if (!match) return false;
  const [, year, month, day, hour, minute, second, fraction = ""] = match;
  const date = new Date(value);
  return Number.isFinite(date.getTime())
    && date.getUTCFullYear() === Number(year)
    && date.getUTCMonth() + 1 === Number(month)
    && date.getUTCDate() === Number(day)
    && date.getUTCHours() === Number(hour)
    && date.getUTCMinutes() === Number(minute)
    && date.getUTCSeconds() === Number(second)
    && date.getUTCMilliseconds() === Number(fraction.padEnd(3, "0") || 0);
}

function geoMetadataChecks(manifest: GeoPackageManifest): VerificationReport["checks"] {
  const failures: string[] = [];
  const warnings: string[] = [];
  if (!SUPPORTED_HORIZONTAL_DATUMS.has(manifest.horizontalDatum)) {
    failures.push(`unsupported package horizontal datum: ${manifest.horizontalDatum}`);
  }
  if (manifest.verticalDatum !== undefined && manifest.verticalDatum.trim() === "") {
    failures.push("package vertical datum must not be empty");
  }
  if (manifest.kind === "terrain" && manifest.verticalDatum === undefined) {
    failures.push("terrain packages require an explicit vertical datum");
  }
  if (manifest.qualification === "blocked") failures.push("package qualification is blocked");
  else if (manifest.qualification === "qualified-review") warnings.push("package qualification is qualified-review, not approved");

  for (const layer of manifest.layers) {
    if (!SUPPORTED_HORIZONTAL_DATUMS.has(layer.horizontalDatum)) {
      failures.push(`layer ${layer.id} uses unsupported horizontal datum: ${layer.horizontalDatum}`);
    }
    if (layer.verticalDatum !== undefined && layer.verticalDatum.trim() === "") {
      failures.push(`layer ${layer.id} vertical datum must not be empty`);
    }
    if (manifest.kind === "terrain" && layer.verticalDatum === undefined) {
      failures.push(`terrain layer ${layer.id} requires an explicit vertical datum`);
    }
    if (layer.authority.trim() === "") failures.push(`layer ${layer.id} authority is required`);
  }

  const checks: Array<VerificationReport["checks"][number]> = [{
    id: "geo-metadata",
    status: failures.length === 0 ? "pass" : "fail",
    ...(failures.length > 0 ? { reason: failures.join("; ") } : {}),
  }];
  if (warnings.length > 0) checks.push({ id: "qualification", status: "warn", reason: warnings.join("; ") });
  else checks.push({ id: "qualification", status: "pass" });
  return checks;
}

/**
 * Verify a signed geospatial package without any network access. The
 * as-of time is explicit or comes from the deterministic offline verifier
 * environment; it is never taken from the system clock.
 */
export async function verifyGeoPackage(
  directory: string,
  manifest: unknown,
  publicKey: string | Buffer,
  options: GeoPackageVerificationInput = {},
): Promise<VerificationReport> {
  let parsed: GeoPackageManifest;
  try {
    parsed = parseGeoPackageManifest(manifest);
  } catch (error) {
    return invalidReport(manifest, error instanceof Error ? error.message : String(error));
  }

  const metadataChecks = geoMetadataChecks(parsed);
  const normalizedOptions: GeoPackageVerificationOptions = typeof options === "string" ? { asOfUtc: options } : options;
  const asOfUtc = normalizedOptions.asOfUtc ?? process.env.SMS_EVIDENCE_VERIFY_AS_OF ?? "";
  const evidenceReport = await verifyPackage(
    directory,
    parsed,
    publicKey,
    asOfUtc,
    normalizedOptions.availableDependencies ?? [],
  );
  const checks = [...metadataChecks, ...evidenceReport.checks];
  return {
    ...evidenceReport,
    ok: evidenceReport.ok && !metadataChecks.some((check) => check.status === "fail"),
    checks,
  };
}

/** Refuse an expired, not-yet-effective, blocked, stale, or downgraded replacement. */
export function rejectStaleOrDowngradedPackage(
  installed: GeoPackageManifest,
  incoming: GeoPackageManifest,
  nowUtc: string,
): void {
  const current = parseGeoPackageManifest(installed);
  const candidate = parseGeoPackageManifest(incoming);
  if (!isExactUtc(nowUtc)) throw new Error("package comparison requires an exact UTC time");
  if (current.kind !== candidate.kind || current.format !== candidate.format) throw new Error("package replacement changes kind or format");
  if (candidate.qualification === "blocked") throw new Error("package replacement is blocked");
  if (!SUPPORTED_HORIZONTAL_DATUMS.has(candidate.horizontalDatum)) throw new Error("package replacement uses an unsupported horizontal datum");
  const metadataFailure = geoMetadataChecks(candidate).find((check) => check.status === "fail");
  if (metadataFailure !== undefined) throw new Error(`package replacement metadata is invalid: ${metadataFailure.reason ?? "failed"}`);
  const now = Date.parse(nowUtc);
  if (now < Date.parse(candidate.effectiveFromUtc)) throw new Error("package replacement is not yet effective");
  if (candidate.expiresAtUtc !== undefined && now >= Date.parse(candidate.expiresAtUtc)) throw new Error("package replacement is stale or expired");
  rejectDowngrade(current, candidate);
}

export { assertSignedPackageManifest };
