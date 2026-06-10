import { LEVELS } from "@/lib/tracker";
import { METRICS, type GroupStats, type Trajectory } from "@/lib/viz";
import type {
  AnalysisArtifact,
  BayesArtifact,
  BayesModelResult,
  CoefRow,
  FitRow,
  LmmResult,
  RmcorrResult,
} from "@/types";
import {
  ANALYSIS_COLORS,
  CATEGORY_AXIS_STYLE,
  FIGURE_COLORS,
  LEVEL_COLORS,
  LEVEL_SYMBOLS,
  VALUE_AXIS_STYLE,
  type ScientificOption,
  withScientificDefaults,
} from "@/lib/figures/theme";

export interface IntervalRow {
  label: string;
  estimate: number;
  low: number;
  high: number;
  group?: string;
}

const Q_LABELS: Record<"q1" | "q2" | "q4", string> = {
  q1: "Q1",
  q2: "Q2",
  q4: "Q4",
};

const GROUP_COLORS: Record<string, string> = {
  Q1: ANALYSIS_COLORS.q1,
  Q2: ANALYSIS_COLORS.q2,
  Q3: ANALYSIS_COLORS.q3,
  Q4: ANALYSIS_COLORS.q4,
  Bayesian: ANALYSIS_COLORS.bayes,
  Canonical: ANALYSIS_COLORS.q3,
  "Level-adjusted": ANALYSIS_COLORS.sensitivity,
  Estimate: ANALYSIS_COLORS.neutral,
};

function metricLabel(metric: string): string {
  return METRICS[metric]?.label ?? metric;
}

function axisLabel(metric: string): string {
  const meta = METRICS[metric];
  if (!meta) return metric;
  return meta.unit ? `${meta.label} (${meta.unit})` : meta.label;
}

function round(value: number): number {
  return Number(value.toFixed(6));
}

export function ci95(mean: number | null, sd: number | null, n: number): [number, number] | null {
  if (mean == null || sd == null || n < 2) return null;
  const halfWidth = 1.96 * (sd / Math.sqrt(n));
  return [round(mean - halfWidth), round(mean + halfWidth)];
}

function finiteInterval(row: IntervalRow): boolean {
  return Number.isFinite(row.estimate) && Number.isFinite(row.low) && Number.isFinite(row.high);
}

function intervalSegments(rows: IntervalRow[]): [number | null, string][] {
  return rows.flatMap((row) => [
    [row.low, row.label] as [number, string],
    [row.high, row.label] as [number, string],
    [null, row.label] as [null, string],
  ]);
}

function uniqueGroups(rows: IntervalRow[]): string[] {
  const groups = rows.map((row) => row.group ?? "Estimate");
  return Array.from(new Set(groups));
}

function colorForGroup(group: string, index: number): string {
  return GROUP_COLORS[group] ?? [
    ANALYSIS_COLORS.neutral,
    ANALYSIS_COLORS.q1,
    ANALYSIS_COLORS.q2,
    ANALYSIS_COLORS.q3,
    ANALYSIS_COLORS.q4,
    ANALYSIS_COLORS.bayes,
  ][index % 6];
}

export function buildIntervalForestOption(
  rows: IntervalRow[],
  xLabel: string,
  opts: { min?: number; max?: number; reference?: number; heightRows?: boolean } = {},
): ScientificOption {
  const cleanRows = rows.filter(finiteInterval).reverse();
  const categories = cleanRows.map((row) => row.label);
  const groups = uniqueGroups(cleanRows);
  const series = groups.flatMap((group, index) => {
    const groupRows = cleanRows.filter((row) => (row.group ?? "Estimate") === group);
    const color = colorForGroup(group, index);
    return [
      {
        name: `${group} 95% interval`,
        type: "line",
        coordinateSystem: "cartesian2d",
        data: intervalSegments(groupRows),
        symbol: "none",
        lineStyle: { color, width: 1.8 },
        emphasis: { disabled: true },
        tooltip: { show: false },
        silent: true,
      },
      {
        name: group,
        type: "scatter",
        data: groupRows.map((row) => [row.estimate, row.label]),
        symbol: "circle",
        symbolSize: 8,
        itemStyle: { color, borderColor: "#ffffff", borderWidth: 1.5 },
        markLine: opts.reference == null ? undefined : {
          silent: true,
          symbol: "none",
          lineStyle: { color: FIGURE_COLORS.reference, type: "dashed", width: 1 },
          data: [{ xAxis: opts.reference }],
          label: { show: false },
        },
      },
    ];
  });

  return withScientificDefaults({
    grid: {
      left: 142,
      right: 36,
      top: groups.length > 1 ? 58 : 34,
      bottom: 68,
      containLabel: true,
    },
    legend: { show: groups.length > 1, top: 8, right: 16, data: groups },
    tooltip: { trigger: "item", confine: true },
    xAxis: {
      type: "value",
      name: xLabel,
      min: opts.min,
      max: opts.max,
      ...VALUE_AXIS_STYLE,
    },
    yAxis: {
      type: "category",
      name: "Model term",
      nameGap: 104,
      data: categories,
      ...CATEGORY_AXIS_STYLE,
      axisLabel: {
        color: FIGURE_COLORS.ink,
        fontSize: 10,
        width: 132,
        overflow: "truncate",
      },
    },
    series,
  });
}

