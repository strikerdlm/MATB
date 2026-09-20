# JEV v1 completion work

Baseline: merged PR #72, `782a7d3`. This follow-up completes the outstanding
software work from the 19 September specification. It does not authorize a live
provider call or participant egress.

1. Add bounded capture-scoped annotation/run history and review-history reads.
   Reading reference labels records exposure across attempts before disclosure.
2. Add append-only approval revocation and researcher retry controls. Serialize
   revocation with the dispatch check. Once sending begins, report that delivery
   may have occurred; never promise remote deletion or refund.
3. Extend bundles with the source annotation chain, exact stored approval bytes,
   and audit history, while retaining network-free verification of v1.0 bundles.
4. Complete the bilingual panel with saved-work retrieval, annotation versions,
   explicit observation intervals, distributions, diagnostic states and history.
5. Add a frozen conservative lexical comparator and a bounded offline evaluator:
   language arms, paired cases, participant partitions, confusion/F1/recall,
   calibration, agreement, coverage, timing and clustered uncertainty.
6. Exercise acceptance tests, core regression and browser accessibility; obtain
   independent review, resolve material findings and record observed evidence.

Decisions: participant egress remains hard blocked. Named reviewer auditing is
not identity authentication; institutional assignment/access controls remain
necessary. Benchmark input is institution-controlled local data, never Git.
Noul is evaluated as explicit textual presence versus not-explicit, preserving
unmentioned and explicit-absence counts in the report. It is not evaluated as a
four-class instrument that it cannot represent. No inference of fatigue or fitness.

Progress: history API test observed 405 before implementation; now passes through
annotation, projection, mock inference, hidden history, exposure, export/replay,
retry and pre-dispatch revocation. Frontend reopen test observed missing control
before implementation. Evaluator tests observed missing module before implementation.

Independent review: reviewer-handoff exposure and lexical negation gaps were
classified as material. Both were reproduced by failing tests and fixed. No
minor findings were deferred. Optional timing was added as a separate audit
record; the API initially rejected the new timing field before implementation.
