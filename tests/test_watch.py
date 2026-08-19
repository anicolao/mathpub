"""Tests for automatic incremental workspace regeneration."""

from __future__ import annotations

import asyncio
import json
import subprocess
import threading

import pytest
from pypdf import PdfWriter

from mathpub.config import find_project
from mathpub.errors import MathpubError
from mathpub.gui.watch import (
    IncrementalPreviewWatcher,
    _build_in_authoring_environment,
    _changed_page_numbers,
    _pdf_page_fingerprints,
    _review_prompt,
    _selection,
)
from mathpub.scaffold import init_project


def test_preview_selection_rejects_unsafe_values(tmp_path):
    root = tmp_path / "project"
    init_project(root)
    project = find_project(root)
    publication = root / "publications/demo.toml"
    publication.write_text("fixture")
    valid = {
        "publication_path": "publications/demo.toml",
        "root_seed": "2026",
        "variant": "A",
        "projection": "student",
        "font_family": "libertinus",
        "page": 2,
        "lesson_ids": ["lesson-one"],
    }
    selected = _selection(project, valid)
    assert selected is not None
    assert selected.page == 2
    assert selected.lesson_ids == ("lesson-one",)
    assert _selection(project, {**valid, "variant": "../outside"}) is None
    assert _selection(project, {**valid, "publication_path": "../outside.toml"}) is None
    assert _selection(project, {**valid, "page": 0}) is None
    assert _selection(project, {**valid, "page": "2"}) is None
    assert _selection(project, {**valid, "lesson_ids": ["../outside"]}) is None
    assert _selection(project, {**valid, "path": "../outside.pdf"}) is None


def test_changed_pages_include_visual_differences_and_new_page_boundary():
    assert _changed_page_numbers(("same", "old", "removed"), ("same", "new")) == (2,)
    assert _changed_page_numbers(("same",), ("same", "added")) == (2,)
    assert _changed_page_numbers(("same",), ("same",)) == ()


def test_pdf_page_fingerprints_are_stable_for_unchanged_pages(tmp_path):
    pdf = tmp_path / "fixture.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_blank_page(width=612, height=792)
    with pdf.open("wb") as output:
        writer.write(output)

    first = _pdf_page_fingerprints(pdf)

    assert len(first) == 2
    assert first == _pdf_page_fingerprints(pdf)


def test_review_prompt_requires_visual_content_and_diagram_checks():
    prompt = _review_prompt(
        ["build/demo/A/review-pages/demo-A-student-page-002.png"],
        page_count_changed=True,
    )

    assert "use your image-viewing tool" in prompt
    assert "demo-A-student-page-002.png" in prompt
    assert "page count also changed" in prompt
    assert "nothing is clipped, overlapping, or overcrowded" in prompt
    assert "diagram is clear, legible, and mathematically consistent" in prompt


def test_preview_watcher_rebuilds_after_authored_change(tmp_path):
    root = tmp_path / "project"
    init_project(root)
    project = find_project(root)
    publication = root / "publications/demo.toml"
    publication.write_text(
        """schema = 1
id = "demo"
kind = "worksheet"
title = "Demo"
profile = "mathpub.exam"
projections = ["student"]
[[sections]]
title = "Demo"
[[sections.questions]]
id = "demo.question"
"""
    )
    watched = root / "components/watched.tex"
    watched.parent.mkdir(exist_ok=True)
    watched.write_text("before")
    events = []
    calls = []

    def fake_format_dumper(*args, **kwargs):
        calls.append(("format", kwargs))
        return {"format": "build/.mathpub-formats/test/mathpub.fmt"}

    def fake_builder(*args, **kwargs):
        calls.append(("build", kwargs))
        return {
            "edition": "build/demo/A",
            "outputs": [{"projection": "student", "path": "demo-A-student.pdf"}],
            "instance_cache": {"questions_reused": 1},
            "latex_format": "build/.mathpub-formats/test/mathpub.fmt",
        }

    async def exercise():
        async def send_event(event):
            events.append(event)

        watcher = IncrementalPreviewWatcher(
            project,
            send_event,
            poll_interval=0.01,
            builder=fake_builder,
            format_dumper=fake_format_dumper,
        )
        selected = await watcher.select(
            {
                "publication_path": "publications/demo.toml",
                "root_seed": "2026",
                "variant": "A",
                "projection": "student",
                "font_family": "libertinus",
                "page": 2,
                "lesson_ids": ["lesson-one"],
            }
        )
        assert selected is not None
        watched.write_text("after")
        for _ in range(100):
            if any(event["type"] == "preview-built" for event in events):
                break
            await asyncio.sleep(0.01)
        await watcher.close()

    asyncio.run(exercise())
    assert [event["type"] for event in events] == [
        "preview-build-started",
        "preview-built",
    ]
    assert [name for name, _ in calls] == ["format", "build"]
    assert events[-1]["page"] == 2
    build_call = calls[1][1]
    assert build_call["incremental"] is True
    assert build_call["projections"] == ["student"]
    assert build_call["lesson_ids"] == ["lesson-one"]