function cleanCoefRows(rows: CoefRow[] | undefined, names?: string[]): CoefRow[] {
  const source = rows ?? [];
  return source.filter((coef) => {
    if (!coef.ci95) return false;
    if (names) return names.includes(coef.name);
    return coef.name !== "Intercept" && coef.name !== "const";
  });
}

function termLabel(term: string): string {
  const labels: Record<string, string> = {
    "MEDIUM-LOW": "Medium - low",
    "HIGH-LOW": "High - low",
    "HIGH-MEDIUM": "High - medium",
    visit_c: "Visit slope",
    b_visit: "Visit slope",
    b_med: "Medium - low",
    b_high: "High - low",
    b0: "Intercept",
    sigma_u: "Participant SD",
    sigma_e: "Residual SD",
  };
  return labels[term] ?? term.replaceAll("_", " ");
}

export function lmmIntervalRows(
  results: Record<string, LmmResult>,
  question: "q1" | "q2" | "q4",
): IntervalRow[] {
  const rows: IntervalRow[] = [];
  for (const [metricOrParam, result] of Object.entries(results)) {
    if (result.status !== "ok") continue;
    const q1Source = result.contrasts && result.contrasts.length > 0 ? result.contrasts : result.coefs;
    const coefs = question === "q1"
      ? cleanCoefRows(q1Source, ["MEDIUM-LOW", "HIGH-LOW", "HIGH-MEDIUM"])
      : cleanCoefRows(result.coefs, ["visit_c"]);
    for (const coef of coefs) {
      rows.push({
        label: `${metricLabel(metricOrParam)}: ${termLabel(coef.name)}`,
        estimate: coef.coef,
        low: coef.ci95[0],
        high: coef.ci95[1],
        group: Q_LABELS[question],
      });
    }
  }
  return rows;
}

export function buildLmmForestOption(
  results: Record<string, LmmResult>,
  question: "q1" | "q2" | "q4",
): ScientificOption {
  return buildIntervalForestOption(
    lmmIntervalRows(results, question),
    "Fixed effect estimate (95% CI)",
    { reference: 0 },
  );
}

function rmcorrRows(q3: AnalysisArtifact["q3"]): IntervalRow[] {
  const rows: IntervalRow[] = [];
  for (const item of q3) {
    const baseLabel = `${metricLabel(item.x)} x ${metricLabel(item.y)}`;
    rows.push(...rmcorrResultRows(item.canonical, `${baseLabel}: canonical`, "Canonical"));
    if (item.sensitivity) {
      rows.push(...rmcorrResultRows(item.sensitivity, `${baseLabel}: level-adjusted`, "Level-adjusted"));
    }
  }
  return rows;
}

function rmcorrResultRows(result: RmcorrResult, label: string, group: string): IntervalRow[] {
  if (result.status !== "ok" || result.r == null || !result.ci95) return [];
  return [{ label, estimate: result.r, low: result.ci95[0], high: result.ci95[1], group }];
}

export function buildRmcorrForestOption(q3: AnalysisArtifact["q3"]): ScientificOption {
  return buildIntervalForestOption(
    rmcorrRows(q3),
    "Repeated-measures correlation r (95% CI)",
    { min: -1, max: 1, reference: 0 },
  );
}

function bayesRows(section: Record<string, BayesModelResult>, mode: "q2" | "q4"): IntervalRow[] {
  const preferred = mode === "q2" ? ["b_visit", "b_med", "b_high"] : ["b_visit"];
  const rows: IntervalRow[] = [];
  for (const [metricOrParam, result] of Object.entries(section)) {
    if (result.status !== "ok" || !result.coefs) continue;
    for (const name of preferred) {
      const coef = result.coefs[name];
      if (!coef) continue;
      rows.push({
        label: `${metricLabel(metricOrParam)}: ${termLabel(name)}`,
        estimate: coef.mean,
        low: coef.eti95[0],
        high: coef.eti95[1],
        group: "Bayesian",
      });
    }
  }
  return rows;
}

export function buildBayesForestOption(artifact: BayesArtifact, mode: "q2" | "q4"): ScientificOption {
  return buildIntervalForestOption(
    bayesRows(mode === "q2" ? artifact.q2 : artifact.q4, mode),
    "Posterior mean (95% ETI)",
    { reference: 0 },
  );
}

