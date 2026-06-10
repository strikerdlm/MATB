import type { ScientificOption } from "@/lib/figures/theme";

export interface FigurePreflightIssue {
  level: "fail" | "warn";
  message: string;
}

type PlainObject = Record<string, unknown>;

function isObject(value: unknown): value is PlainObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asArray(value: unknown): unknown[] {
  if (value == null) return [];
  return Array.isArray(value) ? value : [value];
}

function hasTruthyPath(value: unknown, path: string[]): boolean {
  let cur = value;
  for (const part of path) {
    if (!isObject(cur) || !(part in cur)) return false;
    cur = cur[part];
  }
  return cur === true;
}

function checkAxis(axis: unknown, axisName: string, issues: FigurePreflightIssue[]) {
  for (const item of asArray(axis)) {
    if (!isObject(item)) {
      issues.push({ level: "fail", message: `${axisName} is missing` });
      continue;
    }
    if (!item.name || typeof item.name !== "string") {
      issues.push({ level: "fail", message: `${axisName} needs a label with units where applicable` });
    }
    const nameGap = item.nameGap;
    if (typeof nameGap !== "number" || nameGap < 24) {
      issues.push({ level: "warn", message: `${axisName} nameGap should leave print-safe label spacing` });
    }
  }
}

export function preflightScientificOption(option: ScientificOption): FigurePreflightIssue[] {
  const issues: FigurePreflightIssue[] = [];

  if (option.animation !== false) {
    issues.push({ level: "fail", message: "animation must be false for reproducible figures" });
  }
  if (!hasTruthyPath(option.aria, ["enabled"])) {
    issues.push({ level: "fail", message: "aria.enabled must be true" });
  }
  if (!hasTruthyPath(option.aria, ["decal", "show"])) {
    issues.push({ level: "warn", message: "aria.decal.show should be true for colorblind-safe redundancy" });
  }
  if ("title" in option) {
    issues.push({ level: "fail", message: "scientific figures should not include an ECharts title block" });
  }
  if (option.backgroundColor !== "#ffffff" && option.backgroundColor !== "white") {
    issues.push({ level: "warn", message: "export background should be white" });
  }

  const grids = asArray(option.grid);
  if (grids.length === 0) {
    issues.push({ level: "fail", message: "grid is missing" });
  }
  for (const grid of grids) {
    if (!isObject(grid) || grid.containLabel !== true) {
      issues.push({ level: "fail", message: "grid.containLabel must be true" });
    }
  }

  checkAxis(option.xAxis, "xAxis", issues);
  checkAxis(option.yAxis, "yAxis", issues);
  return issues;
}

export function summarizePreflight(issues: FigurePreflightIssue[]): string {
  const fails = issues.filter((issue) => issue.level === "fail").length;
  const warns = issues.filter((issue) => issue.level === "warn").length;
  if (!fails && !warns) return "Q1 preflight passed";
  if (fails) return `${fails} fail${fails === 1 ? "" : "s"}, ${warns} warning${warns === 1 ? "" : "s"}`;
  return `${warns} warning${warns === 1 ? "" : "s"}`;
}
