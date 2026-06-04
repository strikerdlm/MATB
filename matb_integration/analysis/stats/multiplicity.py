"""BH-FDR (confirmatory family) and Holm (within-metric contrasts) wrappers."""
from __future__ import annotations

from statsmodels.stats.multitest import multipletests


def bh_fdr(pvals: list[float], q: float = 0.05) -> tuple[list[float], list[bool]]:
    if not pvals:
        return [], []
    reject, p_adj, _, _ = multipletests(pvals, alpha=q, method="fdr_bh")
    return [float(p) for p in p_adj], [bool(r) for r in reject]


def holm(pvals: list[float], alpha: float = 0.05) -> tuple[list[float], list[bool]]:
    if not pvals:
        return [], []
    reject, p_adj, _, _ = multipletests(pvals, alpha=alpha, method="holm")
    return [float(p) for p in p_adj], [bool(r) for r in reject]
