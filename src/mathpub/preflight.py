"""Read-only PDF measurements and explicit, library-owned print policies.

No printer requirements are built in. Measurements are not PDF/X certification.
Stroke bounds are singular values of the paint transform, not an estimate based
on just the two coordinate axes (which is wrong for shear transforms).
"""

from __future__ import annotations

import hashlib
import io
import math
from pathlib import Path
from typing import Any

import jsonschema
import pypdf
from pypdf import PdfReader
from pypdf.generic import ContentStream

from mathpub import __version__
from mathpub.config import load_toml, schema_definition
from mathpub.errors import MathpubError

IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
RULES = (
    "page_count",
    "trim",
    "embedded_fonts",
    "min_font",
    "min_stroke",
    "text_safe",
    "blank_pages",
    "grayscale",
    "content",
)


def _multiply(a, b):
    return (
        a[0] * b[0] + a[1] * b[2],
        a[0] * b[1] + a[1] * b[3],
        a[2] * b[0] + a[3] * b[2],
        a[2] * b[1] + a[3] * b[3],
        a[4] * b[0] + a[5] * b[2] + b[4],
        a[4] * b[1] + a[5] * b[3] + b[5],
    )


def _scales(matrix):
    a, b, c, d = matrix[:4]
    # Stable largest singular value; product of singular values is |det|.
    largest = (math.hypot(a + d, b - c) + math.hypot(a - d, b + c)) / 2
    return (abs(a * d - b * c) / largest if largest else 0.0, largest)


def _embedded(font):
    font = font.get_object()
    if font.get("/Subtype") == "/Type3":
        return bool(font.get("/CharProcs"))
    children = font.get("/DescendantFonts")
    if children is not None:
        return bool(children) and all(_embedded(child) for child in children)
    descriptor = font.get("/FontDescriptor")
    return descriptor is not None and any(
        key in descriptor.get_object() for key in ("/FontFile", "/FontFile2", "/FontFile3")
    )


def _page_marks(page, reader):
    fonts, strokes, unsupported = [], [], set()
    state = {"matrix": IDENTITY, "width": 1.0, "font": None, "size": 0.0, "mode": 0}

    def walk(stream, resources, initial, ancestors=()):
        if stream is None:
            return
        if len(ancestors) >= 32 or id(stream) in ancestors:
            raise ValueError("cyclic or excessively nested PDF Form XObject")
        ancestors = (*ancestors, id(stream))
        state = initial.copy()
        stack = []
        text_matrix = IDENTITY
        path_started = False
        for operands, operator in ContentStream(stream, reader).operations:
            if operator == b"q":
                stack.append(state.copy())
            elif operator == b"Q":
                if not stack:
                    raise ValueError("unbalanced graphics-state restore")
                if path_started and state["matrix"] != stack[-1]["matrix"]:
                    unsupported.add("transform changes inside a painted path")
                state = stack.pop()
            elif operator == b"cm":
                state["matrix"] = _multiply(tuple(map(float, operands)), state["matrix"])
                if path_started:
                    unsupported.add("transform changes inside a painted path")
            elif operator == b"w":
                state["width"] = abs(float(operands[0]))
            elif operator == b"gs":
                ext = resources["/ExtGState"][operands[0]].get_object()
                if "/LW" in ext:
                    state["width"] = abs(float(ext["/LW"]))
                if "/Font" in ext:
                    state["font"], state["size"] = ext["/Font"]
                    state["size"] = float(state["size"])
                if ext.get("/SMask", "/None") != "/None":
                    unsupported.add("soft-mask content")
            elif operator == b"BT":
                text_matrix = IDENTITY
            elif operator == b"Tm":
                text_matrix = tuple(map(float, operands))
            elif operator == b"Tf":
                state["font"] = resources["/Font"][operands[0]].get_object()
                state["size"] = float(operands[1])
            elif operator == b"Tr":
                state["mode"] = int(operands[0])
            elif operator in (b"Tj", b"TJ", b"'", b'"'):
                values = operands[0] if operator == b"TJ" else operands[-1:]
                if state["mode"] != 3 and any(
                    isinstance(value, (str, bytes)) and value for value in values
                ):
                    if state["mode"] in (1, 2, 5, 6):
                        unsupported.add("stroked text glyphs")
                    font = state["font"]
                    if font is None:
                        unsupported.add("text without a resolved font")
                        continue
                    font = font.get_object()
                    transform = _multiply(text_matrix, state["matrix"])
                    size = abs(state["size"]) * math.hypot(transform[2], transform[3])
                    if font.get("/Subtype") == "/Type3":
                        unsupported.add("Type 3 glyph metrics and drawing content")
                    fonts.append(
                        {
                            "name": str(font.get("/BaseFont", font.get("/Subtype", "unknown"))),
                            "embedded": _embedded(font),
                            "size_pt": size * float(page.user_unit),
                        }
                    )
            elif operator in (b"m", b"l", b"c", b"v", b"y", b"re"):
                path_started = True
            elif operator in (b"S", b"s", b"B", b"B*", b"b", b"b*"):
                low, high = _scales(state["matrix"])
                width = state["width"] * float(page.user_unit)
                if path_started:
                    strokes.append({"min_pt": width * low, "max_pt": width * high})
                path_started = False
            elif operator in (b"n", b"f", b"F", b"f*"):
                path_started = False
            elif operator in (b"SCN", b"scn"):
                if any(isinstance(value, str) and value.startswith("/") for value in operands):
                    unsupported.add("pattern drawing content")
            elif operator == b"Do":
                obj = resources["/XObject"][operands[0]].get_object()
                if obj.get("/Subtype") == "/Form":
                    child_state = state.copy()
                    child_state["matrix"] = _multiply(
                        tuple(map(float, obj.get("/Matrix", IDENTITY))), state["matrix"]
                    )
                    walk(obj, obj.get("/Resources", resources), child_state, ancestors)
        if stack:
            raise ValueError("unbalanced graphics-state save")

    if page.get("/Annots"):
        unsupported.add("annotation appearances")
    walk(page.get_contents(), page.get("/Resources", {}), state)
    return fonts, strokes, sorted(unsupported)


