"""E2E visual & functional test scenario for the mathpub interactive GUI workspace."""

from __future__ import annotations

import asyncio
import os
import sys
import threading
from pathlib import Path

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

from mathpub.config import find_project
from mathpub.gui.server import WorkspaceServer
from mathpub.publish import build


def _verify_screenshot(page, scenario_dir, screenshots_dir, diffs_dir, name, update):
    baseline_path = screenshots_dir / f"{name}.png"
    candidate_path = scenario_dir / f"temp-{name}.png"
    page.screenshot(path=str(candidate_path))

    if update or not baseline_path.exists():
        candidate_path.replace(baseline_path)
        return

    img_cand = Image.open(candidate_path).convert("RGB")
    img_base = Image.open(baseline_path).convert("RGB")
    diff = ImageChops.difference(img_cand, img_base)
    candidate_path.unlink()
    if diff.getbbox() is not None:
        diff.save(diffs_dir / f"{name}-diff.png")
        raise AssertionError(
            f"Visual regression in WebKit GUI workspace layout!\nBaseline: {baseline_path}"
        )


def test_gui_workspace_e2e(update_baselines: bool):
    if os.environ.get("HOME") == "/homeless-shelter":
        import pytest

        pytest.skip("Playwright IPC restricted in Nix build sandbox (/homeless-shelter).")

    scenario_dir = Path(__file__).parent
    screenshots_dir = scenario_dir / "screenshots"
    diffs_dir = scenario_dir / "diffs"
    screenshots_dir.mkdir(exist_ok=True)
    diffs_dir.mkdir(exist_ok=True)

    # Pre-build physics practice PDF so the right pane renders its first page.
    project = find_project()
    pub_path = project.root / "publications/physics-practice.toml"
    if pub_path.exists():
        build(project, pub_path, root_seed="2026", variant="A", replace=True)

    with sync_playwright() as p:
        if sys.platform == "darwin":
            browser = p.webkit.launch(headless=True)
        else:
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

            # 3. Verify Right PDF Viewer Pane & Option Dropdown
            assert page.locator("#pane-right").is_visible()
            assert page.locator(".pdf-viewer-wrapper").is_visible()

            # Wait for PTY shell prompt to finish rendering in xterm canvas
            wait_js = (
                "document.querySelector('.xterm-rows') && "
                "document.querySelector('.xterm-rows').textContent.includes('mathpub$')"
            )
            page.wait_for_function(wait_js)

            # Wait for PDF select dropdown to populate from /api/publications
            page.wait_for_function("document.getElementById('pdf-select').options.length > 1")
            expected_pdf = "build/physics.practice/A/physics.practice-A-student.pdf"
            assert page.locator(f'#pdf-select option[value="{expected_pdf}"]').count() == 1
            page.select_option("#pdf-select", expected_pdf)
            page.wait_for_function("document.getElementById('pdf-preview').naturalWidth > 0")
            assert page.locator("#pdf-preview").is_visible()

            boxes_response = page.request.get(
                f"http://127.0.0.1:{bound_port}/api/synctex/boxes"
                "?publication_id=physics.practice"
                "&variant=A"
                "&projection=student"
                "&page=1"
            )
            assert boxes_response.ok
            boxes_payload = boxes_response.json()
            assert boxes_payload["page_size"] == {
                "width": 612.0,
                "height": 792.0,
                "unit": "pt",
            }
            assert {(box["component_id"], box["fragment"]) for box in boxes_payload["boxes"]} >= {
                ("physics.energy.ramp-speed", "prompt"),
                ("physics.forces.car-curve", "prompt"),
            }
            page_width = boxes_payload["page_size"]["width"]
            page_height = boxes_payload["page_size"]["height"]
            assert all(
                box["w"] > 0
                and box["h"] > 0
                and 0 <= box["x"] < box["x"] + box["w"] <= page_width
                and 0 <= box["y"] < box["y"] + box["h"] <= page_height
                for box in boxes_payload["boxes"]
            )

            # 4. Capture & Verify Baseline Screenshot (Strict 0-Pixel Tolerance via WebKit)
            _verify_screenshot(
                page,
                scenario_dir,
                screenshots_dir,
                diffs_dir,
                "000-initial-workspace-load",
                update_baselines,
            )

            # 5. Display mapped regions and verify their rendered PDF geometry.
            toggle = page.locator("#mapped-regions-toggle")
            assert toggle.is_enabled()
            assert toggle.get_attribute("aria-pressed") == "false"
            assert page.locator(".synctex-region").count() == 0
            toggle.click()
            page.wait_for_function(
                f"document.querySelectorAll('.synctex-region').length === "
                f"{len(boxes_payload['boxes'])}"
            )
            assert toggle.get_attribute("aria-pressed") == "true"
            assert toggle.text_content() == "Hide mapped regions"
            assert page.locator("#status-synctex").text_content() == (
                f"{len(boxes_payload['boxes'])} regions mapped"
            )

            preview_metrics = page.locator("#pdf-preview").evaluate(
                """preview => {
                  const rect = preview.getBoundingClientRect();
                  const scale = Math.min(
                    preview.clientWidth / preview.naturalWidth,
                    preview.clientHeight / preview.naturalHeight
                  );
                  const width = preview.naturalWidth * scale;
                  const height = preview.naturalHeight * scale;
                  return {
                    left: rect.left + (preview.clientWidth - width) / 2,
                    top: rect.top,
                    width,
                    height
                  };
                }"""
            )
            rendered_regions = {
                region.get_attribute("data-component-id"): region.bounding_box()
                for region in page.locator(".synctex-region").all()
            }
            for box in boxes_payload["boxes"]:
                region = rendered_regions[box["component_id"]]
                expected = {
                    "x": preview_metrics["left"] + box["x"] / page_width * preview_metrics["width"],
                    "y": preview_metrics["top"]
                    + box["y"] / page_height * preview_metrics["height"],
                    "width": box["w"] / page_width * preview_metrics["width"],
                    "height": box["h"] / page_height * preview_metrics["height"],
                }
                assert all(abs(region[key] - value) < 0.75 for key, value in expected.items())

            _verify_screenshot(
                page,
                scenario_dir,
                screenshots_dir,
                diffs_dir,
                "001-mapped-regions-visible",
                update_baselines,
            )

            # 6. Generate Walkthrough README.md
            readme_path = scenario_dir / "README.md"
            readme_content = (
                "# E2E Visual Verification: Interactive GUI Workspace\n\n"
                "Auto-generated visual walkthrough for `tests/e2e/002_gui_workspace`:\n\n"
                "## Initial Workspace Load (WebKit / Safari Engine)\n\n"
                "![Initial Workspace Load](./screenshots/000-initial-workspace-load.png)\n\n"
                "## SyncTeX Mapped Regions\n\n"
                "![Mapped Regions](./screenshots/001-mapped-regions-visible.png)\n\n"
                "**Verifications:**\n"
                "- [x] Header brand and subtitle render correctly\n"
                "- [x] Isolated PTY terminal emulator loads with clean prompt\n"
                "- [x] PDF dropdown loads and displays the rendered first page\n"
                "- [x] Mapped component regions align with their rendered PDF content\n"
            )
            readme_path.write_text(readme_content)

            browser.close()
        finally:
            if stop_event and loop_ref:
                loop_ref[0].call_soon_threadsafe(stop_event.set)
