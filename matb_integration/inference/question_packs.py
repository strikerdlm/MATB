"""Only repository-owned frozen question packs may become provider instructions."""
from pathlib import Path
from .contracts import QuestionPackV1


def load_question_pack(pack_id: str) -> QuestionPackV1:
    if pack_id != 'matb-debrief-v1':
        raise ValueError('unsupported question pack')
    return QuestionPackV1.model_validate_json(
        (Path(__file__).parent / 'judges' / 'matb-debrief-v1.json').read_bytes())
