// Numeric formatting for statistical output (manuscript-style).

export function fmtP(p: number | null | undefined): string {
  if (p == null) return "—";
  if (p < 0.001) return "<0.001";
  return p.toFixed(3);
}

export function fmtNum(x: number | null | undefined): string {
  if (x == null) return "—";
  return x.toFixed(3);
}

export function fmtCi(ci: [number, number] | null | undefined): string {
  if (!ci) return "—";
  return `[${ci[0].toFixed(3)}, ${ci[1].toFixed(3)}]`;
}
