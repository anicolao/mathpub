"""Discover built-in and library-defined publication styles."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mathpub.config import ID_PATTERN, Project, load_toml, relative
from mathpub.errors import MathpubError

BUILTIN_STYLES: dict[str, dict[str, Any]] = {
    "mathpub": {
        "id": "mathpub",
        "title": "MathPub",
        "description": "The standard book design with title page, contents, and chapter hierarchy.",
    },
    "anna": {
        "id": "anna",
        "title": "Anna",
        "description": "A compact workbook design with prominent lesson and practice headings.",
    },
}

FORBIDDEN_STYLE_TEX = re.compile(
    r"\\(?:documentclass\b|begin\s*\{document\}|end\s*\{document\}|"
    r"include\b|input\b|openin\b|openout\b)"
)


@dataclass(frozen=True)
class ResolvedStyle:
    """One style resolved to a built-in renderer and ordered TeX customizations."""

    identifier: str
    title: str
    description: str
    source: str
    base: str
    metadata_path: Path | None
    metadata_paths: tuple[Path, ...]
    tex_paths: tuple[Path, ...]

    def summary(self, project: Project) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.identifier,
            "title": self.title,
            "description": self.description,
            "source": self.source,
            "base": self.base,
            "supports": ["textbook"],
        }
        if self.metadata_path is not None:
            data["path"] = relative(project, self.metadata_path.parent)
            data["tex"] = [relative(project, path) for path in self.tex_paths]
        return data

    def detail(self, project: Project) -> dict[str, Any]:
        data = self.summary(project)
        data["preamble_sha256"] = hashlib.sha256(self.preamble.encode()).hexdigest()
        return data

    @property
    def preamble(self) -> str:
        return "\n".join(path.read_text(encoding="utf-8").rstrip() for path in self.tex_paths)

    def source_hashes(self, project: Project) -> dict[str, str]:
        return {
            relative(project, path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (*self.metadata_paths, *self.tex_paths)
        }


class StyleCatalog:
    """Catalog built-ins together with styles stored under configured style roots."""

    def __init__(self, project: Project) -> None:
        self.project = project
        self._custom: dict[str, tuple[Path, dict[str, Any]]] = {}
        for root in project.style_roots:
            if not root.exists():
                continue
            for metadata_path in sorted(root.rglob("style.toml")):
                metadata = load_toml(metadata_path, "style")
                identifier = metadata["id"]
                if not ID_PATTERN.fullmatch(identifier):
                    raise MathpubError("MP-SRC-006", f"invalid style ID: {identifier}")
                if identifier in BUILTIN_STYLES:
                    raise MathpubError(
                        "MP-STYLE-001", f"custom style cannot replace built-in style: {identifier}"
                    )
                if identifier in self._custom:
                    raise MathpubError("MP-SRC-007", f"duplicate style ID: {identifier}")
                tex_path = (metadata_path.parent / metadata["tex"]).resolve()
                try:
                    tex_path.relative_to(metadata_path.parent.resolve())
                    tex_path.relative_to(project.root)
                except ValueError as error:
                    raise MathpubError(
                        "MP-SRC-005", f"style source escapes its directory: {metadata['tex']}"
                    ) from error
                if not tex_path.is_file():
                    raise MathpubError("MP-SRC-012", f"missing style TeX source: {tex_path}")
                tex_source = tex_path.read_text(encoding="utf-8")
                source_without_comments = re.sub(r"(?m)(?<!\\)%.*$", "", tex_source)
                forbidden = FORBIDDEN_STYLE_TEX.search(source_without_comments)
                if forbidden:
                    raise MathpubError(
                        "MP-TEX-008",
                        f"forbidden TeX command in {relative(project, tex_path)}: "
                        f"{forbidden.group()}",
                    )
                self._custom[identifier] = (metadata_path, metadata)
        for identifier in self._custom:
            self.resolve(identifier)

    def resolve(self, identifier: str) -> ResolvedStyle:
        return self._resolve(identifier, ())

    def _resolve(self, identifier: str, chain: tuple[str, ...]) -> ResolvedStyle:
        if identifier in BUILTIN_STYLES:
            metadata = BUILTIN_STYLES[identifier]
            return ResolvedStyle(
                identifier=identifier,
                title=metadata["title"],
                description=metadata["description"],
                source="built-in",
                base=identifier,
                metadata_path=None,
                metadata_paths=(),
                tex_paths=(),
            )
        if identifier in chain:
            cycle = " -> ".join((*chain, identifier))
            raise MathpubError("MP-STYLE-002", f"cyclic style inheritance: {cycle}")
        try:
            metadata_path, metadata = self._custom[identifier]
        except KeyError as error:
            raise MathpubError(
                "MP-STYLE-003", f"unknown publication style: {identifier}"
            ) from error
        parent = self._resolve(metadata["extends"], (*chain, identifier))
        tex_path = (metadata_path.parent / metadata["tex"]).resolve()
        return ResolvedStyle(
            identifier=identifier,
            title=metadata["title"],
            description=metadata["description"],
            source="library",
            base=parent.base,
            metadata_path=metadata_path,
            metadata_paths=(*parent.metadata_paths, metadata_path),
            tex_paths=(*parent.tex_paths, tex_path),
        )

    def entries(self) -> list[ResolvedStyle]:
        identifiers = [*BUILTIN_STYLES, *sorted(self._custom)]
        return [self.resolve(identifier) for identifier in identifiers]

    def for_publication(self, publication: dict[str, Any]) -> ResolvedStyle:
        return self.resolve(publication.get("style", "mathpub"))


def prepare_publication_style(project: Project, publication: dict[str, Any]) -> ResolvedStyle:
    """Resolve and attach renderer-only style data to validated publication metadata."""
    style = StyleCatalog(project).for_publication(publication)
    publication["_mathpub_style_id"] = style.identifier
    publication["_mathpub_style_base"] = style.base
    publication["_mathpub_style_preamble"] = style.preamble
    return style


def publication_style_base(publication: dict[str, Any]) -> str:
    """Return the built-in rendering structure used by a prepared publication."""
    return publication.get("_mathpub_style_base", publication.get("style", "mathpub"))
