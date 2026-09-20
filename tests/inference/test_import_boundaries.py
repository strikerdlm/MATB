import ast
from pathlib import Path


def test_inference_has_no_runtime_or_action_imports():
    root=Path(__file__).resolve().parents[2]/'matb_integration'/'inference'
    forbidden=('matb_integration.automation','matb_integration.runtime','aircraft_monitor','SMS','pyglet')
    for file in root.glob('*.py'):
        for node in ast.walk(ast.parse(file.read_text(encoding='utf-8'))):
            modules=[n.name for n in node.names] if isinstance(node,ast.Import) else [node.module or ''] if isinstance(node,ast.ImportFrom) else []
            assert not any(name.startswith(forbidden) for name in modules),file
