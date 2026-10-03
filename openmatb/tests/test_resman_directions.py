from types import SimpleNamespace
import pytest
from core.container import Container
from core.widgets.pump import Pump
from core.widgets import pumpflow

@pytest.mark.parametrize('source_x,destination_x,offset', [(0, 200, 30), (200, 0, 0)])
def test_direction_tip_is_outside_destination_and_does_not_reverse(source_x, destination_x, offset):
    source = Container('source', source_x, 100, 60, 100)
    destination = Container('destination', destination_x, 100, 60, 100)
    v = Pump.flow_arrow_vertices(source, destination, 18, offset)
    direction = 1 if source.cx < destination.cx else -1
    assert v[1] == source.cy + offset
    assert (v[0] - v[2]) * direction > 0
    assert v[0] < destination.l if direction == 1 else v[0] > destination.l + destination.w

def test_elbow_direction_uses_destination_pipe_height():
    source = Container('C', 0, 0, 60, 100)
    destination = Container('A', 100, 200, 90, 100)
    assert Pump.flow_arrow_vertices(source, destination, 18, 0)[1] == destination.cy - 20

def test_status_route_is_fixed_when_flow_changes(monkeypatch):
    monkeypatch.setattr(pumpflow, 'Label', lambda text, **kwargs: SimpleNamespace(text=text, **kwargs))
    widget = pumpflow.PumpFlow('pump_7_flow', Container('flow', 0, 0, 640, 54), '7', 400, route='A → B')
    widget.set_flow(400)
    assert widget.vertex['route'].text == 'A → B'
    assert widget.vertex['rate'].text == '400'
    widget.set_flow(0)
    assert widget.vertex['route'].text == 'A → B'
    assert widget.vertex['rate'].text == '0'
    assert widget.vertex['7'].text == '7'
