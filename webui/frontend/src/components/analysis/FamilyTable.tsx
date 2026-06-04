import { fmtP } from "@/lib/format";
import type { AnalysisArtifact } from "@/types";

const TEST_LABEL: Record<string, string> = {
  Q1_omnibus: "Q1 level omnibus",
  Q2_visit_slope: "Q2 visit slope",
};

export function FamilyTable({ confirmatory }: { confirmatory: AnalysisArtifact["confirmatory"] }) {
  return (
    <div className="rounded-lg border border-border">
      <div className="border-b border-border px-4 py-2 text-sm text-muted-foreground">
        Confirmatory family — BH-FDR at q = {confirmatory.fdr_q} over{" "}
        {confirmatory.family_size_actual}/{confirmatory.family_size_planned} planned tests
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-muted-foreground">
            <th className="px-4 py-2">Metric</th>
            <th className="px-4 py-2">Test</th>
            <th className="px-4 py-2">p</th>
            <th className="px-4 py-2">p (FDR)</th>
            <th className="px-4 py-2">Survives</th>
          </tr>
        </thead>
        <tbody>
          {confirmatory.tests.map((t) => (
            <tr key={`${t.metric}-${t.test}`} className="border-t border-border/50">
              <td className="px-4 py-2 font-mono text-xs">{t.metric}</td>
              <td className="px-4 py-2">{TEST_LABEL[t.test] ?? t.test}</td>
              <td className="px-4 py-2">{fmtP(t.p)}</td>
              <td className="px-4 py-2">{fmtP(t.p_fdr)}</td>
              <td className="px-4 py-2">
                {t.reject == null ? "—" : t.reject ? "✓" : "✗"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
