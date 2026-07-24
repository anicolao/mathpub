"""Reusable LaTeX format dumps for fast interactive publication builds."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from mathpub.config import Project, relative
from mathpub.errors import MathpubError
from mathpub.render import anna_textbook_tex, document_tex, textbook_tex

FORMAT_SCHEMA = 1
FORMAT_STYLES = ("worksheet", "textbook", "anna")
FORMAT_FONTS = ("concrete", "libertinus", "computer-modern")
FORMAT_PAPERS = ("letter", "a4")


def publication_format_style(publication: dict[str, Any]) -> str:
    """Return the format family needed by one publication."""
    if publication.get("style") == "anna":
        return "anna"
    return "textbook" if publication.get("kind") == "textbook" else "worksheet"


def _format_key(style: str, font_family: str, paper: str) -> str:
    return f"{style}-{font_family}-{paper}"


def _format_directory(
    project: Project,
    style: str,
    font_family: str,
    paper: str,
) -> Path:
    build_root = project.root / project.config.get("build_dir", "build")
    return build_root / ".mathpub-formats" / _format_key(style, font_family, paper)


def _template_source(style: str, font_family: str, paper: str) -> str:
    publication = {
        "id": "mathpub.format",
        "kind": "textbook" if style != "worksheet" else "worksheet",
        "title": "mathpub format",
        "subtitle": "",
        "course": "",
        "author": "",
        "paper": paper,
        "style": "anna" if style == "anna" else "mathpub",
        "instructions": {"tex": ""},
    }
    if style == "worksheet":
        return document_tex(publication, "student", [], font_family)
    if style == "anna":
        return anna_textbook_tex(publication, "student", [])
    return textbook_tex(publication, "student", [], font_family)


def _install_luatex_dump_compatibility(destination: Path) -> None:
    """Guard TeX Live 2025's Unicode stage-table lookup during custom format dumps."""
    located = subprocess.run(
        ["kpsewhich", "lua-uni-stage-tables.lua"],
        capture_output=True,
        text=True,
        check=False,
    )
    source_path = Path(located.stdout.strip())
    if located.returncode or not source_path.is_file():
        return
    source = source_path.read_text(encoding="utf-8")
    needle = """    __index = function(_, key)
      local value = reader(buffer, bytes * key + 1)"""
    replacement = """    __index = function(_, key)
      if type(key) ~= 'number' then return nil end
      local value = reader(buffer, bytes * key + 1)"""
    if needle in source:
        (destination / source_path.name).write_text(
            source.replace(needle, replacement, 1),
            encoding="utf-8",
        )


def dump_latex_format(
    project: Project,
    *,
    style: str = "textbook",
    font_family: str = "libertinus",
    paper: str = "letter",
    replace: bool = False,
) -> dict[str, Any]:
    """Create a deterministic ``mathpub.fmt`` for one publication preamble."""
    if style not in FORMAT_STYLES:
        raise MathpubError("MP-TEX-013", f"unknown format style: {style}", exit_code=3)
    if font_family not in FORMAT_FONTS:
        raise MathpubError("MP-TEX-010", f"unknown font family: {font_family}", exit_code=3)
    if paper not in FORMAT_PAPERS:
        raise MathpubError("MP-TEX-014", f"unknown paper size: {paper}", exit_code=3)
    if style == "anna":
        font_family = "computer-modern"
    tex_engine = "pdflatex" if font_family == "computer-modern" else "lualatex"

    destination = _format_directory(project, style, font_family, paper)
    format_path = destination / "mathpub.fmt"
    metadata_path = destination / "format.json"
    source = _template_source(style, font_family, paper)
    source_sha256 = hashlib.sha256(source.encode()).hexdigest()
    if format_path.is_file() and metadata_path.is_file() and not replace:
        try:
            existing = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
        expected = {
            "schema": FORMAT_SCHEMA,
            "style": style,
            "font_family": font_family,
            "paper": paper,
            "tex_engine": tex_engine,
            "source_sha256": source_sha256,
        }
        if all(existing.get(key) == value for key, value in expected.items()):
            return {
                "format": relative(project, format_path),
                "metadata": relative(project, metadata_path),
                "reused": True,
            }

    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    template_path = destination / "mathpub-format.tex"
    template_path.write_text(source, encoding="utf-8")
    if tex_engine == "lualatex":
        _install_luatex_dump_compatibility(destination)
    command = [
        tex_engine,
        "-ini",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-jobname=mathpub",
        f"&{tex_engine}",
        "mylatexformat.ltx",
        template_path.name,
    ]
    process = subprocess.run(
        command,
        cwd=destination,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
        env={
            **os.environ,
            "HOME": str(destination),
            "SOURCE_DATE_EPOCH": "0",
            "XDG_CACHE_HOME": str(destination / ".cache"),
        },
    )
    log_path = destination / "mathpub-format.log"
    log_path.write_text(process.stdout + "\n" + process.stderr, encoding="utf-8")
    if process.returncode or not format_path.is_file():
        raise MathpubError(
            "MP-TEX-015",
            f"could not create {tex_engine} format; see {relative(project, log_path)}",
            exit_code=6,
            details={"log": relative(project, log_path)},
        )

    metadata = {
        "schema": FORMAT_SCHEMA,
        "style": style,
        "font_family": font_family,
        "paper": paper,
        "tex_engine": tex_engine,
        "source_sha256": source_sha256,
    }
    metadata_path.write_text(
        json.dumps(metadata, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return {
        "format": relative(project, format_path),
        "metadata": relative(project, metadata_path),
        "reused": False,
    }


def find_latex_format(
    project: Project,
    publication: dict[str, Any],
    font_family: str,
) -> Path | None:
    """Find a compatible precompiled format without creating one implicitly."""
    style = publication_format_style(publication)
    if style == "anna":
        font_family = "computer-modern"
    paper = "a4" if publication.get("paper") == "a4" else "letter"
    destination = _format_directory(project, style, font_family, paper)
    format_path = destination / "mathpub.fmt"
    metadata_path = destination / "format.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    expected = {
        "schema": FORMAT_SCHEMA,
        "style": style,
        "font_family": font_family,
        "paper": paper,
        "tex_engine": "pdflatex" if font_family == "computer-modern" else "lualatex",
        "source_sha256": hashlib.sha256(
            _template_source(style, font_family, paper).encode()
        ).hexdigest(),
    }
    if not format_path.is_file() or any(
        metadata.get(key) != value for key, value in expected.items()
    ):
        return None
    return format_path
