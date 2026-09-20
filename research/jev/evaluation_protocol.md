# Semantic coding evaluation and keep-or-remove gate

No empirical benchmark has been run. These are prospective analysis requirements.

Split participants/sessions before prompt development. Keep all repeated excerpts
from a participant in one partition. Freeze ontology, rubric, language arms,
thresholds and exclusions before held-out evaluation; never tune on test errors.
Determine sample size from expected endpoint prevalence and desired interval
precision, with an explicit allowance for clustering and missing labels.

Compare manual-only annotation, a frozen lexical/statistical baseline and JEV
assisted coding on identical eligible excerpts. Report macro-F1, confusion
matrices, class-wise recall, interrater agreement, calibration for probabilistic
outputs, abstention/coverage, coding time and correction burden. Use participant
cluster bootstrap intervals with a prespecified seed and replicate count.
Keep insufficient evidence distinct; report it in coverage and confusion counts.
Report English and Spanish separately. Publish disagreements and negative results.

Retain semantic coding only if it improves useful coding quality or efficiency
over simpler baselines without weakening privacy or reproducibility. Leave the
component disabled when no practical benefit is demonstrated. A software pass
or successful synthetic API call is not a performance or human-validation result.

Future prediction requires a separate causal-time feature builder, both event
and availability cutoffs, training-only normalization, participant-grouped nested
evaluation and a prespecified later performance endpoint. Physiology, shadow
policy evaluation and intervention remain outside v1.
