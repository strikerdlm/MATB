import io
import json
import zipfile
import pytest
from test_privacy import reviewed_input
from test_response_validation import wire, attempt
from matb_integration.inference.contracts import canonical_bytes


def bundle():
    from matb_integration.inference.replay import build_bundle
    return build_bundle(reviewed_input(),attempt(canonical_bytes(wire())))


def test_replay_is_network_free_and_exact(tmp_path, monkeypatch):
    from matb_integration.inference.replay import verify_inference_bundle
    import socket
    monkeypatch.setattr(socket,'create_connection',lambda *a,**k: pytest.fail('network'))
    path=tmp_path/'inference.zip'
    path.write_bytes(bundle())
    first=verify_inference_bundle(str(path))
    assert first==verify_inference_bundle(str(path))
    assert first['result']['outcome']=='valid'


@pytest.mark.parametrize('mutation',['payload','manifest','response','traversal','oversize'])
def test_invalid_bundle_rejected(tmp_path,mutation):
    from matb_integration.inference.replay import verify_inference_bundle
    with zipfile.ZipFile(io.BytesIO(bundle())) as archive:
        members={name:archive.read(name) for name in archive.namelist()}
    if mutation=='payload': members['payload.json']=b'{}'
    if mutation=='manifest': members.pop('manifest.json')
    if mutation=='response': members['response.json']=b'{}'
    if mutation=='traversal': members['../outside']=b'bad'
    if mutation=='oversize': members['response.json']=b'x'*300000
    path=tmp_path/'bad.zip'
    with zipfile.ZipFile(path,'w') as archive:
        for name,content in members.items(): archive.writestr(name,content)
    with pytest.raises(ValueError): verify_inference_bundle(str(path))


def test_late_response_remains_late_on_replay(tmp_path):
    from matb_integration.inference.replay import build_bundle, verify_inference_bundle
    path=tmp_path/'late.zip'
    path.write_bytes(build_bundle(reviewed_input(),attempt(canonical_bytes(wire())),disposition='late'))
    assert verify_inference_bundle(str(path))['result']['outcome']=='late'


@pytest.mark.parametrize('field',['annotation','approval','parent','credential'])
def test_extended_provenance_rejects_changed_identity_even_with_new_checksums(tmp_path,field):
    from test_contracts import annotation
    from test_privacy import approval
    from matb_integration.inference.contracts import sha256
    from matb_integration.inference.replay import build_bundle,verify_inference_bundle
    value=reviewed_input();auth=approval(value);encoded=canonical_bytes(auth)
    provenance={'annotations':[annotation().model_dump(mode='json')],'approval':auth,
        'approval_json':encoded.decode(),'approval_hash':sha256(encoded),'approval_id':'a','run_id':'r',
        'input_identity':value.input_identity,'audit':[]}
    original=build_bundle(value,attempt(canonical_bytes(wire())),provenance=provenance)
    with zipfile.ZipFile(io.BytesIO(original)) as archive:
        members={name:archive.read(name) for name in archive.namelist()}
    if field=='annotation':provenance['annotations'][0]['original_text']='changed'
    if field=='approval':provenance['approval']['payload_hash']='f'*64
    if field=='parent':provenance['annotations'][0]['supersedes_annotation_id']='missing'
    if field=='credential':provenance['audit']=[{'api_key':'secret'}]
    members['provenance.json']=canonical_bytes(provenance)
    manifest=json.loads(members['manifest.json']);manifest['checksums']['provenance.json']=sha256(members['provenance.json'])
    members['manifest.json']=canonical_bytes(manifest)
    path=tmp_path/'tampered.zip'
    with zipfile.ZipFile(path,'w') as archive:
        for name,content in members.items():archive.writestr(name,content)
    with pytest.raises(ValueError):verify_inference_bundle(str(path))
