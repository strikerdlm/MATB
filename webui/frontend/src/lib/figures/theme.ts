import { LEVELS } from "@/lib/tracker";

export type WorkloadLevel = (typeof LEVELS)[number];
export type ScientificOption = Record<string, unknown>;

export const FIGURE_FONT =
  "Charter, 'Iowan Old Style', 'Palatino Linotype', Georgia, serif";

export const FIGURE_COLORS = {
  paper: "#ffffff",
  ink: "#202124",
  mutedInk: "#5f6368",
  grid: "#d9dde2",
  faintGrid: "#eceff2",
  reference: "#6b7280",
  ci: "#38414a",
};

// Okabe-Ito / Wong-compatible accents.
export const LEVEL_COLORS: Record<WorkloadLevel, string> = {
  LOW: "#0072B2",
  MEDIUM: "#E69F00",
  HIGH: "#D55E00",
};

export const LEVEL_SYMBOLS: Record<WorkloadLevel, string> = {
  LOW: "circle",
  MEDIUM: "diamond",
  HIGH: "triangle",
};

export const ANALYSIS_COLORS = {
  q1: "#0072B2",
  q2: "#009E73",
  q3: "#CC79A7",
  q4: "#D55E00",
  bayes: "#5D3A9B",
  neutral: "#38414a",
  sensitivity: "#7f8c8d",
};

export const VALUE_AXIS_STYLE = {
  nameLocation: "middle",
  nameGap: 42,
  nameTextStyle: { color: FIGURE_COLORS.ink, fontSize: 12, fontWeight: 600 },
  axisLine: { lineStyle: { color: "#9aa3ad", width: 1 } },
  axisTick: { lineStyle: { color: "#9aa3ad" } },
  axisLabel: { color: FIGURE_COLORS.ink, fontSize: 11 },
  splitLine: {
    show: true,
    lineStyle: { color: FIGURE_COLORS.faintGrid, type: "dashed", width: 1 },
  },
};

export const CATEGORY_AXIS_STYLE = {
  axisLine: { lineStyle: { color: "#9aa3ad", width: 1 } },
  axisTick: { lineStyle: { color: "#9aa3ad" } },
  axisLabel: { color: FIGURE_COLORS.ink, fontSize: 11 },
  splitLine: { show: false },
};

export function scientificBaseOption(): ScientificOption {
  return {
    backgroundColor: FIGURE_COLORS.paper,
    useUTC: true,
    animation: false,
    aria: { enabled: true, decal: { show: true } },
    color: [
      LEVEL_COLORS.LOW,
      LEVEL_COLORS.MEDIUM,
      LEVEL_COLORS.HIGH,
      ANALYSIS_COLORS.q2,
      ANALYSIS_COLORS.q3,
      ANALYSIS_COLORS.bayes,
    ],
    textStyle: {
      color: FIGURE_COLORS.ink,
      fontFamily: FIGURE_FONT,
      fontSize: 12,
    },
    tooltip: {
      trigger: "axis",
      confine: true,
      backgroundColor: "rgba(255, 255, 255, 0.96)",
      borderColor: "#d7dbe0",
      borderWidth: 1,
      textStyle: { color: FIGURE_COLORS.ink, fontSize: 12 },
    },
    legend: {
      type: "scroll",
      top: 8,
      right: 16,
      itemWidth: 20,
      itemHeight: 10,
      textStyle: { color: FIGURE_COLORS.ink, fontSize: 11 },
    },
    grid: {
      left: 84,
      right: 34,
      top: 56,
      bottom: 70,
      containLabel: true,
    },
  };
}

function mergeAxis(base: unknown, axis: unknown): unknown {
  if (!axis) return base;
  if (Array.isArray(axis)) return axis.map((item) => ({ ...(base as object), ...(item as object) }));
  return { ...(base as object), ...(axis as object) };
}

export function withScientificDefaults(option: ScientificOption): ScientificOption {
  const base = scientificBaseOption();
  return {
    ...base,
    ...option,
    grid: option.grid ?? base.grid,
    xAxis: mergeAxis(VALUE_AXIS_STYLE, option.xAxis),
    yAxis: mergeAxis(VALUE_AXIS_STYLE, option.yAxis),
  };
}

export function sanitizeExportName(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 96);
}
