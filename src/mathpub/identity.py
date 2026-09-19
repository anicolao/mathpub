"""Canonical bibliographic identity, display overrides, and non-mutating drift checks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pypdf import PdfReader

from mathpub.config import load_toml
from mathpub.errors import MathpubError


def load_identity(path: Path) -> dict:
    identity = load_toml(path, "identity")
    if "isbn" in identity:
        isbn = identity["isbn"].replace("-", "")
        if (
            len(isbn) != 13
            or not isbn.startswith(("978", "979"))
            or sum(int(value) * (1 if index % 2 == 0 else 3) for index, value in enumerate(isbn))
            % 10
        ):
            raise MathpubError("MP-IDENTITY-001", "invalid ISBN-13 checksum or prefix")
        identity["isbn"] = isbn
    return identity


def resolve_identity(publication: dict, publication_path: Path) -> dict:
    if "identity" not in publication:
        return publication
    path = (publication_path.parent / publication["identity"]).resolve()
    identity = load_identity(path)
    for key in ("title", "subtitle", "author"):
        if key in publication and publication[key] != identity.get(key, ""):
            raise MathpubError(
                "MP-IDENTITY-002", f"publication {key} drifts from canonical identity"
            )
    return {
        **publication,
        **{key: identity.get(key, "") for key in ("title", "subtitle", "author")},
        "_identity": identity,
        "_identity_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "_display_title": identity.get("display", {}).get("title", identity["title"]),
    }


def identity_tex(source: str, identity: dict, engine: str) -> str:
    from mathpub.render import _tex_escape

    command = r"\pdfextension info" if engine == "lualatex" else r"\pdfinfo"
    record = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode().hex()
    title = (b"\xfe\xff" + identity["title"].encode("utf-16-be")).hex()
    author = (b"\xfe\xff" + identity["author"].encode("utf-16-be")).hex()
    macros = []
    for key in (
        "title",
        "subtitle",
        "author",
        "publisher",
        "isbn",
        "edition",
        "year",
        "collection",
    ):
        name = "ISBN" if key == "isbn" else key.title()
        macros.append(
            rf"\providecommand{{\Mathpub{name}}}{{{_tex_escape(str(identity.get(key, '')))}}}"
        )
    spine = identity.get("display", {}).get("spine_title", identity["title"])
    macros.append(rf"\providecommand{{\MathpubSpineTitle}}{{{_tex_escape(spine)}}}")
    metadata = (
        rf"{command}{{/MathpubIdentity <{record}>}}"
        + "\n"
        + r"\makeatletter\@ifpackageloaded{hyperref}{"
        + rf"\hypersetup{{pdftitle={{{_tex_escape(identity['title'])}}},"
        + rf"pdfauthor={{{_tex_escape(identity['author'])}}}}}"
        + "}{"
        + rf"{command}{{/Title <{title}> /Author <{author}>}}"
        + r"}\makeatother"
    )
    marker = r"\begin{document}"
    return source.replace(marker, "\n".join(macros) + "\n" + metadata + "\n" + marker, 1)


def check_identity(path: Path, pdfs: list[Path]) -> dict:
    identity = load_identity(path)
    findings = []
    try:
        for pdf in pdfs:
            data = pdf.read_bytes()
            metadata = PdfReader(pdf).metadata or {}
            observed = json.loads(metadata.get("/MathpubIdentity", "null"))
            differences = [
                key
                for key in set(identity) | set(observed or {})
                if identity.get(key) != (observed or {}).get(key)
            ]
            if metadata.get("/Title") != identity["title"]:
                differences.append("pdf_title")
            if metadata.get("/Author") != identity["author"]:
                differences.append("pdf_author")
            findings.append(
                {
                    "path": str(pdf),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "differences": sorted(differences),
                }
            )
    except (OSError, ValueError, TypeError) as error:
        raise MathpubError("MP-IDENTITY-003", f"cannot inspect identity: {error}") from error
    report = {
        "identity": identity,
        "pdfs": findings,
        "passed": all(not entry["differences"] for entry in findings),
        "limitation": "ISBN checksum validity does not establish ownership.",
    }
    if not report["passed"]:
        raise MathpubError("MP-IDENTITY-002", "PDF identity drift", details={"report": report})
    return report