def inspect_pdf(path: Path) -> dict[str, Any]:
    """Measure a single immutable byte snapshot; never modify or rebuild its source."""
    try:
        payload = path.read_bytes()
        reader = PdfReader(io.BytesIO(payload), strict=True)
        if reader.is_encrypted:
            raise ValueError("encrypted PDFs are not supported")
        if not reader.pages:
            raise ValueError("PDF has no pages")
        pages = []
        for number, page in enumerate(reader.pages, 1):
            unit = float(page.user_unit)
            if not math.isfinite(unit) or unit <= 0:
                raise ValueError("invalid PDF UserUnit")
            fonts, strokes, unsupported = _page_marks(page, reader)
            boxes = {
                name: [float(value) * unit for value in getattr(page, name)]
                for name in ("mediabox", "cropbox", "trimbox", "bleedbox", "artbox")
            }
            if not all(math.isfinite(value) for box in boxes.values() for value in box):
                raise ValueError("non-finite PDF page geometry")
            for box in boxes.values():
                if box[2] <= box[0] or box[3] <= box[1]:
                    raise ValueError("empty or reversed PDF page box")
            if not all(math.isfinite(font["size_pt"]) for font in fonts) or not all(
                math.isfinite(value) for stroke in strokes for value in stroke.values()
            ):
                raise ValueError("non-finite PDF drawing measurement")
            rotation = int(page.rotation) % 360
            if rotation % 90:
                raise ValueError("page rotation must be a multiple of 90 degrees")
            trim = boxes["trimbox"]
            width, height = trim[2] - trim[0], trim[3] - trim[1]
            if rotation in (90, 270):
                width, height = height, width
            pages.append(
                {
                    "page": number,
                    "rotation": rotation,
                    "user_unit": unit,
                    "boxes_pt": boxes,
                    "trim_width_pt": width,
                    "trim_height_pt": height,
                    "fonts": fonts,
                    "strokes": strokes,
                    "unsupported_content": unsupported,
                }
            )
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        RecursionError,
        AttributeError,
        OverflowError,
    ) as error:
        raise MathpubError("MP-PREFLIGHT-001", f"cannot inspect PDF {path}: {error}") from error
    except pypdf.errors.PyPdfError as error:
        raise MathpubError("MP-PREFLIGHT-001", f"cannot inspect PDF {path}: {error}") from error
    return {
        "schema": 1,
        "artifact": {
            "path": str(path),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
        },
        "tools": {"mathpub": __version__, "pypdf": pypdf.__version__},
        "page_count": len(pages),
        "pages": pages,
    }


