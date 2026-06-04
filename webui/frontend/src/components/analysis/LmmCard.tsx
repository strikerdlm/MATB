import { StatBadge } from "@/components/analysis/StatBadge";
import { fmtCi, fmtNum, fmtP } from "@/lib/format";
import type { CoefRow, LmmResult } from "@/types";

function CoefTable({ rows, showHolm }: { rows: CoefRow[]; showHolm?: boolean }) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-muted-foreground">
          <th className="py-1 pr-2">Term</th>
          <th className="py-1 pr-2">b</th>
          <th className="py-1 pr-2">95% CI</th>
          <th className="py-1 pr-2">std</th>
          <th className="py-1 pr-2">p</th>
          {showHolm && <th className="py-1">p (Holm)</th>}
        </tr>
      </thead>
      <tbody>
        {rows.map((c) => (
          <tr key={c.name} className="border-t border-border/40">
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
  return (
    <div className="space-y-3 rounded-lg border border-border p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">
          {title}
          {result.exploratory && (
            <span className="ml-2 text-xs text-muted-foreground">(exploratory)</span>
          )}
        </h3>
        <StatBadge status={result.status} detail={result.detail} />
      </div>
      {result.status === "ok" && (
        <>
          {result.omnibus && (
            <p className="text-xs text-muted-foreground">
              Omnibus {result.omnibus.test}: χ²({result.omnibus.df}) ={" "}
              {fmtNum(result.omnibus.statistic)}, p = {fmtP(result.omnibus.p)} · n ={" "}
              {result.n_obs} obs / {result.n_participants} participants
            </p>
          )}
          {result.coefs && <CoefTable rows={result.coefs} />}
          {result.interactions && result.interactions.length > 0 && (
            <details className="text-xs text-muted-foreground">
              <summary>Interactions (secondary)</summary>
              <CoefTable rows={result.interactions} />
            </details>
          )}
          {result.contrasts && (
            <div>
              <p className="mb-1 text-xs text-muted-foreground">
                Pairwise contrasts (Holm within metric; shown because the omnibus survived FDR)
              </p>
              <CoefTable rows={result.contrasts} showHolm />
            </div>
          )}
        </>
      )}
    </div>
  );
}
