# suhir — DEPDF mission-outcome layer

Read-only analysis layer implementing Suhir (2018) *Human-in-the-Loop*
probabilistic mission-outcome model on OpenMATB `log_converter` output.

## What it computes
- `depdf.py` — basic DEPDF (Eq. 5.1), ordinary-capacity form (Eq. 5.16), Weibull degradation.
- `failure_events.py` — discrete per-task failures → MTTF, failure rate.
- `mwl.py` — within-participant MWL normalization (G/G0 anchored to LOW block).
- `hcf.py` — HCF input contract (external neurocognitive screen; F0 default).
- `calibration.py` — FOAT fit (Eq. 5.19–5.21) + Beta-update for P0.
- `mission.py` — mission failure Q (Eq. 5.10).
- `report.py` — training targets, selection ranking.
- `pipeline.py` / `cli.py` — end-to-end per-participant fit.

## Run
```bash
python3 -m matb_integration.suhir.cli fit \
  --participant P01 --low LOW.csv --medium MED.csv --high HIGH.csv \
  --source raw_tlx --out P01_suhir.json
```

## Validity (read before citing)
- Within-participant **comparative** model only (Suhir's framing); MWL ratios
  are anchored to each participant's LOW block.
- 3 MWL levels exactly-identify G0/P0/tau0 → no goodness-of-fit df.
- TLX/ISA/Bedford are ordinal/interval; run the `--source` sensitivity sweep.
- Phase 1 runs F = F0 (Eq. 5.16); per-participant HCF requires the external
  neurocognitive screen. Phase 2 adds the Ch. 9 physiological-symptom term.
- Research instrument — not a certified safety tool.

Spec: `docs/superpowers/specs/2026-06-03-suhir-depdf-mission-outcome-design.md`
