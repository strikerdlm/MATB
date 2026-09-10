"""Shared mission presentation validation, used by authoring and actual launch."""
from matb_integration.suas.presentation.packages import read_package


def bind_presentation(manifest, config, loaded, *, technical_block=None):
    if config is None:
        return
    if config.scene_id:
        read_package(config.scene_id, config.scene_sha256)
        if loaded.definition.terrain.bounds != (0, 0, 12000000, 8000000):
            raise ValueError('scene package requires the 12 by 8 km reference footprint')
    if config.traffic.mode == 'live' and technical_block is None:
        raise ValueError('research sessions require recorded traffic')
    if config.traffic.mode == 'recorded':
        from .traffic_service import load_recording
        recording = load_recording(config.traffic.recording_id, config.traffic.recording_sha256)
        if recording['scene_id'] != config.scene_id or recording['scene_sha256'] != config.scene_sha256:
            raise ValueError('traffic recording belongs to a different scene')
        if recording['provider'] != config.traffic.provider:
            raise ValueError('traffic recording belongs to a different provider')
        blocks = [technical_block] if technical_block is not None else list(loaded.definition.blocks)
        if any(recording['duration_ms'] < loaded.definition.blocks[b].duration_ms for b in blocks):
            raise ValueError('traffic recording is shorter than the mission block')
    manifest['presentation'] = config.model_dump(mode='json')
