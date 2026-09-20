"""Explicitly activated experimental semantic-review component."""
from matb_integration.contracts import ComponentManifestV1


class InferenceComponentProvider:
    manifest = ComponentManifestV1.create(component_id='matb-semantic-review',
        component_version='0.1.0-alpha.1', component_kind='research',
        stability='experimental', distribution='optional',
        capabilities=('research.semantic-review',),
        requires=('matb-contracts','matb-research','matb-console'),
        python_entrypoint='app.inference_component:provider', license_expression='MIT')
    model_modules = ('app.inference_models',)
    router_modules = ('app.routers.inference',)

    async def startup(self, app):
        from app.db import get_engine
        from app.inference_service import recover_inference
        recover_inference(get_engine())

    async def shutdown(self, app):
        pass  # The shared station worker owns and drains all provider I/O.


provider = InferenceComponentProvider()
