"""Project discovery and versioned TOML validation."""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from difflib import get_close_matches
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema

from mathpub.errors import MathpubError

ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")


@lru_cache
def schema_definition(schema: str) -> dict[str, Any]:
    """Return one packaged schema as the authoritative metadata definition."""
    schema_text = resources.files("mathpub.schemas").joinpath(f"{schema}-v1.json").read_text()
    return json.loads(schema_text)


def schema_enum(schema: str, property_name: str) -> tuple[str, ...]:
    return tuple(schema_definition(schema)["properties"][property_name]["enum"])


@dataclass(frozen=True)
class Project:
    root: Path
    config: dict[str, Any]

    @property
    def question_roots(self) -> list[Path]:
        return [self.root / path for path in self.config.get("question_roots", ["questions"])]

    @property
    def component_roots(self) -> list[Path]:
        return [self.root / path for path in self.config.get("component_roots", ["components"])]

    @property
    def profile_roots(self) -> list[Path]:
        return [self.root / path for path in self.config.get("profile_roots", ["profiles"])]

    @property
    def style_roots(self) -> list[Path]:
        return [self.root / path for path in self.config.get("style_roots", ["styles"])]

    @property
    def publication_roots(self) -> list[Path]:
        return [self.root / path for path in self.config.get("publication_roots", ["publications"])]


def load_toml(path: Path, schema: str) -> dict[str, Any]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise MathpubError("MP-SRC-001", f"source file does not exist: {path}") from error
    except tomllib.TOMLDecodeError as error:
        raise MathpubError("MP-SRC-002", f"invalid TOML in {path}: {error}") from error
    if schema == "publication" and data.get("kind") == "textbook" and "chapters" in data:
        raise MathpubError(
            "MP-SRC-016",
            "textbook publications must use [[component_chapters]]; raw [[chapters]] TeX "
            "sources are not component-backed and cannot be reliably selected, edited, or "
            "commented on in the review workspace",
            details={
                "source": str(path),
                "unsupported_source_model": "chapters",
                "required_source_model": "component_chapters",
                "remediation": (
                    "Replace [[chapters]] with [[component_chapters]] and move every "
                    "reviewable passage into catalog components referenced by include, derive, "
                    "or problem_set blocks."
                ),
            },
        )
    if schema == "publication" and data.get("kind") == "textbook":
        inline_chapter = next(
            (
                index
                for index, chapter in enumerate(data.get("component_chapters", []))
                if isinstance(chapter, dict) and "introduction" in chapter
            ),
            None,
        )
        if inline_chapter is not None:
            location = f"component_chapters.{inline_chapter}.introduction"
            raise MathpubError(
                "MP-SRC-016",
                f"reviewable textbook text at {location} must be a catalog component; inline "
                "chapter introductions are not selectable or commentable in the review workspace",
                details={
                    "source": str(path),
                    "location": location,
                    "required_source_model": "component",
                    "remediation": (
                        "Move the introduction into a catalog component and reference it from an "
                        "include block with an explicit placement."
                    ),
                },
            )
    try:
        jsonschema.validate(data, schema_definition(schema))
    except jsonschema.ValidationError as error:
        location = ".".join(str(part) for part in error.absolute_path) or "document"
        details: dict[str, Any] = {"source": str(path), "location": location}
        suggestion = ""
        if schema == "component" and list(error.absolute_path) == ["kind"]:
            matches = get_close_matches(str(error.instance), schema_enum("component", "kind"), n=1)
            if matches:
                details["suggestion"] = matches[0]
                suggestion = f"; did you mean {matches[0]!r}?"
        raise MathpubError(
            "MP-SRC-003",
            f"invalid {schema} metadata in {path} at {location}: {error.message}{suggestion}",
            details=details,
        ) from error
    return data


def find_project(start: Path | None = None) -> Project:
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for directory in (current, *current.parents):
        config_path = directory / "mathpub.toml"
        if config_path.is_file():
            return Project(directory, load_toml(config_path, "project"))
    raise MathpubError("MP-SRC-004", "no mathpub.toml found in this directory or its parents")


def relative(project: Project, path: Path) -> str:
    try:
        return path.resolve().relative_to(project.root).as_posix()
    except ValueError as error:
        raise MathpubError("MP-SRC-005", f"path escapes the project root: {path}") from error
