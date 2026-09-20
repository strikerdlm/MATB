# Experimental semantic annotation protocol v1

Status: protocol scaffold; no participant validation performed.

Freeze the Git revision of `matb-debrief-v1.json` and `label_schema.json` before
test labeling. Two independent raters label original-language excerpts without
model answers or the other rater's labels. Retain each original label; a third
adjudicator resolves disagreements using a prespecified written rule. Post-model
adjudication is a different activity and never independent reference data.

Code explicit reports only. Explicit absence and unmentioned evidence are
different reference categories. The model's low noul probability cannot establish
that an event did not occur. No fatigue diagnosis or readiness interpretation.
English and Spanish are separate language arms; UI locale never translates text.
A translation arm requires its own frozen method and provenance.

Record rater identity, annotation version, language, onset/finish of labeling,
corrections and disagreements in institution-controlled storage. Do not commit
participant narratives or identifiers. Synthetic cases exercise software only.

The Console uses named-rater exposure records. It cannot prevent a researcher
from seeing answers outside the Console or changing their declared rater name;
the study must control access and rater assignments independently.
