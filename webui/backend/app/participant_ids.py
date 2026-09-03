"""Shared participant pseudonym contract for every research workflow."""

from __future__ import annotations


# Keep this contract aligned with the browser helper in
# ``webui/frontend/src/lib/participant-id.ts``. Participant identifiers are
# deliberately pseudonymous and stable across all research instruments.
PARTICIPANT_ID_PATTERN = r"^P[0-9]{2,6}$"
