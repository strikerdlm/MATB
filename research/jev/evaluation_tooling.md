# Offline evaluation tooling, version 1.0.0

No command in this document sends material to JEV. Institution-controlled local
JSONL files are inputs; keep participant material and identifiers out of Git.

```text
python -m matb_integration.inference baseline notes.jsonl --output lexical.json
python -m matb_integration.inference benchmark coded.jsonl --bootstrap 1000 --seed 19 --output results.json
```

The baseline input contains `case_id`, `language` (`en`/`es`) and `excerpt`.
It is a frozen, deliberately simple lexical comparator, not a validated coder.
Recognized negation/uncertainty causes abstention on the two presence questions.
The implementation and output baseline version must be frozen before evaluation.
Baseline output contains no fabricated confidence values.

Each benchmark JSONL row has exactly these fields:

```json
{"case_id":"synthetic-1","cluster_id":"synthetic-person-1","language":"en","split":"test","question_id":"reported_task_tradeoff","reference":"present","rater_a":"present","rater_b":"present","method":"manual","prediction":"present","probabilities":null,"annotation_seconds":12.5,"correction_seconds":null,"corrected":false,"blinded":true}
```

- `cluster_id` is the participant grouping key, not the window/session ID when
  several sessions belong to one participant. Use local pseudonyms. Cluster
  membership cannot cross development/test partitions. Report participant counts.
- `reference`, `rater_a`, and `rater_b` use the frozen `label_schema.json` codes.
  Reference labels must come from blinded independent coding/adjudication as
  specified in the protocol; a boolean cannot verify study conduct.
- Supply one row per case/question/method. Manual, lexical and JEV-assisted
  methods must contain identical cases, reference labels and partitions within
  each language/question arm. The tool rejects duplicates and unpaired cases.
- Development rows check partition isolation but do not enter reported estimates.
- Noul comparisons use explicit textual `present` versus `not_explicit`.
  `explicit_absence` and `unmentioned` both map to `not_explicit` for this binary
  endpoint, but their original counts and rater-agreement labels remain distinct.
  This does not mean the reported event did not occur. For a stored noul answer
  `p`, provide probabilities `{"present":p,"not_explicit":1-p}`. A prespecified
  0.5 decision rule may be used for the software pilot; archive any subsequent
  development-derived threshold separately. Never tune on held-out errors.
- Choice probabilities use all four automation-belief keys. A prediction must
  be a maximum-probability category (ties allowed). `insufficient_evidence` is an
  abstention, not an ordinal level. Unknown reference cases are counted but
  excluded from classification denominators.
- Probabilities are optional for manual/lexical methods. Calibration reports its
  available denominator. Do not fabricate probabilities from human labels.
- Times are seconds or null (missing). The Console's optional timer measures
  elapsed browser-monotonic time from explicit start to submission, includes idle
  time, and stores a separate `coding_timing` audit record linked to the review.
  A blinded-reference timer is annotation time; post-model adjudication is
  correction time. For `corrected`, compare recorded codes before/after under the
  study protocol; timing alone does not establish a correction. No timer survives
  a page reload or reviewer handoff. Untimed work remains missing, never zero.

Outputs contain confusion matrices, macro-F1, class recall, coverage/abstention,
reference counts, unweighted Cohen kappa, ten fixed confidence bins, multiclass
Brier sum (binary range 0–2), log loss (probabilities floored at 1e-15), and timing
and correction summaries. Macro-F1 includes classes with nonzero reference or
prediction count; zero-denominator class recall is null. Undefined kappa is null.

Percentile intervals resample whole participant clusters with replacement, using
the same draws for paired methods. Reports include intervals for F1, coverage,
Brier, log loss, kappa and available mean times, plus paired F1 differences.
Intervals are null with fewer than two clusters. Degenerate resamples are omitted
where an estimate is undefined. These software intervals do not establish adequate
sample size or study validity. Inputs are limited to 10,000 rows / 16 MB; bootstrap
replicates are explicitly bounded from 100 to 5,000.

The synthetic unit tests check arithmetic, missingness, pairing, negation,
language handling and partition rejection. They are not a human benchmark and
cannot support a keep/remove decision for JEV. No participant benchmark data or
invented empirical results are included in this repository.