export function buildTrajectoryOption(
  data: Trajectory,
  metric: string,
  kind: "line" | "bar" = "line",
): ScientificOption {
  const series = LEVELS.map((level) => ({
    name: level,
    type: kind,
    data: data.series[level],
    connectNulls: false,
    color: LEVEL_COLORS[level],
    symbol: LEVEL_SYMBOLS[level],
    symbolSize: 7,
    barMaxWidth: kind === "bar" ? 18 : undefined,
    lineStyle: kind === "line" ? { width: 2 } : undefined,
    emphasis: { focus: "series" },
  }));
  return withScientificDefaults({
    legend: { top: 8, right: 16, data: [...LEVELS] },
    xAxis: {
      type: "category",
      name: "Visit",
      nameLocation: "middle",
      nameGap: 34,
      data: data.visits.map((visit) => `V${visit}`),
      ...CATEGORY_AXIS_STYLE,
    },
    yAxis: {
      type: "value",
      name: axisLabel(metric),
      scale: true,
      ...VALUE_AXIS_STYLE,
    },
    series,
  });
}

export function buildGroupTrajectoryOption(data: GroupStats, metric: string): ScientificOption {
  const series = LEVELS.flatMap((level) => {
    const { mean, sd, n } = data.stats[level];
    const lower = mean.map((m, i) => ci95(m, sd[i], n[i])?.[0] ?? null);
    const band = mean.map((m, i) => {
      const ci = ci95(m, sd[i], n[i]);
      return ci ? round(ci[1] - ci[0]) : null;
    });
    return [
      {
        name: `${level} lower CI`,
        type: "line",
        stack: `ci-${level}`,
        data: lower,
        lineStyle: { opacity: 0 },
        symbol: "none",
        tooltip: { show: false },
        silent: true,
      },
      {
        name: `${level} 95% CI`,
        type: "line",
        stack: `ci-${level}`,
        data: band,
        lineStyle: { opacity: 0 },
        symbol: "none",
        areaStyle: { color: LEVEL_COLORS[level], opacity: 0.16 },
        tooltip: { show: false },
        silent: true,
      },
      {
        name: level,
        type: "line",
        data: mean,
        connectNulls: false,
        color: LEVEL_COLORS[level],
        symbol: LEVEL_SYMBOLS[level],
        symbolSize: 7,
        lineStyle: { width: 2 },
      },
    ];
  });

  return withScientificDefaults({
    legend: { top: 8, right: 16, data: [...LEVELS] },
    xAxis: {
      type: "category",
      name: "Visit",
      nameLocation: "middle",
      nameGap: 34,
      data: data.visits.map((visit) => `V${visit}`),
      ...CATEGORY_AXIS_STYLE,
    },
    yAxis: {
      type: "value",
      name: `${axisLabel(metric)}; cohort mean (95% CI)`,
      scale: true,
      ...VALUE_AXIS_STYLE,
    },
    series,
  });
}

export function buildDepdfCurveOption(fits: FitRow[]): ScientificOption {
  const sorted = [...fits].sort((a, b) => a.visit_ordinal - b.visit_ordinal);
  return withScientificDefaults({
    legend: { top: 8, right: 16 },
    xAxis: {
      type: "value",
      name: "G / G0",
      min: 1,
      max: 3,
      ...VALUE_AXIS_STYLE,
    },
    yAxis: {
      type: "value",
      name: "Human nonfailure probability",
      min: 0,
      max: 1,
      ...VALUE_AXIS_STYLE,
    },
    series: sorted.map((fit, index) => ({
      name: `Visit ${fit.visit_ordinal}`,
      type: "line",
      showSymbol: false,
      data: fit.curve.map((point) => [point.r, point.p]),
      color: [
        "#0072B2",
        "#009E73",
        "#E69F00",
        "#CC79A7",
        "#56B4E9",
        "#D55E00",
      ][index % 6],
      lineStyle: { width: 2 },
    })),
  });
}

export function buildDepdfParamOption(
  fits: FitRow[],
  param: "g0" | "p0" | "tau0",
  label: string,
): ScientificOption {
  const sorted = [...fits].sort((a, b) => a.visit_ordinal - b.visit_ordinal);
  return withScientificDefaults({
    legend: { show: false },
    grid: { left: 72, right: 24, top: 24, bottom: 56, containLabel: true },
    xAxis: {
      type: "category",
      name: "Visit",
      nameLocation: "middle",
      nameGap: 32,
      data: sorted.map((fit) => `V${fit.visit_ordinal}`),
      ...CATEGORY_AXIS_STYLE,
    },
    yAxis: {
      type: "value",
      name: label,
      min: param === "p0" ? 0 : undefined,
      max: param === "p0" ? 1 : undefined,
      scale: param !== "p0",
      ...VALUE_AXIS_STYLE,
    },
    series: [{
      name: label,
      type: "line",
      data: sorted.map((fit) => fit[param]),
      color: ANALYSIS_COLORS.q4,
      symbol: "circle",
      symbolSize: 7,
      lineStyle: { width: 2 },
    }],
  });
}
