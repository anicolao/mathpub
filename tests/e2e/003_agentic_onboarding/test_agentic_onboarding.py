"""E2E coverage for private-library creation and one-click agent startup."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import threading
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from mathpub.completion import notify_completion
from mathpub.config import find_project
from mathpub.errors import MathpubError
from mathpub.gui.libraries import LibraryHistory
from mathpub.gui.onboarding import create_authoring_library
from mathpub.gui.server import WorkspaceServer
from mathpub.scaffold import init_project
from tests.e2e.helpers.gui_step_helper import GUIStepHelper

AGENT_START_TIMEOUT_MS = int(os.environ.get("MATHPUB_AGENT_E2E_TIMEOUT_MS", "120000"))


def test_agentic_onboarding_e2e(tmp_path: Path, update_baselines: bool):
    if os.environ.get("HOME") == "/homeless-shelter":
        import pytest

        pytest.skip("Playwright IPC restricted in Nix build sandbox (/homeless-shelter).")

    scenario_dir = Path(__file__).parent
    steps = GUIStepHelper(scenario_dir, update_baselines)
    project = find_project()
    library = tmp_path / "anna-math-library"
    existing_library = tmp_path / "existing-library"
    init_project(existing_library)
    history = LibraryHistory(tmp_path / "workspace-state/recent-libraries.json")
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
            'test "$MATHPUB_AUTHORING_ENV" = 1 && test "$PWD" = "$1" '
            '&& test -n "$MATHPUB_WORKSPACE_COMPLETION_URL" '
            '&& test -n "$MATHPUB_WORKSPACE_COMPLETION_TOKEN" '
            "&& command -v gh >/dev/null "
            "&& command -v pdftotext >/dev/null "
            '&& grep -q "Use the worked examples" reference/course-outline.txt '
            '&& printf "\\033cAntigravity E2E %s\\n" ready',
            "mathpub-agent-e2e",
            str(library),
        ],
        mathpub_url=f"path:{project.root}",
        library_creator=fail_once_then_create,
        library_history=history,
        build_version="0.1.0 (e2e0000)",
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
            page.add_init_script(
                """
                window.__completionChimeNotes = [];
                class TestAudioParam {
                  setValueAtTime() {}
                  exponentialRampToValueAtTime() {}
                }
                class TestAudioNode {
                  connect() { return this; }
                }
                class TestOscillator extends TestAudioNode {
                  constructor() {
                    super();
                    this.frequency = new TestAudioParam();
                    this.type = "sine";
                  }
                  start(when) { window.__completionChimeNotes.push(when); }
                  stop() {}
                }
                class TestGain extends TestAudioNode {
                  constructor() {
                    super();
                    this.gain = new TestAudioParam();
                  }
                }
                class TestAudioContext {
                  constructor() {
                    this.currentTime = 1;
                    this.destination = {};
                    this.state = "running";
                  }
                  createOscillator() { return new TestOscillator(); }
                  createGain() { return new TestGain(); }
                  resume() { return Promise.resolve(); }
                }
                window.AudioContext = TestAudioContext;
                window.webkitAudioContext = TestAudioContext;
                """
            )
            page.goto(f"http://127.0.0.1:{bound_port}/", wait_until="domcontentloaded")
            page.wait_for_function(
                "document.getElementById('library-name').textContent === 'No library open'"
            )
            assert page.locator("#start-agent").is_disabled()
            assert page.locator("#placeholder-title").text_content() == (
                "Open or create your authoring library"
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
            assert (library / "mathpub.toml").is_file()
            assert (library / "styles").is_dir()
            assert (library / "flake.lock").is_file()
            assert (library / ".git/HEAD").read_text().strip() == "ref: refs/heads/main"
            instructions = (library / "AGENTS.md").read_text()
            assert "nix run .#mathpub -- capabilities" in instructions
            assert "version-matched framework contract" in instructions
            assert "locked `nix develop` environment" not in instructions

            workspace = page.request.get(f"http://127.0.0.1:{bound_port}/api/workspace").json()
            assert workspace["project"] == "anna-math-library"
            assert workspace["version"] == "0.1.0 (e2e0000)"
            assert workspace["root"] == str(library)
            assert workspace["recent_libraries"] == [
                {"name": "anna-math-library", "path": str(library)}
            ]
            assert workspace["agent"]["available"] is True
            assert workspace["agent"]["environment"] == "nix develop"

            head_before_import = subprocess.run(
                ["git", "rev-parse", "--verify", "HEAD"],
                cwd=library,
                check=False,
                capture_output=True,
                text=True,
            )
            assert head_before_import.returncode != 0
            reference_content = b"Use the worked examples when planning the new book.\n"
            assert page.locator("#import-reference").is_enabled()
            with page.expect_file_chooser() as chooser:
                page.locator("#import-reference").click()
            chooser.value.set_files(
                {
                    "name": "course-outline.txt",
                    "mimeType": "text/plain",
                    "buffer": reference_content,
                }
            )
            page.wait_for_function(
                "document.getElementById('reference-title').textContent === 'Reference imported'"
            )
            assert page.locator("#reference-dialog").is_visible()
            assert page.locator("#reference-status").text_content() == (
                "The file is committed in this library. You can now mention it in prompts "
                "to the agent."
            )
            assert page.locator("#reference-path").text_content() == (
                "reference/course-outline.txt"
            )
            assert (library / "reference/course-outline.txt").read_bytes() == reference_content
            commit_after_import = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=library,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            assert len(commit_after_import) == 40
            assert subprocess.run(
                [
                    "git",
                    "diff-tree",
                    "--root",
                    "--no-commit-id",
                    "--name-only",
                    "-r",
                    "HEAD",
                ],
                cwd=library,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.splitlines() == ["reference/course-outline.txt"]
            page.mouse.move(640, 600)
            steps.verify(page, "000-reference-imported")
            page.locator("#reference-dialog .button-primary").click()

            page.wait_for_function(
                "!document.getElementById('start-agent').disabled && "
                "document.querySelector('.xterm-rows').textContent.includes('mathpub$')"
            )
            page.locator("#start-agent").click()
            try:
                page.wait_for_function(
                    "document.querySelector('.xterm-rows').textContent.includes("
                    "'Antigravity E2E ready')",
                    timeout=AGENT_START_TIMEOUT_MS,
                )
            except PlaywrightTimeoutError as error:
                terminal_text = page.locator(".xterm-rows").text_content()
                raise AssertionError(
                    f"agent did not start; terminal output was:\n{terminal_text}"
                ) from error
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

            completion_html = (
                "<h3>First-book plan ready</h3>"
                "<p>Prepared the <strong>review outline</strong> and validated its structure.</p>"
                '<p><a href="https://example.com/review">Review notes</a> '
                '<a id="unsafe-link" href="javascript:alert(1)" onclick="alert(2)">unsafe</a></p>'
                '<script>document.body.dataset.completionPwned = "yes"</script>'
                '<img src="invalid" onerror="document.body.dataset.completionPwned = \'yes\'">'
            )
            rejected_completion = page.request.post(
                f"http://127.0.0.1:{bound_port}/api/agent/completed",
                data={"html": completion_html},
            )
            assert rejected_completion.status == 403
            assert not page.locator("#completion-dialog").is_visible()
            with patch.dict(
                os.environ,
                {
                    "MATHPUB_WORKSPACE_COMPLETION_URL": (
                        f"http://127.0.0.1:{bound_port}/api/agent/completed"
                    ),
                    "MATHPUB_WORKSPACE_COMPLETION_TOKEN": server.completion_token,
                },
            ):
                delivered = notify_completion(completion_html)
            assert delivered == {
                "delivered": True,
                "summary_bytes": len(completion_html.encode("utf-8")),
            }
            completion_dialog = page.locator("#completion-dialog")
            assert completion_dialog.is_visible()
            assert page.locator("#completion-title").text_content().strip().endswith("Completed!")
            assert page.locator("#completion-summary h3").text_content() == (
                "First-book plan ready"
            )
            assert page.locator("#completion-summary strong").text_content() == "review outline"
            assert page.locator("#completion-summary script").count() == 0
            assert page.locator("#completion-summary img").count() == 0
            assert page.locator("#completion-summary a").count() == 1
            assert "unsafe" in page.locator("#completion-summary").text_content()
            assert "javascript:" not in page.locator("#completion-summary").evaluate(
                "element => element.innerHTML"
            )
            assert page.locator("body").get_attribute("data-completion-pwned") is None
            assert page.evaluate("window.__completionChimeNotes.length") == 2
            assert page.locator("#agent-status").text_content() == "Completed — review summary"
            page.mouse.move(640, 680)
            steps.verify(page, "001-agent-completed")
            page.locator("#completion-return").click()
            assert not completion_dialog.is_visible()
            assert page.locator(".xterm-helper-textarea").evaluate(
                "element => element === document.activeElement"
            )

            page.locator("#open-library").click()
            open_dialog = page.locator("#open-library-dialog")
            assert open_dialog.is_visible()
            assert page.locator("#open-library-title").text_content() == (
                "Open an authoring library"
            )
            recent = page.locator(".recent-library")
            assert recent.count() == 1
            assert recent.locator(".recent-library-name").text_content() == ("anna-math-library")
            assert recent.locator(".recent-library-path").text_content() == str(library)

            recent.locator(".recent-library-path").evaluate(
                "(element) => { element.textContent = '/authoring-libraries/anna-math-library'; }"
            )
            page.locator("#open-library-path").fill("/authoring-libraries/anna-math-library")
            page.mouse.move(640, 600)
            steps.verify(page, "001-open-recent-library")

            page.locator("#open-library-path").fill(str(existing_library))
            page.locator("#open-library-submit").click()
            page.wait_for_function(
                "document.getElementById('library-name').textContent === 'existing-library'",
                timeout=30_000,
            )
            workspace = page.request.get(f"http://127.0.0.1:{bound_port}/api/workspace").json()
            assert workspace["root"] == str(existing_library)
            assert workspace["recent_libraries"] == [
                {"name": "existing-library", "path": str(existing_library)},
                {"name": "anna-math-library", "path": str(library)},
            ]

            page.locator("#open-library").click()
            page.locator(f'.recent-library[data-path="{library}"]').click()
            page.wait_for_function(
                "document.getElementById('library-name').textContent === 'anna-math-library'",
                timeout=30_000,
            )
            assert history.most_recent().root == library
        finally:
            if browser.is_connected():
                browser.close()
            if stop_event and loop_ref:
                loop_ref[0].call_soon_threadsafe(stop_event.set)
