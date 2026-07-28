"""Unit tests for mathpub workspace GUI backend and PTY manager."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import subprocess
import sys
import threading
import time
import urllib.request

import pytest

from mathpub.config import find_project
from mathpub.errors import MathpubError
from mathpub.gui.libraries import LibraryHistory, open_authoring_library
from mathpub.gui.onboarding import (
    AGENT_BOOTSTRAP_PROMPT,
    AgentConfiguration,
    create_authoring_library,
)
from mathpub.gui.server import (
    WorkspaceServer,
    _feedback_prompt,
    _publication_output_metadata,
)
from mathpub.gui.source_edit import load_tex_source, save_tex_source
from mathpub.gui.terminal import PTYManager
from mathpub.scaffold import init_project


def test_pty_manager_lifecycle():
    pty = PTYManager(command=["echo", "mathpub-pty-test"])
    pty.start(rows=24, cols=80)
    assert pty.master_fd is not None
    assert pty.pid is not None

    deadline = time.monotonic() + 5.0
    output = b""
    while b"mathpub-pty-test" not in output and time.monotonic() < deadline:
        output += pty.read(4096)
        time.sleep(0.02)
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
    assert _feedback_prompt(
        {
            "component_id": "learning-goals",
            "fragment": "slide",
            "authored_source": "publications/credit/slides/01-goals.tex",
            "feedback": "Use a more concrete goal.",
        }
    ) == (
        "Review mathpub slide learning-goals "
        "(slide, publications/credit/slides/01-goals.tex): Use a more concrete goal."
    )


def test_agent_configuration_defaults_to_pinned_antigravity_launcher(monkeypatch):
    monkeypatch.delenv("MATHPUB_AGENT_COMMAND", raising=False)
    configuration = AgentConfiguration.from_environment()
    assert configuration.label == "Antigravity"
    assert configuration.command == (
        "nix",
        "run",
        "github:anicolao/nix-antigravity",
        "--",
        "--new-project",
        "--sandbox",
        "--dangerously-skip-permissions",
        "--prompt-interactive",
        AGENT_BOOTSTRAP_PROMPT,
    )


def test_default_agent_is_confined_to_a_fresh_library_project(tmp_path, monkeypatch):
    monkeypatch.delenv("MATHPUB_AGENT_COMMAND", raising=False)
    (tmp_path / "flake.nix").write_text("{}")
    configuration = AgentConfiguration.from_environment()

    command = configuration.command_for(tmp_path)

    assert command is not None
    assert command[:7] == (
        "nix",
        "develop",
        "--no-write-lock-file",
        "--no-warn-dirty",
        "--quiet",
        "--command",
        "nix",
    )
    agent_arguments = command[7:]
    assert agent_arguments[:5] == (
        "run",
        "github:anicolao/nix-antigravity",
        "--",
        "--new-project",
        "--sandbox",
    )
    assert "--dangerously-skip-permissions" in agent_arguments
    add_dir = agent_arguments.index("--add-dir")
    assert agent_arguments[add_dir + 1] == str(tmp_path)
    prompt = agent_arguments[agent_arguments.index("--prompt-interactive") + 1]
    assert f"The only authoring library for this session is {tmp_path}." in prompt
    assert "Do not search the home directory" in prompt


def test_agent_configuration_requires_an_available_executable():
    available = AgentConfiguration("Antigravity", (sys.executable, "ready"))
    assert available.available is True
    assert available.shell_command == shlex.join(available.command)
    assert available.payload() == {
        "label": "Antigravity",
        "available": True,
        "command": sys.executable,
        "environment": None,
    }

    missing = AgentConfiguration("Antigravity", ("not-a-real-agent-command",))
    assert missing.available is False
    assert missing.shell_command is None


def test_agent_configuration_uses_project_flake_environment(tmp_path):
    (tmp_path / "flake.nix").write_text("{}")
    configuration = AgentConfiguration("Repository agent", ("repository-agent", "--interactive"))

    assert configuration.available is False
    assert configuration.command_for(tmp_path) == (
        "nix",
        "develop",
        "--no-write-lock-file",
        "--no-warn-dirty",
        "--quiet",
        "--command",
        "repository-agent",
        "--interactive",
    )
    assert configuration.shell_command_for(tmp_path) == (
        "nix develop --no-write-lock-file --no-warn-dirty --quiet "
        "--command repository-agent --interactive"
    )
    assert configuration.payload(tmp_path) == {
        "label": "Repository agent",
        "available": True,
        "command": "repository-agent",
        "environment": "nix develop",
    }


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
    tracked = subprocess.run(
        ["git", "-C", library, "ls-files"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert "flake.nix" in tracked
    assert "AGENTS.md" in tracked
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
    assert "locked `nix develop` environment" in instructions
    assert "`gh` and `git`" in instructions
    assert "add its Nixpkgs attribute to `extraPackages`" in instructions
    assert "`presentation` publication, not a textbook" in instructions
    assert 'kind = "presentation"' in instructions
    assert "place each worked solution on a slide after its" in instructions
    assert "only authoring root for this agent session" in instructions
    flake = (library / "flake.nix").read_text()
    assert "extraPackages = pkgs: with pkgs;" in flake


def test_create_authoring_library_reports_sanitized_command_failure(tmp_path, monkeypatch):
    def fail_lock(command, **_kwargs):
        raise subprocess.CalledProcessError(
            1,
            command,
            output="evaluated authoring shell\n",
            stderr="\x1b[31merror:\x1b[0m token=ghp_not-for-the-author\n",
        )

    monkeypatch.setattr(
        "mathpub.gui.onboarding.shutil.which",
        lambda executable: f"/nix/store/fake/bin/{executable}",
    )
    monkeypatch.setattr("mathpub.gui.onboarding.subprocess.run", fail_lock)

    with pytest.raises(MathpubError) as caught:
        create_authoring_library(str(tmp_path), "broken-library")

    error = caught.value
    assert error.code == "MP-GUI-004"
    assert error.message == "could not pin the library toolchain"
    assert error.details == {
        "stage": "Pinning the library toolchain",
        "command": "/nix/store/fake/bin/nix flake lock",
        "exit_status": 1,
        "output": ("stdout:\nevaluated authoring shell\n\nstderr:\nerror: token=[redacted]"),
    }
    assert not (tmp_path / "broken-library").exists()


def test_existing_and_recent_authoring_libraries_are_validated_and_persisted(
    tmp_path,
    monkeypatch,
):
    first = tmp_path / "algebra-library"
    second = tmp_path / "physics-library"
    init_project(first)
    init_project(second)
    history = LibraryHistory(tmp_path / "workspace-state/recent-libraries.json")

    assert open_authoring_library(str(first)).root == first
    with pytest.raises(MathpubError, match="absolute path"):
        open_authoring_library("algebra-library")
    with pytest.raises(MathpubError, match="not a MathPub authoring library"):
        open_authoring_library(str(tmp_path))

    history.remember(first)
    history.remember(second)
    history.remember(first)

    assert history.recent() == [
        {"name": "algebra-library", "path": str(first)},
        {"name": "physics-library", "path": str(second)},
    ]
    assert json.loads(history.path.read_text()) == {
        "schema": 1,
        "libraries": [str(first), str(second)],
    }

    monkeypatch.chdir(tmp_path)
    restored = WorkspaceServer(library_history=history)
    assert restored.project_root == first
    assert restored._workspace_payload()["recent_libraries"] == history.recent()

    (first / "mathpub.toml").unlink()
    assert history.most_recent().root == second
    assert history.recent() == [{"name": "physics-library", "path": str(second)}]


def test_quick_tex_edit_commits_only_revision_matched_source(tmp_path):
    root = tmp_path / "authoring-library"
    init_project(root)
    source = root / "components/demo/prompt.tex"
    source.parent.mkdir(parents=True)
    source.write_text("Original wording.\n")
    subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "MathPub Test"],
        cwd=root,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "mathpub-test@example.invalid"],
        cwd=root,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial authoring library"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    (root / "README.md").write_text("An unrelated local change.\n")
    project = find_project(root)

    loaded = load_tex_source(project, "components/demo/prompt.tex")
    result = save_tex_source(
        project,
        loaded["path"],
        "Improved wording.\n",
        loaded["revision"],
    )

    assert source.read_text() == "Improved wording.\n"
    assert result["message"] == "Quick edit: components/demo/prompt.tex"
    assert (
        result["commit"]
        == subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    committed_paths = subprocess.run(
        ["git", "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert committed_paths == ["components/demo/prompt.tex"]
    assert subprocess.run(
        ["git", "status", "--short"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines() == [" M README.md"]

    source.write_text("Concurrent agent edit.\n")
    with pytest.raises(MathpubError, match="source changed after it was opened") as caught:
        save_tex_source(
            project,
            loaded["path"],
            "Stale browser edit.\n",
            loaded["revision"],
        )
    assert caught.value.code == "MP-GUI-012"
    assert source.read_text() == "Concurrent agent edit.\n"


def test_quick_tex_edit_rejects_sources_outside_authored_roots(tmp_path):
    root = tmp_path / "authoring-library"
    init_project(root)
    outside = root / "private.tex"
    outside.write_text("Not mapped authored content.\n")
    project = find_project(root)

    with pytest.raises(MathpubError, match="outside the authored-content roots") as caught:
        load_tex_source(project, "private.tex")
    assert caught.value.code == "MP-GUI-010"


def test_quick_tex_edit_creates_first_commit_with_fallback_identity(tmp_path, monkeypatch):
    root = tmp_path / "new-authoring-library"
    init_project(root)
    source = root / "components/demo/prompt.tex"
    source.parent.mkdir(parents=True)
    source.write_text("First draft.\n")
    subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
    isolated_home = tmp_path / "isolated-home"
    isolated_home.mkdir()
    monkeypatch.setenv("HOME", str(isolated_home))
    project = find_project(root)
    loaded = load_tex_source(project, "components/demo/prompt.tex")

    saved = save_tex_source(
        project,
        loaded["path"],
        "First quick edit.\n",
        loaded["revision"],
    )

    assert len(saved["commit"]) == 40
    assert (
        subprocess.run(
            ["git", "show", "--format=%an <%ae>", "--no-patch", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "HOME": str(isolated_home)},
        ).stdout.strip()
        == "MathPub Quick Edit <quick-edit@mathpub.local>"
    )
    assert subprocess.run(
        ["git", "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines() == ["components/demo/prompt.tex"]


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


def test_workspace_server_http(tmp_path):
    project_root = tmp_path / "workspace-project"
    other_project_root = tmp_path / "existing-library"
    init_project(project_root)
    init_project(other_project_root)
    history = LibraryHistory(tmp_path / "recent-libraries.json")
    server = WorkspaceServer(
        host="127.0.0.1",
        port=8912,
        project_root=project_root,
        library_history=history,
    )
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
        assert workspace_data["project"] == "workspace-project"
        assert workspace_data["root"]
        assert workspace_data["recent_libraries"] == []
        assert workspace_data["agent"]["label"] == "Antigravity"
        assert workspace_data["agent"]["environment"] == "nix develop"
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

        open_request = urllib.request.Request(
            "http://127.0.0.1:8912/api/libraries/open",
            data=json.dumps({"path": str(other_project_root)}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        opened = json.loads(urllib.request.urlopen(open_request).read().decode())
        assert opened["library"] == {
            "name": "existing-library",
            "root": str(other_project_root),
        }
        assert opened["workspace"]["root"] == str(other_project_root)
        assert opened["workspace"]["recent_libraries"] == [
            {"name": "existing-library", "path": str(other_project_root)}
        ]
        assert history.most_recent().root == other_project_root
    finally:
        if stop_event and loop_ref:
            loop_ref[0].call_soon_threadsafe(stop_event.set)
