"""Persistent authoring-library discovery for the interactive workspace."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mathpub.config import Project, find_project
from mathpub.errors import MathpubError

HISTORY_LIMIT = 10


def default_library_history_path() -> Path:
    """Return the platform-appropriate per-user workspace state file."""
    if configured := os.environ.get("MATHPUB_LIBRARY_HISTORY"):
        return Path(configured).expanduser()
    if state_home := os.environ.get("XDG_STATE_HOME"):
        return Path(state_home).expanduser() / "mathpub/recent-libraries.json"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/MathPub/recent-libraries.json"
    return Path.home() / ".local/state/mathpub/recent-libraries.json"


def open_authoring_library(value: object) -> Project:
    """Validate and open an exact MathPub authoring-library root."""
    if not isinstance(value, str) or not value.strip():
        raise MathpubError("MP-GUI-020", "library folder must be a non-empty path")
    candidate = Path(value.strip()).expanduser()
    if not candidate.is_absolute():
        raise MathpubError("MP-GUI-020", "library folder must be an absolute path")
    candidate = candidate.resolve()
    if not candidate.is_dir():
        raise MathpubError("MP-GUI-020", f"library folder does not exist: {candidate}")
    if not (candidate / "mathpub.toml").is_file():
        raise MathpubError(
            "MP-GUI-021",
            f"folder is not a MathPub authoring library: {candidate}",
        )
    project = find_project(candidate)
    if project.root != candidate:
        raise MathpubError(
            "MP-GUI-021",
            f"folder is not a MathPub authoring-library root: {candidate}",
        )
    return project


@dataclass(frozen=True)
class LibraryHistory:
    """A most-recently-used list of validated local authoring libraries."""

    path: Path
    limit: int = HISTORY_LIMIT

    @classmethod
    def default(cls) -> LibraryHistory:
        return cls(default_library_history_path())

    def _stored_paths(self) -> list[str]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return []
        if (
            not isinstance(payload, dict)
            or payload.get("schema") != 1
            or not isinstance(payload.get("libraries"), list)
        ):
            return []
        return [path for path in payload["libraries"] if isinstance(path, str)]

    @staticmethod
    def _entry(project: Project) -> dict[str, str]:
        return {
            "name": str(project.config["project"]),
            "path": str(project.root),
        }

    def recent(self) -> list[dict[str, str]]:
        """Return stored libraries that still exist and contain valid project metadata."""
        entries: list[dict[str, str]] = []
        seen: set[Path] = set()
        for stored_path in self._stored_paths():
            try:
                project = open_authoring_library(stored_path)
            except MathpubError:
                continue
            if project.root in seen:
                continue
            seen.add(project.root)
            entries.append(self._entry(project))
            if len(entries) >= self.limit:
                break
        return entries

    def most_recent(self) -> Project | None:
        """Return the newest still-valid authoring library."""
        recent = self.recent()
        return open_authoring_library(recent[0]["path"]) if recent else None

    def remember(self, root: Path) -> None:
        """Move a validated library to the front and persist the bounded list atomically."""
        project = open_authoring_library(str(root))
        paths = [str(project.root)]
        paths.extend(
            entry["path"] for entry in self.recent() if Path(entry["path"]) != project.root
        )
        payload: dict[str, Any] = {
            "schema": 1,
            "libraries": paths[: self.limit],
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
            temporary.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.chmod(0o600)
            temporary.replace(self.path)
        except OSError as error:
            raise MathpubError(
                "MP-GUI-022",
                f"could not remember authoring library: {error}",
            ) from error
