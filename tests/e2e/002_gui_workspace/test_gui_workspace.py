"""E2E visual & functional test scenario for the mathpub interactive GUI workspace."""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

from mathpub.config import find_project
from mathpub.gui.server import WorkspaceServer
from mathpub.publish import build
from tests.e2e.helpers.gui_step_helper import GUIStepHelper


def test_gui_workspace_e2e(update_baselines: bool):
    if os.environ.get("HOME") == "/homeless-shelter":
        import pytest

        pytest.skip("Playwright IPC restricted in Nix build sandbox (/homeless-shelter).")

    scenario_dir = Path(__file__).parent
    screenshots_dir = scenario_dir / "screenshots"
    diffs_dir = scenario_dir / "diffs"
    screenshots_dir.mkdir(exist_ok=True)
    diffs_dir.mkdir(exist_ok=True)
    steps = GUIStepHelper(scenario_dir, update_baselines)

    # Pre-build physics practice PDF so the right pane renders its first page.
    project = find_project()
    pub_path = project.root / "publications/physics-practice.toml"
    watched_source = project.root / "components/questions/physics/energy/ramp-speed/prompt.tex"
    original_source_times = None
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
            expected_pdf = "build/physics.practice/A/physics.practice-A-student.pdf"
            stale_pdf = "build/stale/B/stale-B-student.pdf"

            def add_stale_publication(route):
                response = route.fetch()
                payload = response.json()
                payload["publications"] = [
                    publication
                    for publication in payload["publications"]
                    if publication["path"].startswith("build/physics.practice/A/")
                ]
                payload["publications"].append(
                    {
                        "name": "stale-B-student.pdf",
                        "path": stale_pdf,
                        "publication_id": "stale",
                        "variant": "B",
                        "projection": "student",
                        "synctex_ready": False,
                        "mapping_error": "Missing SyncTeX data",
                        "mapping_rebuild_command": (
                            "nix run '.#mathpub' -- build publications/stale.toml "
                            "--seed 2026 --variant B --replace --json"
                        ),
                    }
                )
                route.fulfill(
                    response=response,
                    body=json.dumps(payload),
                    headers={**response.headers, "content-type": "application/json"},
                )

            page.route("**/api/publications", add_stale_publication)
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
            assert page.locator(f'#pdf-select option[value="{expected_pdf}"]').count() == 1
            assert page.locator("#pdf-select").input_value() == expected_pdf
            stale_option = page.locator(f'#pdf-select option[value="{stale_pdf}"]')
            assert stale_option.text_content().endswith("(rebuild for mappings)")
            page.select_option("#pdf-select", stale_pdf)
            assert page.locator("#status-build").text_content() == ("Preview watch unavailable")
            assert page.locator("#mapped-regions-toggle").is_disabled()
            assert page.locator("#mapped-regions-toggle").text_content() == (
                "Mappings need rebuild"
            )
            assert page.locator("#status-synctex").text_content() == ("Rebuild PDF for mappings")
            assert "nix run '.#mathpub'" in page.locator("#mapped-regions-toggle").get_attribute(
                "title"
            )
            page.select_option("#pdf-select", expected_pdf)
            page.wait_for_function("document.getElementById('pdf-preview').naturalWidth > 0")
            page.wait_for_function(
                "document.getElementById('status-build').textContent === 'Preview watching'"
            )
            assert page.locator("#pdf-preview").is_visible()
            assert page.locator("#page-position").text_content() == "Page 1 of 2"
            assert page.locator("#page-previous").is_disabled()
            assert page.locator("#page-next").is_enabled()

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
            page.wait_for_function(
                f"document.querySelectorAll('.synctex-region').length === "
                f"{len(boxes_payload['boxes'])}"
            )

            # 4. Capture & Verify Baseline Screenshot (Strict 0-Pixel Tolerance via WebKit)
            steps.verify(page, "000-initial-workspace-load")

            # 5. Hover and click a mapped region without first revealing every region.
            toggle = page.locator("#mapped-regions-toggle")
            assert toggle.is_enabled()
            assert toggle.get_attribute("aria-pressed") == "false"
            assert page.locator(".synctex-region").count() == len(boxes_payload["boxes"])
            assert all(
                label.evaluate("element => getComputedStyle(element).opacity") == "0"
                for label in page.locator(".synctex-region-label").all()
            )
            ramp_region = page.locator(
                '.synctex-region[data-component-id="physics.energy.ramp-speed"]'
            )
            ramp_region.hover()
            assert (
                ramp_region.locator(".synctex-region-label").evaluate(
                    "element => getComputedStyle(element).opacity"
                )
                == "1"
            )

            steps.verify(page, "001-hovered-region-visible")

            ramp_region.click()
            feedback_dialog = page.locator("#feedback-dialog")
            assert feedback_dialog.is_visible()
            assert page.locator("#feedback-component").text_content() == (
                "physics.energy.ramp-speed"
            )
            page.locator("#feedback-close").click()
            assert not feedback_dialog.is_visible()

            # 6. Reveal every mapped region and verify its rendered PDF geometry.
            toggle.click()
            assert toggle.get_attribute("aria-pressed") == "true"
            assert toggle.text_content() == "Hide mapped regions"
            assert page.locator("#status-synctex").text_content() == (
                f"{len(boxes_payload['boxes'])} regions mapped"
            )

            preview_metrics = page.locator("#pdf-preview").evaluate(
                """preview => {
                  const scale = Math.min(
                    preview.clientWidth / preview.naturalWidth,
                    preview.clientHeight / preview.naturalHeight
                  );
                  const width = preview.naturalWidth * scale;
                  const height = preview.naturalHeight * scale;
                  return {
                    left: (preview.clientWidth - width) / 2,
                    top: 0,
                    width,
                    height
                  };
                }"""
            )
            rendered_regions = {
                region.get_attribute("data-component-id"): region.evaluate(
                    """element => ({
                      x: Number(element.getAttribute('x')),
                      y: Number(element.getAttribute('y')),
                      width: Number(element.getAttribute('width')),
                      height: Number(element.getAttribute('height'))
                    })"""
                )
                for region in page.locator(".synctex-region-box").all()
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
                expected_left = math.floor(expected["x"] + 0.5)
                expected_top = math.floor(expected["y"] + 0.5)
                expected_right = math.floor(expected["x"] + expected["width"] + 0.5)
                expected_bottom = math.floor(expected["y"] + expected["height"] + 0.5)
                assert region == {
                    "x": expected_left,
                    "y": expected_top,
                    "width": expected_right - expected_left,
                    "height": expected_bottom - expected_top,
                }

            steps.verify(page, "001-mapped-regions-visible")

            # 7. Verify the mapped region's source-aware feedback modal.
            assert ramp_region.get_attribute("role") == "button"
            assert ramp_region.get_attribute("tabindex") == "0"
            ramp_region.click()
            feedback_dialog = page.locator("#feedback-dialog")
            assert feedback_dialog.is_visible()
            assert page.locator("#feedback-component").text_content() == (
                "physics.energy.ramp-speed"
            )
            assert page.locator("#feedback-fragment").text_content() == "prompt"
            assert page.locator("#feedback-source").text_content() == (
                "components/questions/physics/energy/ramp-speed/prompt.tex"
            )
            page.locator("#feedback-close").click()
            assert not feedback_dialog.is_visible()
            ramp_region.focus()
            page.keyboard.press("Enter")
            assert feedback_dialog.is_visible()
            assert page.locator("#feedback-text").evaluate(
                "element => element === document.activeElement"
            )

            steps.verify(page, "002-element-feedback-dialog")

            # 8. Insert structured feedback into the active terminal without executing it.
            feedback = "Make the ramp diagram labels larger and clarify why energy is conserved."
            page.locator("#feedback-text").fill(feedback)
            page.locator("#feedback-send").click()
            assert not feedback_dialog.is_visible()
            injected_prefix = "Review mathpub component physics.energy.ramp-speed"
            page.wait_for_function(
                """prefix => document.querySelector('.xterm-rows').textContent.includes(prefix)""",
                arg=injected_prefix,
            )
            terminal_text = page.locator(".xterm-rows").text_content()
            assert injected_prefix in terminal_text
            assert "command not found" not in terminal_text
            assert page.locator("#status-synctex").text_content() == "Feedback inserted"

            steps.verify(page, "003-feedback-inserted-in-terminal")

            # 9. Navigate to page two and verify page-specific content and mappings.
            page.locator("#page-next").click()
            page.wait_for_function(
                "document.getElementById('page-position').textContent === 'Page 2 of 2'"
            )
            page.wait_for_function(
                "document.getElementById('status-synctex').textContent === 'SyncTeX Ready'"
            )
            assert page.locator("#page-previous").is_enabled()
            assert page.locator("#page-next").is_disabled()
            assert "page=2" in page.locator("#pdf-preview").get_attribute("src")
            second_page_response = page.request.get(
                f"http://127.0.0.1:{bound_port}/api/synctex/boxes"
                "?publication_id=physics.practice"
                "&variant=A"
                "&projection=student"
                "&page=2"
            )
            assert second_page_response.ok
            second_page_boxes = second_page_response.json()["boxes"]
            assert {(box["component_id"], box["fragment"]) for box in second_page_boxes} >= {
                ("physics.projectiles.snowball", "prompt")
            }
            page.wait_for_function(
                f"document.querySelectorAll('.synctex-region').length === {len(second_page_boxes)}"
            )

            steps.verify(page, "003-page-two")

            # 10. Touch an authored component and verify a bounded, page-preserving hot-swap.
            source_stat = watched_source.stat()
            original_source_times = (source_stat.st_atime_ns, source_stat.st_mtime_ns)
            os.utime(
                watched_source,
                ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns + 1_000_000_000),
            )
            page.wait_for_function(
                "document.getElementById('status-build').textContent === 'Rebuilding preview…'",
                timeout=30_000,
            )
            page.wait_for_function(
                "document.getElementById('status-build').textContent === 'Preview updated'",
                timeout=90_000,
            )
            build_details = page.locator("#status-build").get_attribute("title")
            assert "3 instances reused" in build_details
            assert "mathpub.fmt" in build_details
            duration_match = re.match(r"(?P<duration>\d+) ms;", build_details)
            assert duration_match is not None
            assert int(duration_match.group("duration")) <= 3500
            page.wait_for_function("document.getElementById('pdf-preview').naturalWidth > 0")
            page.wait_for_function(
                "document.getElementById('status-synctex').textContent === 'SyncTeX Ready'"
            )
            assert page.locator("#pdf-select").input_value() == expected_pdf
            assert page.locator("#page-position").text_content() == "Page 2 of 2"
            assert "page=2" in page.locator("#pdf-preview").get_attribute("src")

            steps.verify(page, "004-incremental-preview-updated")

            # 10. Generate Walkthrough README.md
            readme_path = scenario_dir / "README.md"
            readme_content = (
                "# E2E Visual Verification: Interactive GUI Workspace\n\n"
                "Auto-generated visual walkthrough for `tests/e2e/002_gui_workspace`:\n\n"
                "The committed images below are exact Playwright WebKit renderer baselines. "
                "On Linux,\n"
                "`nix run .#mathpub-gui-e2e` separately launches the packaged Tauri "
                "application through\n"
                "`tauri-driver`, verifies the PTY and PDF preview, and writes a native "
                "screenshot artifact to\n"
                "`build/e2e/tauri-driver.png`.\n\n"
                "## Initial Workspace Load (WebKit / Safari Engine)\n\n"
                "![Initial Workspace Load](./screenshots/000-initial-workspace-load.png)\n\n"
                "## Hovered SyncTeX Region\n\n"
                "![Hovered Region](./screenshots/001-hovered-region-visible.png)\n\n"
                "## SyncTeX Mapped Regions\n\n"
                "![Mapped Regions](./screenshots/001-mapped-regions-visible.png)\n\n"
                "## Element Feedback Dialog\n\n"
                "![Element Feedback Dialog](./screenshots/002-element-feedback-dialog.png)\n\n"
                "## Feedback Inserted into the Active Terminal\n\n"
                "![Feedback Inserted](./screenshots/003-feedback-inserted-in-terminal.png)\n\n"
                "## Page Two with Page-Specific SyncTeX Mappings\n\n"
                "![Page Two](./screenshots/003-page-two.png)\n\n"
                "## Incremental Preview Updated\n\n"
                "![Incremental Preview](./screenshots/004-incremental-preview-updated.png)\n\n"
                "**Verifications:**\n"
                "- [x] Header brand and subtitle render correctly\n"
                "- [x] Isolated PTY terminal emulator loads with clean prompt\n"
                "- [x] PDF dropdown loads and displays the rendered first page\n"
                "- [x] Hovering reveals one clickable mapped region without a prior toggle\n"
                "- [x] Mapped component regions align with their rendered PDF content\n"
                "- [x] Clicking a mapped region opens source-aware feedback controls\n"
                "- [x] Feedback is inserted into the PTY for review without being executed\n"
                "- [x] Multipage navigation loads page-specific PDF content and mappings\n"
                "- [x] Authored changes reuse instances and hot-swap the active page "
                "within budget\n"
            )
            readme_path.write_text(readme_content)

        finally:
            if browser.is_connected():
                browser.close()
            if original_source_times is not None:
                os.utime(watched_source, ns=original_source_times)
            if stop_event and loop_ref:
                loop_ref[0].call_soon_threadsafe(stop_event.set)
