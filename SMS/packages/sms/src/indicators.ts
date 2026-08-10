import type { SpiStatus } from "./types.js";

export interface SpiValue { readonly value?: number; readonly unit: string; readonly dataQuality?: "complete" | "incomplete" | "stale" }
export interface SpiThreshold { readonly alertAt: number; readonly actionAt: number }

export function evaluateSpi(value: SpiValue, threshold: SpiThreshold): SpiStatus {
  if (!Number.isFinite(threshold.alertAt) || !Number.isFinite(threshold.actionAt) || threshold.actionAt < threshold.alertAt) throw new TypeError("SPI thresholds are invalid");
  if (!Number.isFinite(value.value) || value.dataQuality === "incomplete") return { level: "unknown", reason: "SPI data is incomplete", dataQuality: "incomplete" };
  if (value.dataQuality === "stale") return { level: "unknown", reason: "SPI data is stale", dataQuality: "stale" };
  const numeric = value.value!;
  if (numeric >= threshold.actionAt) return { level: "action", reason: `${numeric} ${value.unit} meets action threshold`, dataQuality: "complete" };
  if (numeric >= threshold.alertAt) return { level: "alert", reason: `${numeric} ${value.unit} meets alert threshold`, dataQuality: "complete" };
  return { level: "normal", reason: `${numeric} ${value.unit} is below alert threshold`, dataQuality: "complete" };
}
