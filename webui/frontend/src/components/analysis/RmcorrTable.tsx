"use client";

import { StatBadge } from "@/components/analysis/StatBadge";
import { fmtCi, fmtNum, fmtP } from "@/lib/format";
import type { AnalysisArtifact } from "@/types";
import { useAppLocale } from "@/lib/i18n";

export function RmcorrTable({ q3 }: { q3: AnalysisArtifact["q3"] }) {
  const { copy } = useAppLocale();
  return (
    <div className="data-table-wrap overflow-x-auto">
      <div className="border-b border-white/10 px-4 py-3 font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
        Q3 - {copy("correlación de medidas repetidas (exploratoria; canónica + sensibilidad ajustada por nivel)", "repeated-measures correlation (exploratory; canonical + level-adjusted sensitivity)")}
      </div>
      <table className="data-table">
        <thead>
          <tr>
            <th className="px-4 py-2">x</th>
            <th className="px-4 py-2">y</th>
            <th className="px-4 py-2">r</th>
            <th className="px-4 py-2">df</th>
            <th className="px-4 py-2">IC 95%</th>
            <th className="px-4 py-2">p</th>
            <th className="px-4 py-2">r ({copy("ajustada por nivel", "level-adj")})</th>
            <th className="px-4 py-2">{copy("Estado", "Status")}</th>
          </tr>
        </thead>
        <tbody>
          {q3.map((e) => (
            <tr key={`${e.x}-${e.y}`}>
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
