"""SyncTeX spatial indexing and mathpub source-map resolution."""

from __future__ import annotations

import gzip
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pypdf import PdfReader

SP_PER_BIG_POINT = 65781.76
INPUT_RE = re.compile(r"^Input:(?P<tag>\d+):(?P<path>.+)$")
RECORD_RE = re.compile(
    r"^\((?P<tag>\d+),(?P<line>\d+):"
    r"(?P<x>-?\d+),(?P<y>-?\d+):"
    r"(?P<width>-?\d+),(?P<height>-?\d+),(?P<depth>-?\d+)"
)


class SyncTeXError(ValueError):
    """Raised when SyncTeX or source-map data is missing or malformed."""


@dataclass(frozen=True)
class SyncRecord:
    """One source-associated box from a SyncTeX file, measured in PDF points."""

    page: int
    line: int
    x: float
    y: float
    width: float
    height: float


def _overlaps(first: SyncRecord, second: SyncRecord) -> bool:
    return not (
        first.x + first.width < second.x
        or second.x + second.width < first.x
        or first.y + first.height < second.y
        or second.y + second.height < first.y
    )


def parse_records(
    synctex_path: Path,
    generated_source: Path,
    page: int,
) -> list[SyncRecord]:
    """Parse exact-line boxes for one generated TeX source and PDF page."""
    if page < 1:
        raise SyncTeXError("page must be a positive integer")
    if not synctex_path.is_file():
        raise SyncTeXError(f"SyncTeX file not found: {synctex_path}")

    with gzip.open(synctex_path, "rt", encoding="utf-8", errors="replace") as stream:
        lines = stream.read().splitlines()

    inputs: dict[int, str] = {}
    magnification = 1000
    unit = 1
    x_offset = 0
    y_offset = 0
    for line in lines:
        if match := INPUT_RE.match(line):
            inputs[int(match.group("tag"))] = match.group("path")
        elif line.startswith("Magnification:"):
            magnification = int(line.partition(":")[2])
        elif line.startswith("Unit:"):
            unit = int(line.partition(":")[2])
        elif line.startswith("X Offset:"):
            x_offset = int(line.partition(":")[2])
        elif line.startswith("Y Offset:"):
            y_offset = int(line.partition(":")[2])
        elif line == "Content:":
            break

    source_tag = next(
        (tag for tag, path in inputs.items() if Path(path).name == generated_source.name),
        None,
    )
    if source_tag is None:
        raise SyncTeXError(f"generated source is absent from SyncTeX data: {generated_source.name}")

    scale = unit * magnification / 1000 / SP_PER_BIG_POINT
    current_page: int | None = None
    records: list[SyncRecord] = []
    for line in lines:
        if line.startswith("{") and line[1:].isdigit():
            current_page = int(line[1:])
            continue
        if line == "}":
            current_page = None
            continue
        if current_page != page or not (match := RECORD_RE.match(line)):
            continue
        if int(match.group("tag")) != source_tag:
            continue

        width_sp = int(match.group("width"))
        height_sp = int(match.group("height")) + int(match.group("depth"))
        if width_sp <= 0 or height_sp <= 0:
            continue
        records.append(
            SyncRecord(
                page=page,
                line=int(match.group("line")),
                x=round((int(match.group("x")) + x_offset) * scale, 3),
                y=round(
                    (int(match.group("y")) + y_offset - int(match.group("height"))) * scale,
                    3,
                ),
                width=round(width_sp * scale, 3),
                height=round(height_sp * scale, 3),
            )
        )
    return records


def load_source_map(source_map_path: Path, projection: str) -> list[dict[str, Any]]:
    """Load and validate one projection from a generated source map."""
    try:
        payload = json.loads(source_map_path.read_text(encoding="utf-8"))
        entries = payload["projections"][projection]
    except (FileNotFoundError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise SyncTeXError(
            f"source map does not contain projection {projection!r}: {source_map_path}"
        ) from error
    if payload.get("schema") != 1 or not isinstance(entries, list):
        raise SyncTeXError(f"unsupported source-map schema: {source_map_path}")
    return entries


def resolve_boxes(
    records: list[SyncRecord],
    source_map: list[dict[str, Any]],
    *,
    project_root: Path,
    generated_source: Path,
    page: int,
) -> list[dict[str, Any]]:
    """Union SyncTeX records within each mapped component fragment."""
    boxes: list[dict[str, Any]] = []
    for entry in source_map:
        start = int(entry["generated_start_line"])
        end = int(entry["generated_end_line"])
        matching = [record for record in records if start <= record.line <= end]
        substantive = [record for record in matching if record.line < end - 2]
        if substantive:
            matching = [
                record
                for record in matching
                if record.line < end - 2 or any(_overlaps(record, other) for other in substantive)
            ]
        if not matching:
            continue

        left = min(record.x for record in matching)
        top = min(record.y for record in matching)
        right = max(record.x + record.width for record in matching)
        bottom = max(record.y + record.height for record in matching)
        authored_source = str(entry["authored_source"])
        boxes.append(
            {
                "component_id": entry["component_id"],
                "fragment": entry["fragment"],
                "authored_source": authored_source,
                "authored_source_absolute": str((project_root / authored_source).resolve()),
                "generated_source": str(generated_source.relative_to(project_root)),
                "generated_start_line": start,
                "generated_end_line": end,
                "page": page,
                "x": round(left, 3),
                "y": round(top, 3),
                "w": round(right - left, 3),
                "h": round(bottom - top, 3),
            }
        )
    return boxes


def spatial_index(
    project_root: Path,
    publication_id: str,
    variant: str,
    projection: str,
    page: int,
    *,
    build_dir: str = "build",
) -> dict[str, Any]:
    """Build the Phase 2 API payload for one publication projection and page."""
    edition = project_root / build_dir / publication_id / variant
    manifest_path = edition / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise SyncTeXError(f"edition manifest not found or invalid: {manifest_path}") from error
    if manifest.get("publication_id") != publication_id or manifest.get("variant") != variant:
        raise SyncTeXError(f"edition manifest does not match {publication_id}/{variant}")

    output = next(
        (item for item in manifest.get("outputs", []) if item.get("projection") == projection),
        None,
    )
    if output is None:
        raise SyncTeXError(f"projection not found in edition: {projection}")
    if page < 1 or page > int(output["pages"]):
        raise SyncTeXError(f"page {page} is outside projection page range")

    pdf_path = edition / output["path"]
    synctex_path = edition / output.get("synctex", f"{pdf_path.stem}.synctex.gz")
    generated_source = edition / "generated-tex" / f"{pdf_path.stem}.tex"
    source_map = load_source_map(edition / "generated-tex" / "source-map.json", projection)
    records = parse_records(synctex_path, generated_source, page)
    boxes = resolve_boxes(
        records,
        source_map,
        project_root=project_root,
        generated_source=generated_source,
        page=page,
    )
    pdf_page = PdfReader(pdf_path).pages[page - 1]
    return {
        "schema": 1,
        "publication_id": publication_id,
        "variant": variant,
        "projection": projection,
        "page": page,
        "page_size": {
            "width": float(pdf_page.mediabox.width),
            "height": float(pdf_page.mediabox.height),
            "unit": "pt",
        },
        "boxes": boxes,
    }
