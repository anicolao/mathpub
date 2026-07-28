"""Tests for automatic incremental workspace regeneration."""

from __future__ import annotations

import asyncio

from mathpub.config import find_project
from mathpub.gui.watch import IncrementalPreviewWatcher, _selection
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
        selected = watcher.select(
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
