"""Unit tests for mathpub workspace GUI backend and PTY manager."""

from __future__ import annotations

import asyncio
import json
import threading
import time
import urllib.request

from mathpub.gui.server import WorkspaceServer
from mathpub.gui.terminal import PTYManager


def test_pty_manager_lifecycle():
    pty = PTYManager(command=["echo", "mathpub-pty-test"])
    pty.start(rows=24, cols=80)
    assert pty.master_fd is not None
    assert pty.pid is not None

    time.sleep(0.2)
    output = pty.read(4096)
    assert b"mathpub-pty-test" in output

    pty.set_size(rows=40, cols=120)
    pty.close()
    assert not pty.is_alive()


def test_workspace_server_http():
    server = WorkspaceServer(host="127.0.0.1", port=8912)
    server_ready = threading.Event()
    stop_event = None
    loop_ref = []

    def thread_main():
        nonlocal stop_event
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop_ref.append(loop)
        stop_event = asyncio.Event()

        async def run_server():
            srv = await asyncio.start_server(server.handle_client, "127.0.0.1", 8912)
            async with srv:
                server_ready.set()
                await stop_event.wait()

        loop.run_until_complete(run_server())

    t = threading.Thread(target=thread_main, daemon=True)
    t.start()

    # Wait until server is listening
    assert server_ready.wait(timeout=3.0)

    try:
        # Test /api/health endpoint
        req = urllib.request.urlopen("http://127.0.0.1:8912/api/health")
        assert req.status == 200
        data = json.loads(req.read().decode("utf-8"))
        assert data["status"] == "ok"

        # Test static file serving (index.html)
        req_root = urllib.request.urlopen("http://127.0.0.1:8912/")
        assert req_root.status == 200
        html = req_root.read().decode("utf-8")
        assert "mathpub Interactive Workspace" in html
    finally:
        if stop_event and loop_ref:
            loop_ref[0].call_soon_threadsafe(stop_event.set)
