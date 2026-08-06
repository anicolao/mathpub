"""Incremental publication rebuilding for the interactive workspace."""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import time
import tomllib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mathpub.config import Project, load_toml
from mathpub.latex_format import dump_latex_format, publication_format_style
from mathpub.publish import build
from mathpub.styles import prepare_publication_style

WATCHED_SUFFIXES = {".json", ".py", ".sage", ".tex", ".toml"}
PROJECTIONS = {"student", "answers", "solutions", "validation", "parent"}
FONT_FAMILIES = {"computer-modern", "concrete", "libertinus"}
SAFE_VALUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class PreviewSelection:
    publication_path: Path
    root_seed: str
    variant: str
    projection: str
    font_family: str
    page: int
    lesson_ids: tuple[str, ...]


def _selection(project: Project, message: dict[str, object]) -> PreviewSelection | None:
    publication_value = message.get("publication_path")
    fields = ("root_seed", "variant", "projection", "font_family")
    page = message.get("page", 1)
    lesson_ids = message.get("lesson_ids", [])
    if (
        not isinstance(publication_value, str)
        or not all(isinstance(message.get(field), str) for field in fields)
        or not isinstance(page, int)
        or not isinstance(lesson_ids, list)
        or not all(
            isinstance(lesson_id, str) and SAFE_VALUE.fullmatch(lesson_id)
            for lesson_id in lesson_ids
        )
    ):
        return None
    publication_path = (project.root / publication_value).resolve()
    if (
        not publication_path.is_relative_to(project.root)
        or not publication_path.is_file()
        or publication_path.suffix != ".toml"
        or str(message["projection"]) not in PROJECTIONS
        or str(message["font_family"]) not in FONT_FAMILIES
        or not SAFE_VALUE.fullmatch(str(message["variant"]))
        or page < 1
        or page > 10_000
    ):
        return None
    return PreviewSelection(
        publication_path=publication_path,
        root_seed=str(message["root_seed"]),
        variant=str(message["variant"]),
        projection=str(message["projection"]),
        font_family=str(message["font_family"]),
        page=page,
        lesson_ids=tuple(lesson_ids),
    )


class IncrementalPreviewWatcher:
    """Poll authored inputs and rebuild the active PDF projection after changes."""

    def __init__(
        self,
        project: Project,
        send_event: Callable[[dict[str, Any]], Awaitable[None]],
        *,
        poll_interval: float = 0.35,
        builder: Callable[..., dict[str, Any]] = build,
        format_dumper: Callable[..., dict[str, Any]] = dump_latex_format,
    ) -> None:
        self.project = project
        self.send_event = send_event
        self.poll_interval = poll_interval
        self.builder = builder
        self.format_dumper = format_dumper
        self.selection: PreviewSelection | None = None
        self._snapshot: dict[Path, tuple[int, int]] = {}
        self._selection_revision = 0
        self._snapshot_revision = 0
        self._task: asyncio.Task[None] | None = None

    async def select(self, message: dict[str, object]) -> PreviewSelection | None:
        selected = _selection(self.project, message)
        self._selection_revision += 1
        revision = self._selection_revision
        self.selection = selected
        snapshot = await asyncio.to_thread(self._source_snapshot, selected)
        if revision != self._selection_revision:
            return selected
        self._snapshot = snapshot
        self._snapshot_revision = revision
        if selected is not None and self._task is None:
            self._task = asyncio.create_task(self._run())
        return selected

    def _source_snapshot(
        self,
        selection: PreviewSelection | None,
    ) -> dict[Path, tuple[int, int]]:
        if selection is None:
            return {}
        roots = [selection.publication_path.parent, *self.project.style_roots]
        if self._publication_uses_catalog_sources(selection.publication_path):
            roots.extend((*self.project.question_roots, *self.project.component_roots))

        snapshot: dict[Path, tuple[int, int]] = {}
        for root in roots:
            if not root.exists():
                continue
            for directory, _, filenames in os.walk(root):
                for filename in filenames:
                    if Path(filename).suffix not in WATCHED_SUFFIXES:
                        continue
                    path = Path(directory) / filename
                    with contextlib.suppress(OSError):
                        stat = path.stat()
                        snapshot[path] = (stat.st_mtime_ns, stat.st_size)
        return snapshot

    @staticmethod
    def _publication_uses_catalog_sources(publication_path: Path) -> bool:
        """Whether a publication can depend on entries outside its source directory."""
        try:
            publication = tomllib.loads(publication_path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            # Stay conservative while an author is midway through an invalid edit.
            return True
        return "sections" in publication or "component_chapters" in publication

    def _prepare_format(self, selection: PreviewSelection) -> dict[str, Any]:
        publication = load_toml(selection.publication_path, "publication")
        prepare_publication_style(self.project, publication)
        style = publication_format_style(publication)
        if style == "presentation":
            return {
                "format": None,
                "metadata": None,
                "reused": True,
                "style": style,
            }
        font_family = (
            "computer-modern"
            if style == "anna"
            else selection.font_family or publication.get("font", "libertinus")
        )
        paper = "a4" if publication.get("paper") == "a4" else "letter"
        return self.format_dumper(
            self.project,
            style=style,
            font_family=font_family,
            paper=paper,
            replace=False,
        )

    def prepare(self, selection: PreviewSelection) -> dict[str, Any]:
        """Warm the selected preview's reusable format before reporting readiness."""
        return self._prepare_format(selection)

    def _build(self, selection: PreviewSelection) -> dict[str, Any]:
        self._prepare_format(selection)
        return self.builder(
            self.project,
            selection.publication_path,
            root_seed=selection.root_seed,
            variant=selection.variant,
            projections=[selection.projection],
            font_family=selection.font_family,
            replace=True,
            incremental=True,
            lesson_ids=list(selection.lesson_ids) or None,
        )

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self.poll_interval)
            selection = self.selection
            revision = self._selection_revision
            current = await asyncio.to_thread(self._source_snapshot, selection)
            if (
                selection is None
                or revision != self._selection_revision
                or revision != self._snapshot_revision
                or current == self._snapshot
            ):
                continue
            self._snapshot = current
            started = time.monotonic()
            await self.send_event({"type": "preview-build-started"})
            try:
                result = await asyncio.to_thread(self._build, selection)
            except Exception as error:
                await self.send_event(
                    {
                        "type": "preview-build-failed",
                        "error": str(error),
                    }
                )
                continue
            if selection != self.selection:
                continue
            output = next(
                item for item in result["outputs"] if item["projection"] == selection.projection
            )
            await self.send_event(
                {
                    "type": "preview-built",
                    "path": f"{result['edition']}/{output['path']}",
                    "page": selection.page,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                    "instance_cache": result["instance_cache"],
                    "format": result["latex_format"],
                }
            )

    async def close(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
