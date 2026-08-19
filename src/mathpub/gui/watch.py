"""Incremental publication rebuilding for the interactive workspace."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import tomllib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mathpub.config import Project, load_toml
from mathpub.errors import MathpubError
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
    output_path: Path | None


def _selection(project: Project, message: dict[str, object]) -> PreviewSelection | None:
    publication_value = message.get("publication_path")
    fields = ("root_seed", "variant", "projection", "font_family")
    page = message.get("page", 1)
    lesson_ids = message.get("lesson_ids", [])
    output_value = message.get("path")
    if (
        not isinstance(publication_value, str)
        or not all(isinstance(message.get(field), str) for field in fields)
        or not isinstance(page, int)
        or not isinstance(lesson_ids, list)
        or not all(
            isinstance(lesson_id, str) and SAFE_VALUE.fullmatch(lesson_id)
            for lesson_id in lesson_ids
        )
        or (output_value is not None and not isinstance(output_value, str))
    ):
        return None
    publication_path = (project.root / publication_value).resolve()
    output_path = (project.root / output_value).resolve() if output_value else None
    if (
        not publication_path.is_relative_to(project.root)
        or not publication_path.is_file()
        or publication_path.suffix != ".toml"
        or str(message["projection"]) not in PROJECTIONS
        or str(message["font_family"]) not in FONT_FAMILIES
        or not SAFE_VALUE.fullmatch(str(message["variant"]))
        or page < 1
        or page > 10_000
        or (
            output_path is not None
            and (
                not output_path.is_relative_to(project.root) or output_path.suffix.lower() != ".pdf"
            )
        )
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
        output_path=output_path,
    )


def _pdf_page_fingerprints(pdf_path: Path | None) -> tuple[str, ...]:
    """Fingerprint low-resolution page pixels so PDF internals do not cause false changes."""
    if pdf_path is None or not pdf_path.is_file():
        return ()
    pdftocairo = shutil.which("pdftocairo")
    if pdftocairo is None:
        raise RuntimeError("pdftocairo is unavailable; cannot identify changed PDF pages")
    with tempfile.TemporaryDirectory(prefix="mathpub-page-fingerprints-") as temporary:
        prefix = Path(temporary) / "page"
        subprocess.run(
            [pdftocairo, "-png", "-r", "36", str(pdf_path), str(prefix)],
            check=True,
            capture_output=True,
            timeout=120,
        )
        pages = sorted(
            prefix.parent.glob("page-*.png"),
            key=lambda path: int(path.stem.rsplit("-", 1)[1]),
        )
        return tuple(hashlib.sha256(path.read_bytes()).hexdigest() for path in pages)


def _render_pdf_page(pdf_path: Path, page: int, target: Path) -> None:
    """Render one review page to a stable PNG path using the Nix-provided Poppler tool."""
    pdftocairo = shutil.which("pdftocairo")
    if pdftocairo is None:
        raise RuntimeError("pdftocairo is unavailable; cannot render incremental review pages")
    target.parent.mkdir(parents=True, exist_ok=True)
    prefix = target.with_suffix("")
    subprocess.run(
        [
            pdftocairo,
            "-png",
            "-singlefile",
            "-f",
            str(page),
            "-l",
            str(page),
            "-r",
            "150",
            str(pdf_path),
            str(prefix),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    if not target.is_file():
        raise RuntimeError(f"pdftocairo did not create review image: {target}")


def _changed_page_numbers(
    previous: tuple[str, ...],
    current: tuple[str, ...],
) -> tuple[int, ...]:
    """Return current pages whose rendered pixels changed."""
    changed = {
        index + 1
        for index, fingerprint in enumerate(current)
        if index >= len(previous) or previous[index] != fingerprint
    }
    if len(previous) != len(current) and current:
        changed.add(len(current))
    return tuple(sorted(changed))


def _review_prompt(review_pages: list[str], *, page_count_changed: bool) -> str:
    if review_pages:
        pages = ", ".join(review_pages)
        count_note = " The publication's page count also changed." if page_count_changed else ""
        return (
            "MathPub's incremental build completed. Before continuing, use your image-viewing "
            f"tool to inspect every changed page PNG: {pages}.{count_note} Check that the content "
            "and formatting are correct, nothing is clipped, overlapping, or overcrowded, and "
            "every diagram is clear, legible, and mathematically consistent. Fix any issue in "
            "the authored source and let the incremental build run again; do not declare the "
            "task complete until you have reviewed all of these pages."
        )
    return (
        "MathPub's incremental build completed, but no rendered page content changed. Confirm "
        "that this is expected before continuing; if the edit should be visible, investigate the "
        "publication selection and authored source."
    )


def _build_in_authoring_environment(
    project: Project,
    selection: PreviewSelection,
) -> dict[str, Any]:
    """Build through the library shell so generators can use its extra packages."""
    nix = shutil.which("nix")
    if nix is None:
        raise RuntimeError("Nix is unavailable; cannot enter the library authoring environment")
    command = [
        nix,
        "develop",
        "--no-write-lock-file",
        "--no-warn-dirty",
        "--quiet",
        "--command",
        "mathpub",
        "build",
        str(selection.publication_path.relative_to(project.root)),
        "--seed",
        selection.root_seed,
        "--variant",
        selection.variant,
        "--projection",
        selection.projection,
        "--font",
        selection.font_family,
        "--replace",
        "--json",
    ]
    for lesson_id in selection.lesson_ids:
        command.extend(("--lesson", lesson_id))
    process = subprocess.run(
        command,
        cwd=project.root,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError as error:
        diagnostic = process.stderr.strip() or process.stdout.strip() or "no diagnostic output"
        raise RuntimeError(f"library authoring environment build failed: {diagnostic}") from error
    if not isinstance(payload, dict):
        raise RuntimeError("library authoring environment build returned invalid JSON")
    if process.returncode != 0 or payload.get("status") != "ok":
        details = payload.get("error", {})
        if not isinstance(details, dict):
            details = {}
        raise MathpubError(
            str(details.get("code", "MP-GUI-024")),
            str(details.get("message", process.stderr.strip() or "preview build failed")),
            exit_code=process.returncode or 1,
            details=details.get("details") if isinstance(details.get("details"), dict) else None,
        )
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("library authoring environment build returned invalid JSON data")
    return data


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
        page_fingerprinter: Callable[[Path | None], tuple[str, ...]] = _pdf_page_fingerprints,
        page_renderer: Callable[[Path, int, Path], None] = _render_pdf_page,
        send_review_prompt: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self.project = project
        self.send_event = send_event
        self.poll_interval = poll_interval
        self.builder = builder
        self.format_dumper = format_dumper
        self.page_fingerprinter = page_fingerprinter
        self.page_renderer = page_renderer
        self.send_review_prompt = send_review_prompt
        self.selection: PreviewSelection | None = None
        self._snapshot: dict[Path, tuple[int, int]] = {}
        self._selection_revision = 0
        self._snapshot_revision = 0
        self._task: asyncio.Task[None] | None = None
        self._page_fingerprints: tuple[str, ...] | None = None
        self._fingerprint_revision = 0

    async def select(self, message: dict[str, object]) -> PreviewSelection | None:
        selected = _selection(self.project, message)
        previous_selection = self.selection
        previous_fingerprints = self._page_fingerprints
        self._selection_revision += 1
        revision = self._selection_revision
        self.selection = selected
        self._page_fingerprints = None
        self._fingerprint_revision = revision
        if (
            selected is not None
            and previous_selection is not None
            and selected.output_path == previous_selection.output_path
            and previous_fingerprints is not None
        ):
            fingerprints = previous_fingerprints
        else:
            fingerprints = await asyncio.to_thread(
                self.page_fingerprinter,
                selected.output_path if selected is not None else None,
            )
        snapshot = await asyncio.to_thread(self._source_snapshot, selected)
        if revision != self._selection_revision:
            return selected
        self._page_fingerprints = fingerprints
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
        if self.builder is build and (self.project.root / "flake.nix").is_file():
            return _build_in_authoring_environment(self.project, selection)
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

    def _review_changed_pages(
        self,
        pdf_path: Path,
        previous_fingerprints: tuple[str, ...],
    ) -> tuple[list[str], tuple[str, ...]]:
        current_fingerprints = self.page_fingerprinter(pdf_path)
        changed_pages = _changed_page_numbers(previous_fingerprints, current_fingerprints)
        review_dir = pdf_path.parent / "review-pages"
        review_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        with tempfile.TemporaryDirectory(prefix=".tmp-review-", dir=review_dir) as temporary:
            staged = []
            for page in changed_pages:
                name = f"{pdf_path.stem}-page-{page:03d}.png"
                target = Path(temporary) / name
                self.page_renderer(pdf_path, page, target)
                staged.append((target, review_dir / name))
            for stale in review_dir.glob(f"{pdf_path.stem}-page-*.png"):
                stale.unlink()
            for source, target in staged:
                source.replace(target)
                paths.append(str(target.relative_to(self.project.root)))
        return paths, current_fingerprints

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
            if self._page_fingerprints is None or self._fingerprint_revision != revision:
                self._page_fingerprints = await asyncio.to_thread(
                    self.page_fingerprinter,
                    selection.output_path,
                )
                self._fingerprint_revision = revision
            previous_fingerprints = self._page_fingerprints
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
            pdf_path = self.project.root / result["edition"] / output["path"]
            try:
                review_pages, current_fingerprints = await asyncio.to_thread(
                    self._review_changed_pages,
                    pdf_path,
                    previous_fingerprints,
                )
            except Exception as error:
                review_pages = []
                current_fingerprints = previous_fingerprints
                review_error = str(error)
            else:
                review_error = None
                self._page_fingerprints = current_fingerprints
            page_count_changed = len(previous_fingerprints) != len(current_fingerprints)
            await self.send_event(
                {
                    "type": "preview-built",
                    "path": f"{result['edition']}/{output['path']}",
                    "page": selection.page,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                    "instance_cache": result["instance_cache"],
                    "format": result["latex_format"],
                    "review_pages": review_pages,
                }
            )
            if review_error is not None:
                await self.send_event(
                    {
                        "type": "preview-review-failed",
                        "error": review_error,
                    }
                )
                if self.send_review_prompt is not None:
                    await self.send_review_prompt(
                        "MathPub's incremental build completed, but changed-page PNG generation "
                        f"failed: {review_error}. Investigate this review failure before declaring "
                        "the task complete."
                    )
            elif self.send_review_prompt is not None:
                await self.send_review_prompt(
                    _review_prompt(review_pages, page_count_changed=page_count_changed)
                )

    async def close(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