def test_preview_watcher_builds_in_library_development_environment(tmp_path, monkeypatch):
    root = tmp_path / "project"
    init_project(root)
    project = find_project(root)
    publication = root / "publications/demo.toml"
    publication.write_text(
        """schema = 1
id = "demo"
kind = "worksheet"
title = "Demo"
profile = "mathpub.exam"
projections = ["student"]
[[sections]]
title = "Demo"
questions = []
"""
    )
    commands = []

    def fake_run(command, **kwargs):
        commands.append((command, kwargs))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "schema": 1,
                    "status": "ok",
                    "command": "build",
                    "data": {
                        "edition": "build/demo/A",
                        "outputs": [{"projection": "student", "path": "demo-A-student.pdf"}],
                        "instance_cache": {"components_reused": 1},
                        "latex_format": None,
                    },
                }
            ),
            stderr="",
        )

    monkeypatch.setattr("mathpub.gui.watch.shutil.which", lambda command: f"/nix/bin/{command}")
    monkeypatch.setattr("mathpub.gui.watch.subprocess.run", fake_run)
    watcher = IncrementalPreviewWatcher(
        project,
        lambda _event: None,
        format_dumper=lambda *_args, **_kwargs: {"format": None},
    )
    selected = _selection(
        project,
        {
            "publication_path": "publications/demo.toml",
            "root_seed": "2026",
            "variant": "A",
            "projection": "student",
            "font_family": "libertinus",
            "page": 1,
            "lesson_ids": ["lesson-one"],
        },
    )

    assert selected is not None
    result = watcher._build(selected)

    assert result["edition"] == "build/demo/A"
    assert len(commands) == 1
    command, kwargs = commands[0]
    assert command == [
        "/nix/bin/nix",
        "develop",
        "--no-write-lock-file",
        "--no-warn-dirty",
        "--quiet",
        "--command",
        "mathpub",
        "build",
        "publications/demo.toml",
        "--seed",
        "2026",
        "--variant",
        "A",
        "--projection",
        "student",
        "--font",
        "libertinus",
        "--replace",
        "--json",
        "--lesson",
        "lesson-one",
    ]
    assert kwargs == {
        "cwd": project.root,
        "capture_output": True,
        "text": True,
        "check": False,
    }


def test_library_environment_build_preserves_mathpub_error(tmp_path, monkeypatch):
    root = tmp_path / "project"
    init_project(root)
    project = find_project(root)
    publication = root / "publications/demo.toml"
    publication.write_text("fixture")
    selected = _selection(
        project,
        {
            "publication_path": "publications/demo.toml",
            "root_seed": "2026",
            "variant": "A",
            "projection": "student",
            "font_family": "libertinus",
            "page": 1,
        },
    )
    payload = {
        "schema": 1,
        "status": "error",
        "error": {
            "code": "MP-GEN-001",
            "message": "Sage runner failed: qrencode was not found",
            "details": {"question_id": "demo.question"},
        },
    }
    monkeypatch.setattr("mathpub.gui.watch.shutil.which", lambda _command: "/nix/bin/nix")
    monkeypatch.setattr(
        "mathpub.gui.watch.subprocess.run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command, 1, stdout=json.dumps(payload), stderr=""
        ),
    )

    assert selected is not None
    with pytest.raises(MathpubError, match="qrencode was not found") as raised:
        _build_in_authoring_environment(project, selected)

    assert raised.value.code == "MP-GEN-001"
    assert raised.value.details == {"question_id": "demo.question"}


