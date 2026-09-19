"""Shared, explicit Poppler measurements for preflight, reviews and QR audits."""

from __future__ import annotations

import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from mathpub.errors import MathpubError


def run_pdf_tool(command: list[str], timeout: int = 120):
    try:
        return subprocess.run(command, capture_output=True, check=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as error:
        raise MathpubError("MP-PDF-020", f"PDF measurement failed: {command[0]}") from error


def render_page(pdf: Path, page: int, target: Path, dpi: int = 150) -> None:
    if page < 1 or not 36 <= dpi <= 600:
        raise MathpubError("MP-PDF-020", "invalid physical page or render DPI (36–600)")
    target.parent.mkdir(parents=True, exist_ok=True)
    run_pdf_tool(
        [
            "pdftocairo",
            "-png",
            "-singlefile",
            "-f",
            str(page),
            "-l",
            str(page),
            "-r",
            str(dpi),
            str(pdf),
            str(target.with_suffix("")),
        ]
    )
    if not target.is_file():
        raise MathpubError("MP-PDF-020", "renderer did not produce the requested page")


def text_pages(data: bytes) -> list[dict]:
    with tempfile.TemporaryDirectory(prefix="mathpub-text-") as temp:
        path = Path(temp) / "input.pdf"
        path.write_bytes(data)
        result = run_pdf_tool(["pdftotext", "-cropbox", "-bbox-layout", str(path), "-"])
    try:
        root = ET.fromstring(result.stdout)
        pages = []
        for node in root.iter():
            if node.tag.rsplit("}", 1)[-1] != "page":
                continue
            words = [
                {
                    "text": "".join(word.itertext()),
                    "box": [float(word.attrib[key]) for key in ("xMin", "yMin", "xMax", "yMax")],
                }
                for word in node.iter()
                if word.tag.rsplit("}", 1)[-1] == "word"
            ]
            pages.append(
                {
                    "width_pt": float(node.attrib["width"]),
                    "height_pt": float(node.attrib["height"]),
                    "words": words,
                    "text": " ".join(word["text"] for word in words),
                }
            )
        return pages
    except (ET.ParseError, KeyError, ValueError) as error:
        raise MathpubError("MP-PDF-020", "invalid text geometry from Poppler") from error


def raster_measurements(
    data: bytes, pages: int, dpi: int = 150, ink_threshold: int = 250, color_tolerance: int = 2
) -> list[dict]:
    from PIL import Image, ImageChops

    results = []
    with tempfile.TemporaryDirectory(prefix="mathpub-raster-") as temp:
        pdf, png = Path(temp) / "input.pdf", Path(temp) / "page.png"
        pdf.write_bytes(data)
        for number in range(1, pages + 1):
            render_page(pdf, number, png, dpi)
            with Image.open(png) as image:
                red, green, blue = image.convert("RGB").split()
                minimum = ImageChops.darker(ImageChops.darker(red, green), blue)
                maximum = ImageChops.lighter(ImageChops.lighter(red, green), blue)
                ink = sum(minimum.histogram()[:ink_threshold])
                colored = sum(
                    ImageChops.subtract(maximum, minimum).histogram()[color_tolerance + 1 :]
                )
                count = image.width * image.height
                results.append(
                    {
                        "page": number,
                        "pixels": count,
                        "ink_pixels": ink,
                        "color_pixels": colored,
                        "dpi": dpi,
                    }
                )
    return results
