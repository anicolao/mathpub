"""Minimal stdio MCP server for MathPub workspace agent tools."""

from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from mathpub import display_version
from mathpub.completion import load_completion_html, notify_completion
from mathpub.errors import MathpubError

MCP_PROTOCOL_VERSION = "2025-06-18"
COMPLETE_TASK_TOOL = {
    "name": "complete_task",
    "title": "Complete MathPub task",
    "description": (
        "REQUIRED FINAL ACTION: Call this tool after the user's requested work and "
        "validation are genuinely complete, before giving the final conversational response. "
        "If the tool returns pending generated-page reviews, process them and call it again; only "
        "one successful call is expected. "
        "It opens the author's visible Completed! dialog and sounds a chime. Supply concise HTML "
        "covering what changed, what was validated, and what is ready to review. Never finish a "
        "successful task only with terminal prose; do not call this for progress, questions, "
        "partial results, or blocked work."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "html": {
                "type": "string",
                "description": (
                    "Concise HTML summary using headings, paragraphs, lists, emphasis, code, "
                    "and safe http(s) links."
                ),
            }
        },
        "required": ["html"],
        "additionalProperties": False,
    },
    "annotations": {
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
}


def _result(request_id: object, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: object, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _tool_error(message: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    }


def handle_mcp_message(message: object) -> dict[str, Any] | None:
    """Handle one decoded MCP request or notification."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(None, -32600, "invalid JSON-RPC request")

    method = message.get("method")
    request_id = message.get("id")
    if request_id is None:
        return None

    if method == "initialize":
        params = message.get("params")
        requested_version = params.get("protocolVersion") if isinstance(params, dict) else None
        protocol_version = (
            requested_version if isinstance(requested_version, str) else MCP_PROTOCOL_VERSION
        )
        return _result(
            request_id,
            {
                "protocolVersion": protocol_version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "mathpub-workspace", "version": display_version()},
                "instructions": (
                    "For every successfully completed user task, call complete_task before the "
                    "final response. If it returns pending generated-page reviews, process them "
                    "and retry; terminal prose alone is not a completion signal."
                ),
            },
        )
    if method == "ping":
        return _result(request_id, {})
    if method == "tools/list":
        return _result(request_id, {"tools": [COMPLETE_TASK_TOOL]})
    if method == "tools/call":
        params = message.get("params")
        if not isinstance(params, dict) or params.get("name") != COMPLETE_TASK_TOOL["name"]:
            return _error(request_id, -32602, "unknown MathPub tool")
        arguments = params.get("arguments")
        html = arguments.get("html") if isinstance(arguments, dict) else None
        if not isinstance(html, str):
            return _result(request_id, _tool_error("complete_task requires an HTML string"))
        try:
            summary = load_completion_html(html=html, html_file=None)
            delivered = notify_completion(summary)
        except MathpubError as error:
            return _result(request_id, _tool_error(f"{error.code}: {error.message}"))
        return _result(
            request_id,
            {
                "content": [
                    {
                        "type": "text",
                        "text": "Completed summary delivered to the MathPub workspace.",
                    }
                ],
                "structuredContent": delivered,
            },
        )
    return _error(request_id, -32601, f"method not found: {method}")


def serve_mcp(
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> int:
    """Serve newline-delimited MCP messages until the client closes stdin."""
    source = input_stream or sys.stdin
    destination = output_stream or sys.stdout
    for line in source:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            response = _error(None, -32700, "invalid JSON")
        else:
            response = handle_mcp_message(message)
        if response is None:
            continue
        destination.write(json.dumps(response, separators=(",", ":")) + "\n")
        destination.flush()
    return 0
