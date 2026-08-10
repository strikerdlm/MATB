export const CONSOLE_ROUTES = [
  "/missions",
  "/missions/:id/plan",
  "/missions/:id/review",
  "/missions/:id/monitor",
  "/missions/:id/debrief",
  "/sms",
  "/research",
] as const;

export type ConsoleRoute = (typeof CONSOLE_ROUTES)[number];

export function routeTitle(path: string): string {
  if (path.includes("/review")) return "Safety review";
  if (path.includes("/monitor")) return "Telemetry";
  if (path.includes("/debrief")) return "Post-flight debrief";
  if (path.includes("/plan")) return "Flight profile";
  if (path === "/sms") return "Safety management";
  if (path === "/research") return "Research instruments";
  return "Mission overview";
}
