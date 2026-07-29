"""E2E visual & functional test scenario for the mathpub interactive GUI workspace."""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

from mathpub.config import find_project
from mathpub.gui.server import WorkspaceServer
from mathpub.publish import build
from tests.e2e.helpers.gui_step_helper import GUIStepHelper

INCREMENTAL_PREVIEW_BUDGET_MS = int(os.environ.get("MATHPUB_INCREMENTAL_PREVIEW_BUDGET_MS", "6000"))


def test_gui_workspace_e2e(tmp_path: Path, update_baselines: bool):
    if os.environ.get("HOME") == "/homeless-shelter":
        import pytest

        pytest.skip("Playwright IPC restricted in Nix build sandbox (/homeless-shelter).")

    scenario_dir = Path(__file__).parent
    screenshots_dir = scenario_dir / "screenshots"
    diffs_dir = scenario_dir / "diffs"
    screenshots_dir.mkdir(exist_ok=True)
    diffs_dir.mkdir(exist_ok=True)
    steps = GUIStepHelper(scenario_dir, update_baselines)

    # Work in an isolated authoring repository so quick-edit commits never touch the checkout.
    source_project = find_project()
    workspace_root = tmp_path / "authoring-library"
    workspace_root.mkdir()
    for filename in (".gitignore", "mathpub.toml"):
        shutil.copy2(source_project.root / filename, workspace_root / filename)
    for directory in ("components", "profiles", "publications"):
        source_directory = source_project.root / directory
        if source_directory.is_dir():
            shutil.copytree(source_directory, workspace_root / directory)
    presentation_dir = workspace_root / "publications/gui-slide-editing"
    presentation_dir.mkdir()
    presentation_source = presentation_dir / "01-editable-slide.tex"
    presentation_source.write_text(
        r"""\begin{block}{A directly editable slide}
Hover this slide to review it, then open its mapped source for a quick wording change.
\end{block}
"""
    )
    presentation_path = workspace_root / "publications/gui-slide-editing.toml"
    presentation_path.write_text(
        """schema = 1
id = "gui.slide-editing"
kind = "presentation"
title = "Presentation Editing"
profile = "mathpub.exam"
theme = "metropolis"
aspect_ratio = "169"
font = "libertinus"
projections = ["student"]

[[slides]]
id = "editable-slide"
title = "Edit This Slide"
source = "gui-slide-editing/01-editable-slide.tex"
"""
    )
    subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=workspace_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "MathPub E2E"],
        cwd=workspace_root,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "mathpub-e2e@example.invalid"],
        cwd=workspace_root,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=workspace_root, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial authoring library"],
        cwd=workspace_root,
        check=True,
        capture_output=True,
    )

    # Pre-build both document and presentation previews.
    project = find_project(workspace_root)
    pub_path = project.root / "publications/physics-practice.toml"
    watched_source = project.root / "components/questions/physics/projectiles/snowball/prompt.tex"
    build(
        project,
        presentation_path,
        root_seed="2026",
        variant="A",
        replace=True,
    )
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
        opened_pdfs = []
        server = WorkspaceServer(
            host="127.0.0.1",
            port=0,
            project_root=project.root,
            agent_command=[],
            build_version="0.1.0 (e2e0000)",
            native_preview_opener=opened_pdfs.append,
        )
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
                    if publication["path"].startswith(
                        (
                            "build/gui.slide-editing/A/",
                            "build/physics.practice/A/",
                        )
                    )
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
            assert page.locator("#app-version").text_content() == "0.1.0 (e2e0000)"
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
            assert page.locator("#pdf-preview").evaluate(
                "preview => ({width: preview.naturalWidth, height: preview.naturalHeight})"
            ) == {"width": 1632, "height": 2112}
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

            # 10. Quick-edit the mapped TeX source, commit only it, and hot-swap the preview.
            snowball_region = page.locator(
                '.synctex-region[data-component-id="physics.projectiles.snowball"]'
            )
            snowball_region.click()
            assert feedback_dialog.is_visible()
            page.locator("#feedback-edit").click()
            editor_dialog = page.locator("#editor-dialog")
            assert editor_dialog.is_visible()
            page.wait_for_function(
                "document.getElementById('editor-status').textContent === 'Source loaded'"
            )
            assert page.locator("#editor-source").text_content() == (
                "components/questions/physics/projectiles/snowball/prompt.tex"
            )
            original_content = page.locator("#editor-content").input_value()
            assert "Ignore air resistance." in original_content
            edited_content = original_content.replace(
                "Ignore air resistance.",
                "Assume air resistance is negligible.",
            )
            page.locator("#editor-content").fill(edited_content)
            assert page.locator("#editor-save").is_enabled()

            steps.verify(page, "004-quick-tex-editor")

            commit_before = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=project.root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            page.locator("#editor-save").click()
            page.wait_for_function(
                "!document.getElementById('editor-dialog').open",
                timeout=30_000,
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
            assert int(duration_match.group("duration")) <= INCREMENTAL_PREVIEW_BUDGET_MS
            page.wait_for_function("document.getElementById('pdf-preview').naturalWidth > 0")
            page.wait_for_function(
                "document.getElementById('status-synctex').textContent === 'SyncTeX Ready'"
            )
            assert page.locator("#pdf-select").input_value() == expected_pdf
            assert page.locator("#page-position").text_content() == "Page 2 of 2"
            assert "page=2" in page.locator("#pdf-preview").get_attribute("src")
            assert watched_source.read_text() == edited_content

            commit_after = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=project.root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            assert commit_after != commit_before
            assert subprocess.run(
                ["git", "show", "--format=%s", "--no-patch", "HEAD"],
                cwd=project.root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip() == (
                "Quick edit: components/questions/physics/projectiles/snowball/prompt.tex"
            )
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
                cwd=project.root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.splitlines() == [
                "components/questions/physics/projectiles/snowball/prompt.tex"
            ]
            assert (
                subprocess.run(
                    ["git", "status", "--short"],
                    cwd=project.root,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout
                == ""
            )

            steps.verify(page, "005-quick-edit-preview-updated")

            # 11. Hover a mapped Beamer slide and open the same quick editor used by documents.
            presentation_pdf = "build/gui.slide-editing/A/gui.slide-editing-A-student.pdf"
            assert page.locator(f'#pdf-select option[value="{presentation_pdf}"]').count() == 1
            page.select_option("#pdf-select", presentation_pdf)
            page.wait_for_function(
                "document.getElementById('page-position').textContent === 'Page 1 of 2'"
            )
            page.locator("#page-next").click()
            page.wait_for_function(
                "document.getElementById('page-position').textContent === 'Page 2 of 2'"
            )
            page.wait_for_function(
                "document.getElementById('status-build').textContent === 'Preview watching'",
                timeout=30_000,
            )

            slide_response = page.request.get(
                f"http://127.0.0.1:{bound_port}/api/synctex/boxes"
                "?publication_id=gui.slide-editing"
                "&variant=A"
                "&projection=student"
                "&page=2"
            )
            assert slide_response.ok
            slide_boxes = slide_response.json()["boxes"]
            assert [(box["component_id"], box["fragment"]) for box in slide_boxes] == [
                ("editable-slide", "slide")
            ]
            page.wait_for_function("document.querySelectorAll('.synctex-region').length === 1")
            slide_region = page.locator('.synctex-region[data-component-id="editable-slide"]')
            slide_region.hover()
            assert (
                slide_region.locator(".synctex-region-label").evaluate(
                    "element => getComputedStyle(element).opacity"
                )
                == "1"
            )
            slide_region.click()
            assert feedback_dialog.is_visible()
            assert page.locator("#feedback-component").text_content() == "editable-slide"
            assert page.locator("#feedback-fragment").text_content() == "slide"
            assert page.locator("#feedback-source").text_content() == (
                "publications/gui-slide-editing/01-editable-slide.tex"
            )
            page.locator("#feedback-edit").click()
            page.wait_for_function(
                "document.getElementById('editor-status').textContent === 'Source loaded'"
            )
            assert editor_dialog.is_visible()
            slide_original = page.locator("#editor-content").input_value()
            slide_edited = slide_original.replace(
                "quick wording change",
                "small wording change",
            )
            page.locator("#editor-content").fill(slide_edited)
            slide_preview_before = page.locator("#pdf-preview").get_attribute("src")

            steps.verify(page, "006-presentation-slide-editor")

            slide_commit_before = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=project.root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            page.locator("#editor-save").click()
            page.wait_for_function(
                "document.getElementById('status-build').textContent === 'Rebuilding preview…'",
                timeout=30_000,
            )
            page.wait_for_function(
                "document.getElementById('status-build').textContent === 'Preview updated'",
                timeout=90_000,
            )
            assert "format: none" in page.locator("#status-build").get_attribute("title")
            slide_preview_after = page.locator("#pdf-preview").get_attribute("src")
            assert slide_preview_after != slide_preview_before
            assert page.locator("#pdf-preview").evaluate(
                "element => element.complete && element.naturalWidth > 0"
            )
            page.wait_for_function(
                "document.getElementById('status-synctex').textContent === 'SyncTeX Ready'"
            )
            assert page.locator("#pdf-select").input_value() == presentation_pdf
            assert page.locator("#page-position").text_content() == "Page 2 of 2"
            assert presentation_source.read_text() == slide_edited
            slide_commit_after = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=project.root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            assert slide_commit_after != slide_commit_before
            assert subprocess.run(
                ["git", "show", "--format=%s", "--no-patch", "HEAD"],
                cwd=project.root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip() == ("Quick edit: publications/gui-slide-editing/01-editable-slide.tex")
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
                cwd=project.root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.splitlines() == ["publications/gui-slide-editing/01-editable-slide.tex"]

            steps.verify(page, "007-presentation-slide-updated")

            # 12. Open the selected built PDF in the native viewer.
            page.locator("#open-native-preview").click()
            page.wait_for_function(
                "document.getElementById('status-build').textContent === 'Opened in Preview'"
            )
            assert opened_pdfs == [(project.root / presentation_pdf).resolve()]

            # 13. Generate Walkthrough README.md
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
                "## Quick TeX Editor\n\n"
                "![Quick TeX Editor](./screenshots/004-quick-tex-editor.png)\n\n"
                "## Quick Edit Committed and Preview Updated\n\n"
                "![Quick Edit Preview](./screenshots/005-quick-edit-preview-updated.png)\n\n"
                "## Presentation Slide Quick Editor\n\n"
                "![Presentation Slide Editor]"
                "(./screenshots/006-presentation-slide-editor.png)\n\n"
                "## Presentation Slide Committed and Rebuilt\n\n"
                "![Updated Presentation Slide]"
                "(./screenshots/007-presentation-slide-updated.png)\n\n"
                "**Verifications:**\n"
                "- [x] Header brand and subtitle render correctly\n"
                "- [x] The package version and build Git revision are visible\n"
                "- [x] Isolated PTY terminal emulator loads with clean prompt\n"
                "- [x] PDF dropdown loads and displays the rendered first page\n"
                "- [x] Hovering reveals one clickable mapped region without a prior toggle\n"
                "- [x] Mapped component regions align with their rendered PDF content\n"
                "- [x] Clicking a mapped region opens source-aware feedback controls\n"
                "- [x] Feedback is inserted into the PTY for review without being executed\n"
                "- [x] Multipage navigation loads page-specific PDF content and mappings\n"
                "- [x] A mapped TeX source can be edited directly in the GUI\n"
                "- [x] Saving commits only that source file in Git\n"
                "- [x] The committed edit reuses instances and hot-swaps the active page "
                "within budget\n"
                "- [x] A Beamer slide exposes a hoverable source-mapped region\n"
                "- [x] Presentation feedback identifies the authored slide fragment\n"
                "- [x] A quick slide edit commits only its TeX source and rebuilds the preview\n"
                "- [x] The selected built PDF can be opened in the native viewer\n"
            )
            readme_path.write_text(readme_content)

        finally:
            if browser.is_connected():
                browser.close()
            if stop_event and loop_ref:
                loop_ref[0].call_soon_threadsafe(stop_event.set)
