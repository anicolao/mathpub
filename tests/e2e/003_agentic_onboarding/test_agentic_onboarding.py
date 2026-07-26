"""E2E coverage for private-library creation and one-click agent startup."""

from __future__ import annotations

import asyncio
import os
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

from mathpub.config import find_project
from mathpub.errors import MathpubError
from mathpub.gui.onboarding import create_authoring_library
from mathpub.gui.server import WorkspaceServer
from tests.e2e.helpers.gui_step_helper import GUIStepHelper


def test_agentic_onboarding_e2e(tmp_path: Path, update_baselines: bool):
    if os.environ.get("HOME") == "/homeless-shelter":
        import pytest

        pytest.skip("Playwright IPC restricted in Nix build sandbox (/homeless-shelter).")

    scenario_dir = Path(__file__).parent
    steps = GUIStepHelper(scenario_dir, update_baselines)
    project = find_project()
    creation_attempts = 0

    def fail_once_then_create(parent, name, **kwargs):
        nonlocal creation_attempts
        creation_attempts += 1
        if creation_attempts == 1:
            raise MathpubError(
                "MP-GUI-004",
                "could not pin the library toolchain",
                details={
                    "stage": "Pinning the library toolchain",
                    "command": "nix flake lock",
                    "exit_status": 1,
                    "output": "stderr:\nerror: deterministic lock failure",
                },
            )
        return create_authoring_library(parent, name, **kwargs)

    server = WorkspaceServer(
        host="127.0.0.1",
        port=0,
        project_root=tmp_path,
        agent_command=[
            "sh",
            "-c",
            'test "$MATHPUB_AUTHORING_ENV" = 1 && command -v gh >/dev/null '
            '&& printf "\\033cAntigravity E2E %s\\n" ready',
        ],
        mathpub_url=f"path:{project.root}",
        library_creator=fail_once_then_create,
    )
    server_ready = threading.Event()
    stop_event = None
    loop_ref = []
    bound_port = 0

    def thread_main():
        nonlocal stop_event, bound_port
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop_ref.append(loop)
        stop_event = asyncio.Event()

        async def run_server():
            nonlocal bound_port
            listener = await asyncio.start_server(server.handle_client, "127.0.0.1", 0)
            for socket in listener.sockets:
                os.set_inheritable(socket.fileno(), False)
            bound_port = listener.sockets[0].getsockname()[1]
            async with listener:
                server_ready.set()
                await stop_event.wait()

        loop.run_until_complete(run_server())

    thread = threading.Thread(target=thread_main, daemon=True)
    thread.start()
    assert server_ready.wait(timeout=5.0)

    with sync_playwright() as playwright:
        browser = (
            playwright.webkit.launch(headless=True)
            if sys.platform == "darwin"
            else playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--font-render-hinting=none",
                ],
            )
        )
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.goto(f"http://127.0.0.1:{bound_port}/", wait_until="domcontentloaded")
            page.wait_for_function(
                "document.getElementById('library-name').textContent === 'No library open'"
            )
            assert page.locator("#start-agent").is_disabled()
            assert page.locator("#placeholder-title").text_content() == (
                "Create your private authoring library"
            )

            page.locator("#create-library").click()
            dialog = page.locator("#library-dialog")
            assert dialog.is_visible()
            assert page.locator("#library-title").text_content() == "Create an authoring library"
            page.locator("#library-parent").fill(str(tmp_path))
            page.locator("#library-project-name").fill("anna-math-library")
            page.locator("#library-submit").click()

            page.wait_for_function(
                "document.getElementById('library-error').textContent.includes("
                "'deterministic lock failure')"
            )
            assert dialog.is_visible()
            assert page.locator("#library-submit").is_enabled()
            error_text = page.locator("#library-error").text_content()
            assert "could not pin the library toolchain" in error_text
            assert "Code: MP-GUI-004" in error_text
            assert "Stage: Pinning the library toolchain" in error_text
            assert "Command: nix flake lock" in error_text
            assert "Exit status: 1" in error_text
            assert "stderr:\nerror: deterministic lock failure" in error_text

            page.locator("#library-submit").click()
            page.wait_for_function(
                "document.getElementById('library-name').textContent === 'anna-math-library'",
                timeout=30_000,
            )
            library = tmp_path / "anna-math-library"
            assert (library / "mathpub.toml").is_file()
            assert (library / "flake.lock").is_file()
            assert (library / ".git/HEAD").read_text().strip() == "ref: refs/heads/main"
            instructions = (library / "AGENTS.md").read_text()
            assert "Operate MathPub on the author's behalf" in instructions
            assert "many related publications" in instructions
            assert "locked `nix develop` environment" in instructions
            assert "`gh` and `git`" in instructions
            assert "extraPackages" in instructions

            workspace = page.request.get(f"http://127.0.0.1:{bound_port}/api/workspace").json()
            assert workspace["project"] == "anna-math-library"
            assert workspace["root"] == str(library)
            assert workspace["agent"]["available"] is True
            assert workspace["agent"]["environment"] == "nix develop"

            page.wait_for_function(
                "!document.getElementById('start-agent').disabled && "
                "document.querySelector('.xterm-rows').textContent.includes('mathpub$')"
            )
            page.locator("#start-agent").click()
            page.wait_for_function(
                "document.querySelector('.xterm-rows').textContent.includes("
                "'Antigravity E2E ready')",
                timeout=300_000,
            )
            assert page.locator("#agent-status").text_content() == "Antigravity started"

            page.locator("#starter-prompt").click()
            page.wait_for_function(
                "document.querySelector('.xterm-rows').textContent.includes("
                "'Outline my first book')"
            )
            terminal_text = page.locator(".xterm-rows").text_content()
            assert "Outline my first book" in terminal_text
            assert "command not found" not in terminal_text
            assert page.locator("#agent-status").text_content() == "First-book prompt ready"
            assert page.locator("#placeholder-title").text_content() == (
                "Your authoring agent is ready"
            )

            steps.verify(page, "000-private-library-agent-ready")
        finally:
            if browser.is_connected():
                browser.close()
            if stop_event and loop_ref:
                loop_ref[0].call_soon_threadsafe(stop_event.set)
