"""Unit tests for mathpub workspace GUI backend and PTY manager."""

from __future__ import annotations

import asyncio
import json
import threading
import time
import urllib.request

from mathpub.gui.onboarding import AgentConfiguration, create_authoring_library
from mathpub.gui.server import (
    WorkspaceServer,
    _feedback_prompt,
    _publication_output_metadata,
)
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


def test_feedback_prompt_is_single_line_and_validated():
    prompt = _feedback_prompt(
        {
            "component_id": "physics.energy.ramp-speed",
            "fragment": "prompt",
            "authored_source": "components/questions/physics/energy/ramp-speed/prompt.tex",
            "feedback": "Clarify the energy argument.\nEnlarge the \x1bdiagram.",
        }
    )
    assert prompt == (
        "Review mathpub component physics.energy.ramp-speed "
        "(prompt, components/questions/physics/energy/ramp-speed/prompt.tex): "
        "Clarify the energy argument. Enlarge the diagram."
    )
    assert (
        _feedback_prompt(
            {
                "component_id": "physics.energy.ramp-speed; rm",
                "fragment": "prompt",
                "authored_source": "prompt.tex",
                "feedback": "No",
            }
        )
        is None
    )


def test_agent_configuration_defaults_to_pinned_antigravity_launcher(monkeypatch):
    monkeypatch.delenv("MATHPUB_AGENT_COMMAND", raising=False)
    configuration = AgentConfiguration.from_environment()
    assert configuration.label == "Antigravity"
    assert configuration.command == (
        "nix",
        "run",
        "github:anicolao/nix-antigravity",
    )


def test_agent_configuration_requires_an_available_executable():
    available = AgentConfiguration("Antigravity", ("/bin/echo", "ready"))
    assert available.available is True
    assert available.shell_command == "/bin/echo ready"
    assert available.payload() == {
        "label": "Antigravity",
        "available": True,
        "command": "/bin/echo",
    }

    missing = AgentConfiguration("Antigravity", ("not-a-real-agent-command",))
    assert missing.available is False
    assert missing.shell_command is None


def test_create_authoring_library_initializes_agent_ready_git_project(tmp_path):
    result = create_authoring_library(
        str(tmp_path),
        "anna-math-library",
        mathpub_url="github:publisher/mathpub",
        lock_flake=False,
    )

    library = tmp_path / "anna-math-library"
    assert result["root"] == str(library)
    assert result["git_initialized"] is True
    assert result["flake_locked"] is False
    assert result["remote_created"] is False
    assert (library / ".git/HEAD").read_text().strip() == "ref: refs/heads/main"
    assert (library / "mathpub.toml").is_file()
    assert {path.name for path in library.iterdir()} >= {
        ".git",
        ".gitignore",
        "AGENTS.md",
        "README.md",
        "components",
        "flake.nix",
        "mathpub.toml",
        "profiles",
        "publications",
    }
    instructions = (library / "AGENTS.md").read_text()
    assert "many related publications" in instructions
    assert "Operate MathPub on the author's behalf" in instructions
    assert "student, answer, solution, validation, and\nparent editions" in instructions


def test_publication_metadata_reports_stale_synctex_build(tmp_path):
    project_root = tmp_path / "project"
    edition = project_root / "build/demo/A"
    generated = edition / "generated-tex"
    generated.mkdir(parents=True)
    manifest_path = edition / "manifest.json"
    pdf_path = edition / "demo-A-student.pdf"
    pdf_path.write_bytes(b"%PDF fixture")
    (generated / "demo-A-student.tex").write_text("generated")
    (generated / "source-map.json").write_text("{}")
    synctex_path = edition / "demo-A-student.synctex.gz"
    synctex_path.write_bytes(b"synctex fixture")
    manifest = {
        "publication_id": "demo",
        "publication_path": "publications/demo.toml",
        "root_seed": "2026",
        "variant": "A",
        "lesson_ids": ["lesson-one"],
    }
    output = {
        "path": pdf_path.name,
        "projection": "student",
        "synctex": synctex_path.name,
        "pages": 3,
    }

    resolved_path, metadata = _publication_output_metadata(manifest_path, manifest, output)
    assert resolved_path == pdf_path
    assert metadata["synctex_ready"] is True
    assert metadata["pages"] == 3
    assert metadata["lesson_ids"] == ["lesson-one"]

    synctex_path.unlink()
    _, stale_metadata = _publication_output_metadata(manifest_path, manifest, output)
    assert stale_metadata["synctex_ready"] is False
    assert stale_metadata["mapping_error"] == "Missing SyncTeX data"
    assert stale_metadata["mapping_rebuild_command"] == (
        "nix run '.#mathpub' -- build publications/demo.toml "
        "--seed 2026 --variant A --replace --json"
    )


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

        req_workspace = urllib.request.urlopen("http://127.0.0.1:8912/api/workspace")
        assert req_workspace.status == 200
        workspace_data = json.loads(req_workspace.read().decode("utf-8"))
        assert workspace_data["project"] == "mathpub"
        assert workspace_data["root"]
        assert workspace_data["agent"]["label"] == "Antigravity"
        assert "Outline my first book" in workspace_data["starter_prompt"]

        # Test static file serving (index.html)
        req_root = urllib.request.urlopen("http://127.0.0.1:8912/")
        assert req_root.status == 200
        html = req_root.read().decode("utf-8")
        assert "mathpub Interactive Workspace" in html

        # Test /api/publications endpoint
        req_pubs = urllib.request.urlopen("http://127.0.0.1:8912/api/publications")
        assert req_pubs.status == 200
        pubs_data = json.loads(req_pubs.read().decode("utf-8"))
        assert "publications" in pubs_data
    finally:
        if stop_event and loop_ref:
            loop_ref[0].call_soon_threadsafe(stop_event.set)
