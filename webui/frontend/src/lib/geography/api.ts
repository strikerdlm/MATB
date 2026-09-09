import { getApiBase } from "@/lib/runtime-config";
import type { SceneManifest } from "@/lib/simulation/presentation/contracts";
import type {
  PreparationJob,
  Region,
  TrafficFrame,
  TrafficRecording,
} from "./types";
export interface GeographyCatalog {
  regions: Region[];
  scenes: SceneManifest[];
  providers: { id: string; available: boolean }[];
  reference: { acquired_at: string } | null;
}
export async function geographyRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${await getApiBase()}/geography${path}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : (body.detail?.message ??
          `Geography request failed (${response.status})`),
    );
  }
  return response.json() as Promise<T>;
}
export const geographyCatalog = () =>
  geographyRequest<GeographyCatalog>("/catalog");
export const trafficRecordings = () =>
  geographyRequest<TrafficRecording[]>("/recordings");
export const areaTraffic = (
  lat: number,
  lon: number,
  radius: number,
  provider: string,
  signal?: AbortSignal,
) =>
  geographyRequest<TrafficFrame>(
    `/traffic?lat=${lat}&lon=${lon}&radius_nm=${radius}&provider=${encodeURIComponent(provider)}`,
    { signal },
  );
export const prepareArea = (area: {
  lat: number;
  lon: number;
  title: string;
  region: string;
}) =>
  geographyRequest<PreparationJob>("/preparations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      lat: area.lat,
      lon: area.lon,
      title: area.title,
      region: area.region,
    }),
  });
