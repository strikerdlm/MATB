import type { RequestOptions } from "node:https";

export function buildInstalledRequestOptions(mode: "live" | "ready", environment?: NodeJS.ProcessEnv): Promise<RequestOptions>;
