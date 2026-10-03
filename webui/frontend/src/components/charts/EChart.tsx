"use client";

import dynamic from "next/dynamic";
import { useMemo, useRef } from "react";
import type { ComponentType, ReactNode } from "react";
import { Download, FileImage, FileJson } from "lucide-react";

import {
  LEVEL_COLORS,
  VALUE_AXIS_STYLE,
  preflightScientificOption,
  sanitizeExportName,
  summarizePreflight,
  type ScientificOption,
  withScientificDefaults,
} from "@/lib/figures";
import { cn } from "@/lib/utils";
import { useAppLocale } from "@/lib/i18n";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false }) as ComponentType<any>;

export { LEVEL_COLORS };
export const AXIS_STYLE = VALUE_AXIS_STYLE;

interface ChartHandle {
  getEchartsInstance?: () => {
    getDataURL: (opts: Record<string, unknown>) => string;
  };
}

export interface ScientificChartProps {
  option: ScientificOption;
  height?: number;
  figureId?: string;
  exportName?: string;
  caption?: string;
  className?: string;
  showExports?: boolean;
}

function downloadHref(href: string, filename: string) {
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
}

function downloadText(text: string, filename: string, type: string) {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  downloadHref(url, filename);
  URL.revokeObjectURL(url);
}

function ExportButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-slate-300 bg-white text-slate-700 shadow-sm transition hover:border-slate-500 hover:text-slate-950"
    >
      {children}
    </button>
  );
}

export function ScientificChart({
  option,
  height = 380,
  figureId,
  exportName,
  caption,
  className,
  showExports = true,
}: ScientificChartProps) {
  const { copy } = useAppLocale();
  const chartRef = useRef<ChartHandle | null>(null);
  const mergedOption = useMemo(() => withScientificDefaults(option), [option]);
  const preflight = useMemo(() => preflightScientificOption(mergedOption), [mergedOption]);
  const preflightSummary = summarizePreflight(preflight);
  const filenameBase = sanitizeExportName(exportName ?? figureId ?? "matb-figure") || "matb-figure";

  function exportDataUrl(type: "svg" | "png") {
    const instance = chartRef.current?.getEchartsInstance?.();
    if (!instance) return;
    const href = instance.getDataURL({
      type,
      pixelRatio: type === "png" ? 3 : 1,
      backgroundColor: "#ffffff",
      excludeComponents: ["toolbox"],
    });
    downloadHref(href, `${filenameBase}.${type}`);
  }

  function exportJson() {
    downloadText(
      JSON.stringify(mergedOption, null, 2),
      `${filenameBase}.json`,
      "application/json;charset=utf-8",
    );
  }

  return (
    <figure className={cn("rounded-md border border-slate-300 bg-white p-3 shadow-sm", className)}>
      {showExports && (
        <div className="mb-2 flex items-center justify-between gap-3">
          <div className="min-w-0">
            {figureId && (
              <p className="truncate font-serif text-xs font-semibold uppercase tracking-[0.16em] text-slate-700">
                {figureId}
              </p>
            )}
            <p
              className={cn(
                "text-xs",
                preflight.some((issue) => issue.level === "fail") ? "text-red-700" : "text-slate-500",
              )}
              title={preflight.map((issue) => issue.message).join("\n")}
            >
              {preflightSummary}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <ExportButton label={copy("Descargar SVG", "Download SVG")} onClick={() => exportDataUrl("svg")}>
              <Download className="h-4 w-4" />
            </ExportButton>
            <ExportButton label={copy("Descargar PNG", "Download PNG")} onClick={() => exportDataUrl("png")}>
              <FileImage className="h-4 w-4" />
            </ExportButton>
            <ExportButton label={copy("Descargar JSON de ECharts", "Download ECharts JSON")} onClick={exportJson}>
              <FileJson className="h-4 w-4" />
            </ExportButton>
          </div>
        </div>
      )}
      <ReactECharts
        ref={chartRef}
        option={mergedOption}
        notMerge
        lazyUpdate
        opts={{ renderer: "svg", height }}
        style={{ height, width: "100%" }}
      />
      {caption && (
        <figcaption className="mt-2 border-t border-slate-200 pt-2 font-serif text-xs leading-5 text-slate-600">
          {caption}
        </figcaption>
      )}
    </figure>
  );
}

export function EChart({ option, height = 360 }: { option: ScientificOption; height?: number }) {
  return <ScientificChart option={option} height={height} showExports={false} />;
}
