"""Discover questions, publications, and profiles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mathpub.config import ID_PATTERN, Project, load_toml, relative
from mathpub.errors import MathpubError


@dataclass(frozen=True)
class Entry:
    kind: str
    path: Path
    metadata: dict[str, Any]

    def summary(self, project: Project) -> dict[str, Any]:
        result = {
            "id": self.metadata["id"],
            "title": self.metadata.get("title", ""),
            "path": relative(project, self.path),
        }
        if self.kind == "question":
            result.update(
                {
                    "points": self.metadata["points"],
                    "tags": self.metadata.get("tags", []),
                    "difficulty": self.metadata.get("difficulty"),
                    "generator": self.metadata.get("generator"),
                    "projections": [
                        name for name in ("prompt", "answer", "solution") if self.metadata.get(name)
                    ],
                }
            )
        elif self.kind == "component":
            result.update(
                {
                    "kind": self.metadata["kind"],
                    "status": self.metadata.get("status", "draft"),
                    "tags": self.metadata.get("tags", []),
                    "concepts": self.metadata.get("concepts", []),
                    "generator": self.metadata.get("generator"),
                    "fragments": sorted(self.metadata.get("fragments", {})),
                }
            )
        return result


class Catalog:
    def __init__(self, project: Project) -> None:
        self.project = project
        self.questions = self._directories(project.question_roots, "question", "question.toml")
        self.components = self._directories(project.component_roots, "component", "component.toml")
        self.profiles = self._directories(project.profile_roots, "profile", "profile.toml")
        self.publications = self._files(project.publication_roots, "publication", "*.toml")
        duplicate_components = set(self.questions) & set(self.components)
        if duplicate_components:
            duplicate = sorted(duplicate_components)[0]
            raise MathpubError("MP-SRC-007", f"duplicate component ID: {duplicate}")

    def _add(self, entries: dict[str, Entry], entry: Entry) -> None:
        identifier = entry.metadata["id"]
        if not ID_PATTERN.fullmatch(identifier):
            raise MathpubError("MP-SRC-006", f"invalid {entry.kind} ID: {identifier}")
        if identifier in entries:
            raise MathpubError("MP-SRC-007", f"duplicate {entry.kind} ID: {identifier}")
        entries[identifier] = entry

    def _directories(self, roots: list[Path], kind: str, filename: str) -> dict[str, Entry]:
        entries: dict[str, Entry] = {}
        for root in roots:
            if not root.exists():
                continue
            for metadata_path in sorted(root.rglob(filename)):
                self._add(
                    entries, Entry(kind, metadata_path.parent, load_toml(metadata_path, kind))
                )
        return entries

    def _files(self, roots: list[Path], kind: str, pattern: str) -> dict[str, Entry]:
        entries: dict[str, Entry] = {}
        for root in roots:
            if not root.exists():
                continue
            for metadata_path in sorted(root.rglob(pattern)):
                self._add(entries, Entry(kind, metadata_path, load_toml(metadata_path, kind)))
        return entries

    def entries(self, kind: str) -> dict[str, Entry]:
        return {
            "questions": self.questions,
            "components": self.components,
            "profiles": self.profiles,
            "publications": self.publications,
        }[kind]

    def get(self, kind: str, identifier: str) -> Entry:
        if kind == "component" and identifier in self.questions:
            return self.questions[identifier]
        entries = self.entries(f"{kind}s")
        try:
            return entries[identifier]
        except KeyError as error:
            raise MathpubError("MP-SRC-008", f"unknown {kind}: {identifier}") from error