def test_preview_watcher_renders_changed_pages_and_prompts_agent(tmp_path):
    root = tmp_path / "project"
    init_project(root)
    project = find_project(root)
    publication = root / "publications/demo.toml"
    publication.write_text(
        """schema = 1
id = "demo"
kind = "worksheet"
title = "Demo"
profile = "mathpub.exam"
projections = ["student"]
[[sections]]
title = "Demo"
questions = []
"""
    )
    watched = root / "components/watched.tex"
    watched.parent.mkdir(exist_ok=True)
    watched.write_text("before")
    edition = root / "build/demo/A"
    edition.mkdir(parents=True)
    pdf = edition / "demo-A-student.pdf"
    pdf.write_bytes(b"old pdf fixture")
    review_dir = edition / "review-pages"
    review_dir.mkdir()
    stale = review_dir / "demo-A-student-page-001.png"
    stale.write_bytes(b"stale")
    fingerprints = iter((("same", "before"), ("same", "after")))
    rendered = []
    events = []
    prompts = []

    def fake_builder(*_args, **_kwargs):
        pdf.write_bytes(b"new pdf fixture")
        return {
            "edition": "build/demo/A",
            "outputs": [{"projection": "student", "path": "demo-A-student.pdf", "pages": 2}],
            "instance_cache": {"components_reused": 1},
            "latex_format": None,
        }

    def fake_renderer(_pdf_path, page, target):
        rendered.append((page, target))
        target.write_bytes(b"changed page")

    async def exercise():
        async def send_event(event):
            events.append(event)

        async def send_review_prompt(prompt):
            prompts.append(prompt)

        watcher = IncrementalPreviewWatcher(
            project,
            send_event,
            poll_interval=0.01,
            builder=fake_builder,
            format_dumper=lambda *_args, **_kwargs: {"format": None},
            page_fingerprinter=lambda _path: next(fingerprints),
            page_renderer=fake_renderer,
            send_review_prompt=send_review_prompt,
        )
        selected = await watcher.select(
            {
                "publication_path": "publications/demo.toml",
                "path": "build/demo/A/demo-A-student.pdf",
                "root_seed": "2026",
                "variant": "A",
                "projection": "student",
                "font_family": "libertinus",
                "page": 1,
            }
        )
        assert selected is not None
        watched.write_text("after")
        for _ in range(100):
            if any(event["type"] == "preview-built" for event in events):
                break
            await asyncio.sleep(0.01)
        await watcher.close()

    asyncio.run(exercise())
    expected = "build/demo/A/review-pages/demo-A-student-page-002.png"
    assert events[-1]["review_pages"] == [expected]
    assert [page for page, _target in rendered] == [2]
    assert not stale.exists()
    assert (root / expected).read_bytes() == b"changed page"
    assert len(prompts) == 1
    assert expected in prompts[0]
    assert "do not declare the task complete" in prompts[0]


def test_preview_watcher_does_not_prepare_a_document_format_for_presentations(tmp_path):
    root = tmp_path / "project"
    init_project(root)
    project = find_project(root)
    publication = root / "publications/slides.toml"
    publication.write_text(
        """schema = 1
id = "demo.slides"
kind = "presentation"
title = "Demo Slides"
profile = "mathpub.exam"
theme = "metropolis"
projections = ["student"]
[[slides]]
id = "goals"
title = "Learning Goals"
source = "slides/goals.tex"
"""
    )

    def unexpected_format_dump(*_args, **_kwargs):
        raise AssertionError("presentations must compile through their Beamer preamble")

    watcher = IncrementalPreviewWatcher(
        project,
        lambda _event: None,
        format_dumper=unexpected_format_dump,
    )
    selected = _selection(
        project,
        {
            "publication_path": "publications/slides.toml",
            "root_seed": "2026",
            "variant": "review",
            "projection": "student",
            "font_family": "libertinus",
            "page": 1,
        },
    )
    assert selected is not None
    assert watcher.prepare(selected) == {
        "format": None,
        "metadata": None,
        "reused": True,
        "style": "presentation",
    }


