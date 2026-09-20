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
