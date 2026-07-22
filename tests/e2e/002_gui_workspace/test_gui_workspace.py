"""E2E visual & functional test scenario for the mathpub interactive GUI workspace."""

from __future__ import annotations

import asyncio
import os
import threading
from pathlib import Path

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

from mathpub.gui.server import WorkspaceServer


def test_gui_workspace_e2e(update_baselines: bool):
    if os.environ.get("HOME") == "/homeless-shelter" or os.environ.get("NIX_BUILD_TOP"):
        import pytest

        pytest.skip("Playwright IPC restricted in Nix build sandbox (/homeless-shelter).")

    scenario_dir = Path(__file__).parent
    screenshots_dir = scenario_dir / "screenshots"
    diffs_dir = scenario_dir / "diffs"
    screenshots_dir.mkdir(exist_ok=True)
    diffs_dir.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--font-render-hinting=none",
            ],
        )

        bound_port = 0
        server = WorkspaceServer(host="127.0.0.1", port=0)
        server_ready = threading.Event()
        stop_event = None
        loop_ref = []

        def thread_main():
            nonlocal stop_event, bound_port
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop_ref.append(loop)
            stop_event = asyncio.Event()

            async def run_server():
                nonlocal bound_port
                srv = await asyncio.start_server(server.handle_client, "127.0.0.1", 0)
                for sock in srv.sockets:
                    os.set_inheritable(sock.fileno(), False)
                bound_port = srv.sockets[0].getsockname()[1]
                async with srv:
                    server_ready.set()
                    await stop_event.wait()

            loop.run_until_complete(run_server())

        t = threading.Thread(target=thread_main, daemon=True)
        t.start()

        assert server_ready.wait(timeout=5.0)

        try:
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.goto(f"http://127.0.0.1:{bound_port}/", wait_until="domcontentloaded")

            # 1. Verify Header Elements
            assert page.locator(".logo").text_content() == "mathpub"
            assert "Interactive Workspace" in page.locator(".subtitle").text_content()

            # 2. Verify Left Terminal Pane & xterm Container
            assert page.locator("#pane-left").is_visible()
            assert page.locator("#terminal-container").is_visible()
            assert page.locator(".xterm").is_visible()

            # 3. Verify Right PDF Viewer Pane
            assert page.locator("#pane-right").is_visible()
            assert page.locator(".pdf-viewer-wrapper").is_visible()
            page.wait_for_selector(".xterm-rows")

            # 4. Capture & Verify Baseline Screenshot (Strict 0-Pixel Tolerance)
            baseline_path = screenshots_dir / "000-initial-workspace-load.png"
            candidate_path = scenario_dir / "temp-candidate.png"
            page.screenshot(path=str(candidate_path))

            if update_baselines or not baseline_path.exists():
                candidate_path.replace(baseline_path)
            else:
                img_cand = Image.open(candidate_path).convert("RGB")
                img_base = Image.open(baseline_path).convert("RGB")
                candidate_path.unlink()

                diff = ImageChops.difference(img_cand, img_base)
                if diff.getbbox() is not None:
                    diff.save(diffs_dir / "000-initial-workspace-load-diff.png")
                    raise AssertionError(
                        "Visual regression in GUI workspace layout (0-pixel tolerance violated)!\n"
                        f"Candidate: {candidate_path}\n"
                        f"Baseline: {baseline_path}"
                    )

            # 5. Generate Walkthrough README.md
            readme_path = scenario_dir / "README.md"
            readme_content = (
                "# E2E Visual Verification: Interactive GUI Workspace\n\n"
                "Auto-generated visual walkthrough for `tests/e2e/002_gui_workspace`:\n\n"
                "## Initial Workspace Load\n\n"
                "![Initial Workspace Load](./screenshots/000-initial-workspace-load.png)\n\n"
                "**Verifications:**\n"
                "- [x] Header brand and subtitle render correctly\n"
                "- [x] Terminal PTY pane loads xterm.js canvas\n"
                "- [x] PDF viewer pane renders with split-pane layout\n"
            )
            readme_path.write_text(readme_content)

            browser.close()
        finally:
            if stop_event and loop_ref:
                loop_ref[0].call_soon_threadsafe(stop_event.set)
