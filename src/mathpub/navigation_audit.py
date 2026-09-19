"""Vector QR assets and placement-keyed rendered QR/link/bookmark audits."""

from __future__ import annotations

import html
import io
import math
import tempfile
from collections import Counter
from pathlib import Path

import qrcode
import zxingcpp
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject

from mathpub.config import load_toml
from mathpub.errors import MathpubError
from mathpub.pdf_render import render_page
from mathpub.releases import sha256


def render_qr(payload: str, output: Path, size_pt: float = 72) -> dict:
    if not payload or not math.isfinite(size_pt) or size_pt <= 0:
        raise MathpubError("MP-QR-001", "QR payload and positive finite size are required")
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4)
    try:
        qr.add_data(payload)
        qr.make(fit=True)
        matrix = qr.get_matrix()
        count = len(matrix)
        step = size_pt / count
        cells = [
            (x, count - y - 1)
            for y, row in enumerate(matrix)
            for x, filled in enumerate(row)
            if filled
        ]
        if output.suffix == ".pdf":
            writer = PdfWriter()
            page = writer.add_blank_page(size_pt, size_pt)
            stream = DecodedStreamObject()
            stream.set_data(
                (
                    "0 g\n"
                    + "\n".join(
                        f"{x * step:.8f} {y * step:.8f} {step:.8f} {step:.8f} re f"
                        for x, y in cells
                    )
                ).encode()
            )
            page.replace_contents(stream)
            memory = io.BytesIO()
            writer.write(memory)
            data = memory.getvalue()
        elif output.suffix == ".tex":
            data = (
                rf"\begin{{tikzpicture}}[x={step}bp,y={step}bp]"
                + "\n"
                + rf"\path[use as bounding box] (0,0) rectangle ({count},{count});"
                + "\n"
                + "\n".join(rf"\fill ({x},{y}) rectangle ++(1,1);" for x, y in cells)
                + "\n"
                + r"\end{tikzpicture}"
                + "\n"
            ).encode()
        elif output.suffix == ".svg":
            paths = " ".join(f"M{x},{count - y - 1}h1v1h-1z" for x, y in cells)
            data = (
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{size_pt}pt" '
                f'height="{size_pt}pt" viewBox="0 0 {count} {count}">'
                f"<title>{html.escape(payload)}</title>"
                '<rect width="100%" height="100%" fill="white"/>'
                f'<path d="{paths}" fill="black"/></svg>'
            ).encode()
        else:
            raise ValueError("QR output suffix must be .pdf, .svg, or .tex")
        with output.open("xb") as stream:
            stream.write(data)
        return {
            "payload": payload,
            "path": str(output),
            "sha256": sha256(data),
            "size_pt": size_pt,
            "modules": count,
            "quiet_zone_modules": 4,
        }
    except (OSError, ValueError, qrcode.exceptions.DataOverflowError) as error:
        raise MathpubError("MP-QR-001", f"cannot render QR: {error}") from error


def _destination(reader, value):
    if isinstance(value, str):
        destination = reader.named_destinations.get(value)
        return reader.get_destination_page_number(destination) + 1 if destination else None
    if isinstance(value, list) and value:
        for number, page in enumerate(reader.pages, 1):
            if value[0] == page.indirect_reference:
                return number
    return None


