"""Incremental publication rebuilding for the interactive workspace."""

from __future__ import annotations

import asyncio
import contextlib
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mathpub.config import Project, load_toml
from mathpub.latex_format import dump_latex_format, publication_format_style
from mathpub.publish import build

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


def _selection(project: Project, message: dict[str, object]) -> PreviewSelection | None:
    publication_value = message.get("publication_path")
    fields = ("root_seed", "variant", "projection", "font_family")
    if not isinstance(publication_value, str) or not all(
        isinstance(message.get(field), str) for field in fields
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
    ):
        return None
    return PreviewSelection(
        publication_path=publication_path,
        root_seed=str(message["root_seed"]),
        variant=str(message["variant"]),
        projection=str(message["projection"]),
        font_family=str(message["font_family"]),
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
        self._task: asyncio.Task[None] | None = None

    def select(self, message: dict[str, object]) -> PreviewSelection | None:
        selected = _selection(self.project, message)
        self.selection = selected
        self._snapshot = self._source_snapshot(selected)
        if selected is not None and self._task is None:
            self._task = asyncio.create_task(self._run())
        return selected

    def _source_snapshot(
        self,
        selection: PreviewSelection | None,
    ) -> dict[Path, tuple[int, int]]:
        if selection is None:
            return {}
        paths = [
            path
            for path in selection.publication_path.parent.rglob("*")
            if path.is_file() and path.suffix in WATCHED_SUFFIXES
        ]
        for root in (*self.project.question_roots, *self.project.component_roots):
            if root.exists():
                paths.extend(
                    path
                    for path in root.rglob("*")
                    if path.is_file() and path.suffix in WATCHED_SUFFIXES
                )
        snapshot = {}
        for path in paths:
            with contextlib.suppress(OSError):
                stat = path.stat()
                snapshot[path] = (stat.st_mtime_ns, stat.st_size)
        return snapshot

    def _prepare_format(self, selection: PreviewSelection) -> dict[str, Any]:
        publication = load_toml(selection.publication_path, "publication")
        style = publication_format_style(publication)
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
        )

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self.poll_interval)
            selection = self.selection
            current = self._source_snapshot(selection)
            if selection is None or current == self._snapshot:
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
