# HRV workload descriptors: scientific contract

## Provenance

The minimum calculation code is ported from `strikerdlm/HRV` commit
`ef086092cfc57c74171f9ac9374b8ba24ceb0e6a` under its MIT license. Release A
registers `polar-live-time-domain-v2` and `astra-hrv-metrics-1.0.0`. It uses the
published Lipponen–Tarvainen detector with a conservative rejection and
continuity-break policy named `lipponen-tarvainen-rejection-v1`.

Release A intentionally does **not** claim `hrv-class-aware-correction-v1`:
that identifier includes an audited duration-preserving structural edit engine
whose full dependency surface has not been ported. Raw finite positive RR values
remain unchanged. A rejected beat, notification gap, or reconnect epoch cannot
form a successive pair and cannot be bridged for spectral analysis.

The exact upstream paths and SHA-256 values are recorded in
[`source-provenance.json`](source-provenance.json).

## Equations and gates

For accepted NN intervals `NN_i` in milliseconds:

- mean instantaneous HR = `mean(60000 / NN_i)`;
- SDNN = sample standard deviation, denominator `n - 1`;
- RMSSD = `sqrt(mean((NN_(i+1) - NN_i)^2))` over valid contiguous pairs;
- lnRMSSD = natural logarithm of positive RMSSD;
- pNN50 = percentage of valid contiguous pairs with absolute difference
  strictly greater than 50 ms.

The live panel requires a 60-second window, at least 30 beats, and signal
quality of at least 0.8. It is descriptive; 60-second SDNN is ultra-short and
exploratory. Comparable offline results require standardized five-minute
baseline/task phases and return `null` plus a reason when duration, continuity,
contact, or quality support fails.

Absolute LF/HF power uses 4 Hz beat-time interpolation, linear detrending, a
Hann-window Welch density PSD, and stationarity gates (two-half mean shift
`z <= 0.5`, variance ratio `<= 2`). HF requires 60 s; LF and the LF/HF ratio
require 120 s. Release A only calculates a spectrum across a fully continuous,
artifact-free window. LF/HF is labelled a neutral mathematical ratio and never
sympathovagal balance.

## Workload-response output

The only derived task response is:

- `delta_ln_rmssd = lnRMSSD_task - lnRMSSD_baseline`;
- `delta_mean_hr_bpm = mean_HR_task - mean_HR_baseline`.

Artifact burden, usable coverage, and ACC movement context accompany these
descriptors. Block condition, NASA-TLX/ISA, and MATB performance remain separate
observed variables. No universal HRV workload equation, category, probability,
autonomic score, or operational threshold is implemented.

Primary HRV comes from HRS RR intervals. Raw ECG is retained, but ECG-derived R
peaks/RR remain experimental until a 130 Hz detector passes public-dataset and
simultaneous-reference qualification.

## References

- Lipponen JA, Tarvainen MP. A robust algorithm for heart rate variability time
  series artefact correction using novel beat classification. *J Med Eng
  Technol*. 2019. https://doi.org/10.1080/03091902.2019.1640306
- Billman GE. The LF/HF ratio does not accurately measure cardiac sympatho-vagal
  balance. *Front Physiol*. 2013. https://doi.org/10.3389/fphys.2013.00026
- Wang et al. Review of physiological workload measurement in aviation.
  *Sensors*. 2024. https://doi.org/10.3390/s24123723
- Quigley et al. Recommendations for physiological measurement and inference.
  *Psychophysiology*. 2024. https://doi.org/10.1111/psyp.14604