def preflight_pdf(path: Path, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """Apply opt-in rules; uncertain requested measurements fail closed.

    Libraries can consume ``inspect_pdf`` separately for semantic rules. This
    function returns all findings, including failures, without raising for policy
    violations. Only invalid inputs raise MathpubError.
    """
    profile = {"schema": 1, "id": "inspection-only"} if profile is None else dict(profile)
    try:
        jsonschema.validate(profile, schema_definition("preflight"))
        if any(isinstance(v, float) and not math.isfinite(v) for v in profile.values()):
            raise ValueError("profile values must be finite")
    except (jsonschema.ValidationError, ValueError) as error:
        raise MathpubError("MP-PREFLIGHT-002", f"invalid preflight profile: {error}") from error
    report = inspect_pdf(path)
    checks = []
    enabled = set()
    tolerance = profile.get("tolerance_pt", 0.01)

    def check(rule, page, measured, expected, status):
        enabled.add(rule)
        checks.append(
            {
                "rule": rule,
                "page": page,
                "measured": measured,
                "expected": expected,
                "status": status,
            }
        )

    if "page_count" in profile:
        check(
            "page_count",
            None,
            report["page_count"],
            profile["page_count"],
            "pass" if report["page_count"] == profile["page_count"] else "fail",
        )
    for page in report["pages"]:
        number = page["page"]
        if "width_pt" in profile:
            expected = [profile["width_pt"], profile["height_pt"]]
            measured = [page["trim_width_pt"], page["trim_height_pt"]]
            check(
                "trim",
                number,
                measured,
                {"size_pt": expected, "tolerance_pt": tolerance},
                "pass"
                if all(abs(a - b) <= tolerance for a, b in zip(measured, expected, strict=True))
                else "fail",
            )
        for rule, key in (
            ("embedded_fonts", "require_embedded_fonts"),
            ("min_font", "min_font_pt"),
            ("min_stroke", "min_stroke_pt"),
        ):
            if not profile.get(key):
                continue
            if page["unsupported_content"]:
                check(rule, number, page["unsupported_content"], profile[key], "unresolved")
            values = page["strokes"] if rule == "min_stroke" else page["fonts"]
            if not values:
                check(rule, number, None, profile[key], "not-applicable")
            for value in values:
                if rule == "embedded_fonts":
                    status = "pass" if value["embedded"] else "fail"
                elif rule == "min_font":
                    status = "pass" if value["size_pt"] + tolerance >= profile[key] else "fail"
                elif value["max_pt"] == 0:
                    status = "fail"
                elif value["min_pt"] + tolerance >= profile[key]:
                    status = "pass"
                elif value["max_pt"] + tolerance < profile[key]:
                    status = "fail"
                else:
                    status = "unresolved"
                check(rule, number, value, profile[key], status)
    if any(
        key in profile
        for key in (
            "text_safe_margin_pt",
            "allowed_blank_pages",
            "require_grayscale",
            "content_expectations",
        )
    ):
        from mathpub.pdf_render import raster_measurements, renderer_versions, text_pages

        report["tools"].update(renderer_versions())

        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != report["artifact"]["sha256"]:
            raise MathpubError("MP-PREFLIGHT-001", "PDF changed during inspection")
        if "text_safe_margin_pt" in profile or "content_expectations" in profile:
            pages = text_pages(data)
            if len(pages) != report["page_count"]:
                raise MathpubError("MP-PREFLIGHT-001", "text extractor page count mismatch")
            for number, page in enumerate(pages, 1):
                if "text_safe_margin_pt" in profile:
                    left, top, right, bottom = profile["text_safe_margin_pt"]
                    safe = [left, top, page["width_pt"] - right, page["height_pt"] - bottom]
                    outside = [
                        word
                        for word in page["words"]
                        if not (
                            word["box"][0] >= safe[0] - tolerance
                            and word["box"][1] >= safe[1] - tolerance
                            and word["box"][2] <= safe[2] + tolerance
                            and word["box"][3] <= safe[3] + tolerance
                        )
                    ]
                    check(
                        "text_safe",
                        number,
                        outside,
                        safe,
                        "pass"
                        if not outside and safe[0] < safe[2] and safe[1] < safe[3]
                        else "fail",
                    )
            for expected in profile.get("content_expectations", []):
                number = expected["page"]
                actual = (
                    pages[number - 1]["text"].count(" ".join(expected["text"].split()))
                    if number <= len(pages)
                    else None
                )
                check(
                    "content",
                    number,
                    {"id": expected["id"], "count": actual},
                    expected,
                    "pass" if actual == expected.get("count", 1) else "fail",
                )
        if "allowed_blank_pages" in profile or profile.get("require_grayscale"):
            raster = raster_measurements(
                data,
                report["page_count"],
                profile.get("raster_dpi", 150),
                profile.get("ink_threshold", 250),
                profile.get("color_tolerance", 2),
            )
            report["raster"] = raster
            for page in raster:
                if "allowed_blank_pages" in profile:
                    check(
                        "blank_pages",
                        page["page"],
                        page["ink_pixels"],
                        {"allowed_blank": page["page"] in profile["allowed_blank_pages"]},
                        "pass"
                        if page["ink_pixels"] or page["page"] in profile["allowed_blank_pages"]
                        else "fail",
                    )
                if profile.get("require_grayscale"):
                    check(
                        "grayscale",
                        page["page"],
                        page["color_pixels"],
                        0,
                        "pass" if not page["color_pixels"] else "fail",
                    )
    report.update(
        {
            "profile": profile,
            "checks": checks,
            "passed": all(check["status"] not in ("fail", "unresolved") for check in checks),
            "checked_rules": sorted(enabled),
            "skipped_rules": sorted(set(RULES) - enabled),
            "limitations": [
                "Not PDF/X certification, printer acceptance, or editorial approval.",
                "Text bounds are not artwork safety; raster color is not PDF color-space proof.",
                "Font size is the transformed text em height, not visible glyph bounds.",
                "Stroke bounds are conservative; uncertain widths fail closed.",
                "Clipping, optional visibility, and text rendered as outlines are not interpreted.",
            ],
        }
    )
    return report


def preflight_command(path: Path, profile_path: Path | None = None) -> dict[str, Any]:
    profile = load_toml(profile_path, "preflight") if profile_path is not None else None
    report = preflight_pdf(path, profile)
    if not report["passed"]:
        raise MathpubError(
            "MP-PREFLIGHT-003",
            "PDF failed the requested preflight policy",
            details={"report": report},
        )
    return report
