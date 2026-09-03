import io
import json

from core.controlbridge import StdioControlBridge


def test_stdio_bridge_reads_commands_and_reports_protocol_errors():
    source = io.StringIO('{"command":"pause"}\nnot-json\n{"command":"resume"}\n')
    sink = io.StringIO()
    bridge = StdioControlBridge(source, sink)

    bridge.start()
    bridge._reader.join(timeout=1)

    assert [item["command"] for item in bridge.drain()] == ["pause", "resume"]
    errors = [json.loads(line) for line in sink.getvalue().splitlines()]
    assert errors[0]["schema_version"] == "1.0"
    assert errors[0]["event"] == "protocol_error"


def test_stdio_bridge_emits_compact_utf8_json_lines():
    sink = io.StringIO()
    bridge = StdioControlBridge(io.StringIO(), sink)

    bridge.emit("ready", state="ejecución")

    assert json.loads(sink.getvalue()) == {
        "schema_version": "1.0",
        "event": "ready",
        "state": "ejecución",
    }
