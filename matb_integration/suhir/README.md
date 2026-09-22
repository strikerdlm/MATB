# suhir â€” DEPDF mission-outcome layer

Read-only analysis layer implementing Suhir (2018) *Human-in-the-Loop*
probabilistic mission-outcome model on OpenMATB `log_converter` output.

## What it computes
- `depdf.py` â€” basic DEPDF (Eq. 5.1), ordinary-capacity form (Eq. 5.16), Weibull degradation.
- `failure_events.py` â€” discrete per-task failures â†’ MTTF, failure rate.
- `mwl.py` â€” within-participant MWL normalization (G/G0 anchored to LOW block).
- `hcf.py` â€” HCF input contract (external test battery; F0 default).
- `calibration.py` â€” FOAT fit (Eq. 5.19â€“5.21) + Beta-update for P0.
- `mission.py` â€” mission failure Q (Eq. 5.10).
- `report.py` â€” training targets, selection ranking.
- `pipeline.py` / `cli.py` â€” end-to-end per-participant fit.

## Run
```bash
python3 -m matb_integration.suhir.cli fit \
  --participant P01 --low LOW.csv --medium MED.csv --high HIGH.csv \
  --source rtlx_mean_0_100 --out P01_suhir.json
```

## Validity (read before citing)
- Within-participant **comparative** model only (Suhir's framing); MWL ratios
  are anchored to each participant's LOW block.
- The default TLX input is the complete-form unweighted RTLX mean on a 0â€“100
  scale. `raw_tlx` remains selectable only to reproduce legacy v1 analyses; it
  is a non-standard sum and is not confirmatory-eligible.
- 3 MWL levels exactly-identify G0/P0/tau0 â†’ no goodness-of-fit df.
- TLX/ISA/Bedford are ordinal/interval; run the `--source` sensitivity sweep.
- Phase 1 runs F = F0 (Eq. 5.16); per-participant HCF requires the external
  test battery. Phase 2 adds the Ch. 9 physiological-symptom term.
- Research instrument â€” not a certified safety tool.

Spec: `docs/superpowers/specs/2026-06-03-suhir-depdf-mission-outcome-design.md`
