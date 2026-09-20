"""Checksummed bounded artifacts; replay has no provider-client dependency."""
import io
import json
from pathlib import Path
import zipfile
from .contracts import InferenceInputV1, ProviderAttempt, QuestionPackV1, canonical_bytes, sha256
from .question_packs import load_question_pack
from .response_validation import validate_response

MEMBERS={'input.json','payload.json','question-pack.json','attempt.json','response.json','reviews.json','manifest.json'}


def reject_credentials(value):
    if isinstance(value,dict):
        if any(str(k).lower() in {'authorization','api_key','jev_ai_api_key','access_token','password'} for k in value):
            raise ValueError('forbidden credential field')
        for child in value.values(): reject_credentials(child)
    elif isinstance(value,list):
        for child in value: reject_credentials(child)


def build_bundle(value: InferenceInputV1, attempt: ProviderAttempt, reviews=None, *, disposition=None) -> bytes:
    members={'input.json':value.model_dump_json().encode(), 'payload.json':value.outbound_bytes,
        'question-pack.json':load_question_pack(value.question_pack_id).model_dump_json().encode(),
        'attempt.json':attempt.model_dump_json().encode(),'response.json':attempt.raw_response,
        'reviews.json':canonical_bytes(reviews or [])}
    for name,content in members.items():
        if len(content)>200000: raise ValueError('bundle member too large')
        try: reject_credentials(json.loads(content))
        except json.JSONDecodeError:
            if name!='response.json': raise
    validated=validate_response(json.loads(value.outbound_bytes),attempt)
    disposition=disposition or validated.outcome
    if disposition not in {validated.outcome,'late','outcome_unknown'}:
        raise ValueError('invalid archived disposition')
    members['manifest.json']=canonical_bytes({'schema_version':'1.0','input_identity':value.input_identity,'disposition':disposition,
        'checksums':{name:sha256(content) for name,content in members.items()}})
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,content in sorted(members.items()): archive.writestr(name,content)
    return output.getvalue()


def verify_inference_bundle(path: str) -> dict:
    if Path(path).stat().st_size>1000000: raise ValueError('bundle too large')
    try:
        with zipfile.ZipFile(path) as archive:
            entries=archive.infolist()
            if len(entries)!=len(MEMBERS) or {e.filename for e in entries}!=MEMBERS:
                raise ValueError('bundle member inventory')
            if any(e.file_size>200000 or e.flag_bits&1 for e in entries) or sum(e.file_size for e in entries)>1000000:
                raise ValueError('bundle size or encryption')
            members={entry.filename:archive.read(entry) for entry in entries}
        manifest=json.loads(members['manifest.json'])
        if manifest['schema_version']!='1.0' or set(manifest['checksums'])!=MEMBERS-{'manifest.json'}:
            raise ValueError('manifest schema')
        if any(sha256(members[name])!=digest for name,digest in manifest['checksums'].items()):
            raise ValueError('checksum mismatch')
        value=InferenceInputV1.model_validate_json(members['input.json'])
        pack=QuestionPackV1.model_validate_json(members['question-pack.json'])
        attempt=ProviderAttempt.model_validate_json(members['attempt.json'])
        if value.input_identity!=manifest['input_identity'] or sha256(pack)!=value.question_pack_hash:
            raise ValueError('input or question identity')
        if members['payload.json']!=value.outbound_bytes or members['response.json']!=attempt.raw_response:
            raise ValueError('payload or response identity')
        payload=json.loads(value.outbound_bytes)
        if payload['questions']!=pack.model_dump()['questions'] or payload['model']!=value.requested_model:
            raise ValueError('payload rubric or model')
        for name,content in members.items():
            try: reject_credentials(json.loads(content))
            except json.JSONDecodeError:
                if name!='response.json': raise
        result=validate_response(payload,attempt).model_dump(mode='json')
        disposition=manifest['disposition']
        if disposition not in {result['outcome'],'late','outcome_unknown'}:
            raise ValueError('invalid archived disposition')
        result['outcome']=disposition
        return {'input_identity':value.input_identity,'result':result}
    except (KeyError,TypeError,zipfile.BadZipFile,UnicodeError) as exc:
        raise ValueError('invalid inference bundle') from exc
