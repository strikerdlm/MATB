"use client";
import { useSearchParams } from "next/navigation";
import type { ExecutionPurpose } from "@/lib/experiments";

type SearchParamsReader = Pick<URLSearchParams, "get">;

export function isExecutionPurpose(value: unknown): value is ExecutionPurpose {
  return value === "practice" || value === "study";
}

/**
 * Resolve preparation purpose from an explicit URL choice. A fast verification
 * is always practice even if a conflicting purpose was supplied.
 */
export function resolveExecutionPurpose(query: SearchParamsReader): ExecutionPurpose | null {
  if (query.get("fast") === "1") return "practice";
  const selected = query.get("purpose");
  return isExecutionPurpose(selected) ? selected : null;
}

/** Existing sessions use their persisted purpose; block names are never inputs. */
export function resolveSessionExecutionPurpose(storedSessionPurpose: unknown): ExecutionPurpose | null {
  return isExecutionPurpose(storedSessionPurpose) ? storedSessionPurpose : null;
}

export function useExecutionPurpose(): ExecutionPurpose | null {
  return resolveExecutionPurpose(useSearchParams());
}

export function withExecutionPurpose(href: string, purpose: ExecutionPurpose): string {
  const base = new URL(href, "http://matb.local");
  base.searchParams.delete("fast");
  base.searchParams.set("purpose", purpose);
  return `${base.pathname}${base.search}${base.hash}`;
}
