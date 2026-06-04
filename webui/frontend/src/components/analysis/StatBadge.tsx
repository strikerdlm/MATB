import { cn } from "@/lib/utils";
import type { AnalysisStatus } from "@/types";

const STYLES: Record<AnalysisStatus, string> = {
  ok: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  insufficient_data: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  not_estimable: "bg-red-500/15 text-red-400 border-red-500/30",
};
const LABELS: Record<AnalysisStatus, string> = {
  ok: "ok",
  insufficient_data: "insufficient data",
  not_estimable: "not estimable",
};

export function StatBadge({ status, detail }: { status: AnalysisStatus; detail?: string }) {
  return (
    <span
      title={detail}
      className={cn("inline-block rounded-full border px-2 py-0.5 text-xs font-medium", STYLES[status])}
    >
      {LABELS[status]}
    </span>
  );
}
