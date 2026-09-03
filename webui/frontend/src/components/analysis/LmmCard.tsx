"use client";

import { StatBadge } from "@/components/analysis/StatBadge";
import { fmtCi, fmtNum, fmtP } from "@/lib/format";
import type { CoefRow, LmmResult } from "@/types";
import { useAppLocale } from "@/lib/i18n";

function CoefTable({ rows, showHolm }: { rows: CoefRow[]; showHolm?: boolean }) {
  const { copy } = useAppLocale();
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
          <th className="py-1 pr-2">{copy("Término", "Term")}</th>
          <th className="py-1 pr-2">b</th>
          <th className="py-1 pr-2">IC 95%</th>
          <th className="py-1 pr-2">{copy("est.", "std")}</th>
          <th className="py-1 pr-2">p</th>
          {showHolm && <th className="py-1">p (Holm)</th>}
        </tr>
      </thead>
      <tbody>
        {rows.map((c) => (
          <tr key={c.name} className="border-t border-white/10">
            <td className="py-1 pr-2 font-mono text-xs">{c.name}</td>
            <td className="py-1 pr-2">{fmtNum(c.coef)}</td>
            <td className="py-1 pr-2">{fmtCi(c.ci95)}</td>
            <td className="py-1 pr-2">{fmtNum(c.std_effect)}</td>
            <td className="py-1 pr-2">{fmtP(c.p)}</td>
            {showHolm && <td className="py-1">{fmtP(c.p_holm)}</td>}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function LmmCard({ title, result }: { title: string; result: LmmResult }) {
  const { copy } = useAppLocale();
  return (
    <div className="mission-panel space-y-3 p-4">
      <div className="flex items-center justify-between">
        <h3 className="font-mono text-xs font-semibold uppercase tracking-[0.12em]">
          {title}
          {result.exploratory && (
            <span className="ml-2 text-[10px] text-muted-foreground">({copy("exploratorio", "exploratory")})</span>
          )}
        </h3>
        <StatBadge status={result.status} detail={result.detail} />
      </div>
      {result.status === "ok" && (
        <>
          {result.omnibus && (
            <p className="text-xs text-muted-foreground">
              {copy("Ómnibus", "Omnibus")} {result.omnibus.test}: χ²({result.omnibus.df}) ={" "}
              {fmtNum(result.omnibus.statistic)}, p = {fmtP(result.omnibus.p)} · n ={" "}
              {result.n_obs} obs / {result.n_participants} {copy("participantes", "participants")}
            </p>
          )}
          {result.coefs && <CoefTable rows={result.coefs} />}
          {result.interactions && result.interactions.length > 0 && (
            <details className="text-xs text-muted-foreground">
              <summary>{copy("Interacciones (secundarias)", "Interactions (secondary)")}</summary>
              <CoefTable rows={result.interactions} />
            </details>
          )}
          {result.contrasts && (
            <div>
              <p className="mb-1 text-xs text-muted-foreground">
                {copy("Contrastes por pares (Holm dentro de cada métrica; se muestran porque el ómnibus superó FDR)", "Pairwise contrasts (Holm within metric; shown because the omnibus survived FDR)")}
              </p>
              <CoefTable rows={result.contrasts} showHolm />
            </div>
          )}
        </>
      )}
    </div>
  );
}
