import type { ConsoleCapabilities } from "@/types";

export interface ProductRoute {
  componentId: "matb-liftoff" | "matb-suas" | "matb-openmatb" | "matb-physiology";
  href: string;
  label: string;
}

const OPTIONAL_ROUTES: readonly ProductRoute[] = [
  { componentId: "matb-openmatb", href: "/openmatb/setup", label: "OpenMATB" },
  { componentId: "matb-physiology", href: "/physiology/polar-h10", label: "Polar H10" },
  { componentId: "matb-liftoff", href: "/liftoff/setup", label: "Liftoff" },
  { componentId: "matb-suas", href: "/mission/setup", label: "Mission" },
];

export function activeComponentIds(capabilities: Pick<ConsoleCapabilities, "components">): string[] {
  return Array.from(new Set(capabilities.components.map((component) => component.component_id))).sort();
}

export function hasComponent(
  capabilities: Pick<ConsoleCapabilities, "components">,
  componentId: string,
): boolean {
  return capabilities.components.some((component) => component.component_id === componentId);
}

export function productRoutes(capabilities: Pick<ConsoleCapabilities, "components">): ProductRoute[] {
  const active = new Set(activeComponentIds(capabilities));
  return OPTIONAL_ROUTES.filter((route) => active.has(route.componentId));
}