def test_preview_watcher_tracks_library_style_sources(tmp_path):
    root = tmp_path / "project"
    init_project(root)
    project = find_project(root)
    publication = root / "publications/demo.toml"
    publication.write_text(
        """schema = 1
id = "demo"
kind = "worksheet"
title = "Demo"
profile = "mathpub.exam"
projections = ["student"]
[[sections]]
title = "Demo"
questions = []
"""
    )
    style_directory = root / "styles/house"
    style_directory.mkdir(parents=True)
    metadata = style_directory / "style.toml"
    metadata.write_text(
        """schema = 1
id = "house"
title = "House"
description = "The library house style."
extends = "mathpub"
tex = "style.tex"
"""
    )
    tex = style_directory / "style.tex"
    tex.write_text("\\geometry{margin=1in}\n")
    selected = _selection(
        project,
        {
            "publication_path": "publications/demo.toml",
            "root_seed": "2026",
            "variant": "A",
            "projection": "student",
            "font_family": "libertinus",
            "page": 1,
        },
    )
    assert selected is not None
    watcher = IncrementalPreviewWatcher(project, lambda _event: None)

    snapshot = watcher._source_snapshot(selected)

    assert metadata in snapshot
    assert tex in snapshot


def test_preview_watcher_does_not_scan_unrelated_catalog_for_presentations(tmp_path):
    root = tmp_path / "project"
    init_project(root)
    project = find_project(root)
    publication = root / "publications/slides.toml"
    publication.write_text(
        """schema = 1
id = "demo.slides"
kind = "presentation"
title = "Demo Slides"
profile = "mathpub.exam"
theme = "metropolis"
projections = ["student"]
[[slides]]
id = "goals"
title = "Learning Goals"
source = "slides/goals.tex"
"""
    )
    slide = root / "publications/slides/goals.tex"
    slide.parent.mkdir(parents=True)
    slide.write_text("Goals")
    unrelated = root / "components/unrelated/component.toml"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("unrelated")
    selected = _selection(
        project,
        {
            "publication_path": "publications/slides.toml",
            "root_seed": "2026",
            "variant": "A",
            "projection": "student",
            "font_family": "libertinus",
            "page": 1,
        },
    )
    assert selected is not None
    watcher = IncrementalPreviewWatcher(project, lambda _event: None)

    snapshot = watcher._source_snapshot(selected)

    assert publication in snapshot
    assert slide in snapshot
    assert unrelated not in snapshot


def test_preview_watcher_scans_without_blocking_terminal_event_loop(tmp_path, monkeypatch):
    root = tmp_path / "project"
    init_project(root)
    project = find_project(root)
    publication = root / "publications/demo.toml"
    publication.write_text("fixture")
    watcher = IncrementalPreviewWatcher(
        project,
        lambda _event: None,
        poll_interval=0.01,
    )
    message = {
        "publication_path": "publications/demo.toml",
        "root_seed": "2026",
        "variant": "A",
        "projection": "student",
        "font_family": "libertinus",
        "page": 1,
    }
    scan_started = threading.Event()
    release_scan = threading.Event()
    scan_finished = threading.Event()

    async def exercise():
        selected = await watcher.select(message)
        assert selected is not None
        original_snapshot = watcher._source_snapshot

        def slow_snapshot(selection):
            scan_started.set()
            release_scan.wait(timeout=1.0)
            result = original_snapshot(selection)
            scan_finished.set()
            return result

        monkeypatch.setattr(watcher, "_source_snapshot", slow_snapshot)
        fallback_release = threading.Timer(0.3, release_scan.set)
        fallback_release.start()
        try:
            for _ in range(100):
                if scan_started.is_set():
                    break
                await asyncio.sleep(0.005)
            assert scan_started.is_set()

            # This coroutine remains schedulable while the filesystem scan is blocked.
            await asyncio.sleep(0.01)
            assert not scan_finished.is_set()
        finally:
            release_scan.set()
            fallback_release.cancel()
            await watcher.close()

    asyncio.run(exercise())
