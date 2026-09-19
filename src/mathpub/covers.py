"""Profile-driven paperback cover geometry linked to an exact interior artifact."""

from __future__ import annotations

import io
import json
import math
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject

from mathpub.config import load_toml
from mathpub.errors import MathpubError
from mathpub.pdf_render import text_pages
from mathpub.print_export import manifest_artifact
from mathpub.releases import sha256


def cover_geometry(spec_path: Path) -> dict:
    spec = load_toml(spec_path, "cover")
    try:
        if any(isinstance(value, float) and not math.isfinite(value) for value in spec.values()):
            raise ValueError("non-finite cover dimension")
        manifest, output, data, manifest_hash = manifest_artifact(
            spec_path.parent / spec["interior_manifest"], spec["projection"]
        )
        reader = PdfReader(io.BytesIO(data))
        pages = len(reader.pages)
        if pages != output["pages"] or not spec.get("min_pages", 1) <= pages <= spec.get(
            "max_pages", 10000
        ):
            raise ValueError("interior page count violates its manifest or printer profile")
        width, height = spec["trim_width_pt"], spec["trim_height_pt"]
        for page in reader.pages:
            dims = [
                float(page.trimbox.width) * page.user_unit,
                float(page.trimbox.height) * page.user_unit,
            ]
            if page.rotation % 180:
                dims.reverse()
            if any(abs(a - b) > 0.01 for a, b in zip(dims, (width, height), strict=True)):
                raise ValueError("every interior page must match the profile trim")
        multiple = spec.get("round_pages_to", 2)
        production_pages = math.ceil(pages / multiple) * multiple
        spine = production_pages * spec["spine_per_page_pt"]
        bleed, safe = spec["bleed_pt"], spec["safe_pt"]
        if 2 * safe >= min(width, height):
            raise ValueError("text-safe margin consumes the whole cover panel")
        back = [bleed + safe, bleed + safe, bleed + width - safe, bleed + height - safe]
        front = [back[0] + width + spine, back[1], back[2] + width + spine, back[3]]
        barcode = spec.get("barcode_box_pt")
        if barcode and not (
            back[0] <= barcode[0] < barcode[2] <= back[2]
            and back[1] <= barcode[1] < barcode[3] <= back[3]
        ):
            raise ValueError("barcode box must be inside the back panel safe area")
        return {
            "schema": 1,
            "profile": spec,
            "profile_sha256": sha256(spec_path.read_bytes()),
            "interior": {
                "sha256": sha256(data),
                "manifest_sha256": manifest_hash,
                "source": manifest["source"],
                "pages": pages,
                "identity": manifest.get("identity"),
            },
            "production_pages": production_pages,
            "spine_pt": spine,
            "width_pt": 2 * width + spine + 2 * bleed,
            "height_pt": height + 2 * bleed,
            "folds_pt": [bleed + width, bleed + width + spine],
            "safe_panels_pt": [back, front],
            "barcode_box_pt": barcode,
        }
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise MathpubError("MP-COVER-001", f"cannot prepare cover: {error}") from error


def cover_preamble(geometry: dict) -> str:
    return (
        rf"\geometry{{paperwidth={geometry['width_pt']}bp,"
        rf"paperheight={geometry['height_pt']}bp,margin=0bp}}" + "\n" + r"\pagestyle{empty}"
    )


def _guides(geometry: dict, target: Path):
    writer = PdfWriter()
    page = writer.add_blank_page(geometry["width_pt"], geometry["height_pt"])
    commands = ["1 0 0 RG 0.5 w"]
    for x in geometry["folds_pt"]:
        commands.append(f"{x} 0 m {x} {geometry['height_pt']} l S")
    for left, bottom, right, top in geometry["safe_panels_pt"]:
        commands.append(f"{left} {bottom} {right - left} {top - bottom} re S")
    if geometry["barcode_box_pt"]:
        left, bottom, right, top = geometry["barcode_box_pt"]
        commands.append(f"0 0 1 RG {left} {bottom} {right - left} {top - bottom} re S")
    stream = DecodedStreamObject()
    stream.set_data("\n".join(commands).encode())
    page.replace_contents(stream)
    writer.add_metadata(
        {"/Title": "DIMENSION PROOF — NOT COVER ARTWORK", "/MathpubArtifactRole": "proof"}
    )
    writer.write(target)


def prepare_cover(spec_path: Path, destination: Path) -> dict:
    geometry = cover_geometry(spec_path)
    try:
        destination.mkdir()
        (destination / "geometry.json").write_text(
            json.dumps(geometry, indent=2, sort_keys=True) + "\n"
        )
        (destination / "geometry.tex").write_text(cover_preamble(geometry) + "\n")
        _guides(geometry, destination / "dimension-proof.pdf")
        return geometry
    except OSError as error:
        raise MathpubError(
            "MP-COVER-002", f"cannot publish cover specification: {error}"
        ) from error


def check_cover(spec_path: Path, artwork: Path, prepared: Path | None = None) -> dict:
    geometry = cover_geometry(spec_path)
    if prepared is not None and json.loads(prepared.read_text()) != geometry:
        raise MathpubError("MP-COVER-003", "prepared cover is stale relative to interior/profile")
    data = artwork.read_bytes()
    reader = PdfReader(io.BytesIO(data))
    if (reader.metadata or {}).get("/MathpubArtifactRole") == "proof":
        raise MathpubError("MP-COVER-003", "dimension proof is not upload artwork")
    if len(reader.pages) != 1:
        raise MathpubError("MP-COVER-003", "cover artwork must have exactly one page")
    page = reader.pages[0]
    if (
        page.rotation
        or page.user_unit != 1
        or any(
            abs(a - b) > 0.01
            for a, b in zip(
                [float(page.mediabox.width), float(page.mediabox.height)],
                [geometry["width_pt"], geometry["height_pt"]],
                strict=True,
            )
        )
    ):
        raise MathpubError("MP-COVER-003", "cover artwork geometry does not match profile")
    outside, barcode_overlap = [], []
    for word in text_pages(data)[0]["words"]:
        x0, y0, x1, y1 = word["box"]
        box = [x0, geometry["height_pt"] - y1, x1, geometry["height_pt"] - y0]
        regions = list(geometry["safe_panels_pt"])
        safe = geometry["profile"]["safe_pt"]
        folds = geometry["folds_pt"]
        if folds[1] - folds[0] > 2 * safe:
            regions.append([folds[0] + safe, safe, folds[1] - safe, geometry["height_pt"] - safe])
        if not any(
            box[0] >= r[0] and box[1] >= r[1] and box[2] <= r[2] and box[3] <= r[3] for r in regions
        ):
            outside.append(word)
        barcode = geometry["barcode_box_pt"]
        if (
            barcode
            and box[0] < barcode[2]
            and box[2] > barcode[0]
            and box[1] < barcode[3]
            and box[3] > barcode[1]
        ):
            barcode_overlap.append(word)
    result = {
        "geometry": geometry,
        "artwork_sha256": sha256(data),
        "outside_safe_text": outside,
        "barcode_text_overlap": barcode_overlap,
        "passed": not outside and not barcode_overlap,
        "limitation": "Text bounds do not establish artwork or barcode scan safety.",
    }
    if not result["passed"]:
        raise MathpubError(
            "MP-COVER-003", "cover text violates safe regions", details={"report": result}
        )
    return result
