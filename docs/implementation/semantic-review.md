# Experimental semantic review

This optional research component codes synthetic narrative excerpts after
reconciliation. It does not modify events, metrics, eligibility, purpose,
physiology, task snapshots or automation. Participant egress is currently blocked.

## Installation and activation

Use the normal backend installation, then optionally install
`webui/backend/requirements-inference.txt`. Its HTTPX pin matches the backend.
The core installation requires neither a provider key nor remote access.

```text
MATB_COMPONENTS=matb-semantic-review
MATB_ENABLE_SEMANTIC_REVIEW=1
MATB_JEV_MODE=off
MATB_JEV_PROVIDER=jev_ai_pro
MATB_JEV_MODEL=jev-1.13.0
```

`MATB_COMPONENTS=core` excludes the component. Auto discovery also requires the
explicit enable flag. `off` and `replay` never send. For separately authorized
synthetic provider testing, use `post_session_remote` and configure
`JEV_AI_API_KEY` in the server environment only. Unsupported provider/model
settings block requests; there is no fallback provider. Never put keys in browser
configuration, URLs, jobs, logs or exports.

## Researcher workflow

1. Finish recording and close the protected station visit and held runtime.
2. Open Scientific Evidence and choose an explicit reconciled run.
3. Enter a synthetic note, its original language and optional event IDs.
4. Queue the projection and refresh its status. Inspect the exact outbound text,
   local lineage and exclusions. Edit by creating a new annotation/preview.
5. Supply the named reviewer and synthetic protocol authorization, review the
   payload and authorize its exact bytes for one hour.
6. Queue one assessment. The existing station worker rechecks source integrity
   and current authorization after admission, then makes at most one attempt.
7. Submit independent reference labels before revealing answers. Subsequent
   model-assisted adjudication is recorded separately. Named exposure applies
   across replicated attempts of the same input, including exports.
8. Export the separate inference ZIP and verify it without networking:

```text
python -m matb_integration.inference verify inference.zip
```

The API supports explicit retries with fresh authorization; a retry creates a new
attempt and must obey all previous attempts' outstanding retry limits. An unknown
delivery outcome is never retried automatically. Cancelled/late results remain
separate from active assessments. Restart recovery does not alter evidence runs.

## Interpretation and access

Noul values concern textual statements, not physiological condition probability.
Choice distributions and model-reported confidence are displayed without
promoting them into facts. Low probability does not distinguish explicit absence
from unmentioned evidence. The frozen reference schema preserves that distinction.

Local narratives and inference artifacts reside in the Console database; existing
station export storage also applies to deferred downloads. Apply institutional
access, backup and retention controls to those locations. Named-rater auditing
does not authenticate identities or prevent off-platform exposure; independent
study access and assignment controls remain necessary. Pattern screening assists
review but cannot prove anonymity. Participant processing needs a separately
reviewed institutional arrangement and an explicit implementation change.

See the [implementation plan](../superpowers/plans/2026-09-19-matb-jev-semantic-review.md),
[annotation protocol](../../research/jev/annotation_protocol.md) and
[verification report](../reports/2026-09-19-jev-semantic-review.md).
