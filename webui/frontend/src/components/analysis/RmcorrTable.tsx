import { StatBadge } from "@/components/analysis/StatBadge";
import { fmtCi, fmtNum, fmtP } from "@/lib/format";
import type { AnalysisArtifact } from "@/types";

export function RmcorrTable({ q3 }: { q3: AnalysisArtifact["q3"] }) {
  return (
    <div className="rounded-lg border border-border">
      <div className="border-b border-border px-4 py-2 text-sm text-muted-foreground">
        Q3 — repeated-measures correlation (exploratory; canonical + level-adjusted sensitivity)
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-muted-foreground">
            <th className="px-4 py-2">x</th>
            <th className="px-4 py-2">y</th>
            <th className="px-4 py-2">r</th>
            <th className="px-4 py-2">df</th>
            <th className="px-4 py-2">95% CI</th>
            <th className="px-4 py-2">p</th>
            <th className="px-4 py-2">r (level-adj)</th>
            <th className="px-4 py-2">Status</th>
          </tr>
        </thead>
        <tbody>
          {q3.map((e) => (
            <tr key={`${e.x}-${e.y}`} className="border-t border-border/50">
              <td className="px-4 py-2 font-mono text-xs">{e.x}</td>
              <td className="px-4 py-2 font-mono text-xs">{e.y}</td>
              <td className="px-4 py-2">{fmtNum(e.canonical.r)}</td>
              <td className="px-4 py-2">{e.canonical.dof ?? "—"}</td>
              <td className="px-4 py-2">{fmtCi(e.canonical.ci95)}</td>
              <td className="px-4 py-2">{fmtP(e.canonical.p)}</td>
              <td className="px-4 py-2">{fmtNum(e.sensitivity?.r)}</td>
              <td className="px-4 py-2">
                <StatBadge status={e.canonical.status} detail={e.canonical.detail} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