def audit_navigation(pdf: Path, expectation_path: Path) -> dict:
    config = load_toml(expectation_path, "navigation")
    data = pdf.read_bytes()
    reader = PdfReader(io.BytesIO(data))
    checks = []
    ids = [record["id"] for key in ("qr", "links", "bookmarks") for record in config.get(key, [])]
    if len(ids) != len(set(ids)):
        raise MathpubError("MP-NAV-001", "placement IDs must be unique")

    def check(rule, measured, expected, placement=None):
        checks.append(
            {
                "rule": rule,
                "placement": placement,
                "measured": measured,
                "expected": expected,
                "passed": measured == expected,
            }
        )

    if "qr" in config:
        observed = Counter()
        dpi = config.get("dpi", 300)
        with tempfile.TemporaryDirectory(prefix="mathpub-qr-") as temp:
            source, image_path = Path(temp) / "input.pdf", Path(temp) / "page.png"
            source.write_bytes(data)
            for number in range(1, len(reader.pages) + 1):
                render_page(source, number, image_path, dpi)
                with Image.open(image_path) as image:
                    codes = zxingcpp.read_barcodes(image, formats=zxingcpp.BarcodeFormat.QRCode)
                    observed.update((number, code.text) for code in codes)
                    for record in config["qr"]:
                        if record["page"] != number or "box_pt" not in record:
                            continue
                        box = tuple(round(value * dpi / 72) for value in record["box_pt"])
                        if (
                            box[0] >= box[2]
                            or box[1] >= box[3]
                            or min(box) < 0
                            or box[2] > image.width
                            or box[3] > image.height
                        ):
                            raise MathpubError(
                                "MP-NAV-001", "QR placement box lies outside rendered page"
                            )
                        found = [
                            code.text
                            for code in zxingcpp.read_barcodes(
                                image.crop(box), formats=zxingcpp.BarcodeFormat.QRCode
                            )
                        ]
                        check(
                            "qr-placement",
                            found.count(record["payload"]),
                            record.get("count", 1),
                            record["id"],
                        )
        expected = Counter()
        for record in config["qr"]:
            expected[record["page"], record["payload"]] += record.get("count", 1)
        for item in sorted(set(observed) | set(expected)):
            check("qr-count", observed[item], expected[item], {"page": item[0], "payload": item[1]})

    if "links" in config:
        observed = Counter()
        for number, page in enumerate(reader.pages, 1):
            for ref in page.get("/Annots", []):
                annotation = ref.get_object()
                if annotation.get("/Subtype") != "/Link":
                    continue
                action = annotation.get("/A", {})
                if hasattr(action, "get_object"):
                    action = action.get_object()
                if action.get("/S") == "/URI":
                    target = str(action.get("/URI"))
                else:
                    target = _destination(reader, annotation.get("/Dest", action.get("/D")))
                observed[number, str(target)] += 1
        expected = Counter()
        for record in config["links"]:
            expected[record["page"], str(record.get("uri", record.get("destination_page")))] += (
                record.get("count", 1)
            )
        for item in sorted(set(observed) | set(expected)):
            check(
                "link-count", observed[item], expected[item], {"page": item[0], "target": item[1]}
            )

    if "bookmarks" in config:
        observed = Counter()

        def walk(items):
            for item in items:
                if isinstance(item, list):
                    walk(item)
                else:
                    page = reader.get_destination_page_number(item)
                    observed[str(item.title), page + 1 if page is not None else None] += 1

        walk(reader.outline)
        expected = Counter((record["title"], record["page"]) for record in config["bookmarks"])
        for item in sorted(set(observed) | set(expected), key=str):
            check(
                "bookmark-count",
                observed[item],
                expected[item],
                {"title": item[0], "page": item[1]},
            )
        for record in config["bookmarks"]:
            if "text" in record:
                number = record["page"]
                text = (
                    reader.pages[number - 1].extract_text() if number <= len(reader.pages) else ""
                )
                check(
                    "bookmark-text",
                    record["text"] in " ".join((text or "").split()),
                    True,
                    record["id"],
                )
    report = {
        "schema": 1,
        "pdf_sha256": sha256(data),
        "expectations_sha256": sha256(expectation_path.read_bytes()),
        "dpi": config.get("dpi", 300),
        "checks": checks,
        "passed": all(c["passed"] for c in checks),
        "skipped": [key for key in ("qr", "links", "bookmarks") if key not in config],
        "limitations": [
            "Raster decoding is not a phone-camera guarantee.",
            "Destination text matching is heuristic, not proof of an exact anchor.",
        ],
    }
    if not report["passed"]:
        raise MathpubError("MP-NAV-002", "navigation audit failed", details={"report": report})
    return report
