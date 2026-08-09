from __future__ import annotations

import io
import json

from mathpub.cli import main
from mathpub.mcp import serve_mcp


def _serve(monkeypatch, messages):
    delivered = []

    def notify(html):
        delivered.append(html)
        return {"delivered": True, "summary_bytes": len(html.encode("utf-8"))}

    monkeypatch.setattr("mathpub.mcp.notify_completion", notify)
    source = io.StringIO("".join(json.dumps(message) + "\n" for message in messages))
    destination = io.StringIO()
    assert serve_mcp(source, destination) == 0
    return [json.loads(line) for line in destination.getvalue().splitlines()], delivered


def test_mcp_advertises_and_delivers_required_completion_tool(monkeypatch):
    html = "<h3>Book ready</h3><p>Validated all projections.</p>"
    responses, delivered = _serve(
        monkeypatch,
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "complete_task", "arguments": {"html": html}},
            },
        ],
    )

    assert len(responses) == 3
    initialized = responses[0]["result"]
    assert initialized["capabilities"] == {"tools": {}}
    assert "call complete_task exactly once" in initialized["instructions"]
    tool = responses[1]["result"]["tools"][0]
    assert tool["name"] == "complete_task"
    assert "REQUIRED FINAL ACTION" in tool["description"]
    assert tool["inputSchema"]["required"] == ["html"]
    assert tool["inputSchema"]["additionalProperties"] is False
    assert delivered == [html]
    assert responses[2]["result"]["structuredContent"] == {
        "delivered": True,
        "summary_bytes": len(html.encode("utf-8")),
    }


def test_mcp_returns_tool_error_for_missing_html(monkeypatch):
    responses, delivered = _serve(
        monkeypatch,
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "complete_task", "arguments": {}},
            }
        ],
    )

    assert delivered == []
    assert responses[0]["result"]["isError"] is True
    assert "requires an HTML string" in responses[0]["result"]["content"][0]["text"]


def test_mcp_emits_json_rpc_parse_errors():
    source = io.StringIO("not json\n")
    destination = io.StringIO()

    assert serve_mcp(source, destination) == 0

    response = json.loads(destination.getvalue())
    assert response["id"] is None
    assert response["error"] == {"code": -32700, "message": "invalid JSON"}


def test_mcp_cli_keeps_stdout_protocol_clean(monkeypatch):
    source = io.StringIO('{"jsonrpc":"2.0","id":7,"method":"ping"}\n')
    destination = io.StringIO()
    monkeypatch.setattr("sys.stdin", source)
    monkeypatch.setattr("sys.stdout", destination)

    assert main(["mcp"]) == 0

    assert json.loads(destination.getvalue()) == {
        "jsonrpc": "2.0",
        "id": 7,
        "result": {},
    }
