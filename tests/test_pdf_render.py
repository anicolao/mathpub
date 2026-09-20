from mathpub.preflight import preflight_pdf
from tests.test_preflight import pdf, policy, statuses


def test_raster_detects_graphics_only_nonblank_and_color(tmp_path):
    path = pdf(tmp_path, b"1 0 0 rg 10 10 50 50 re f")
    report = preflight_pdf(
        path, policy(allowed_blank_pages=[], require_grayscale=True, raster_dpi=36)
    )
    assert statuses(report, "blank_pages") == ["pass"]
    assert statuses(report, "grayscale") == ["fail"]
    assert report["raster"][0]["color_pixels"] > 0


def test_blanks_require_explicit_permission(tmp_path):
    path = pdf(tmp_path)
    assert not preflight_pdf(path, policy(allowed_blank_pages=[], raster_dpi=36))["passed"]
    assert preflight_pdf(path, policy(allowed_blank_pages=[1], raster_dpi=36))["passed"]


def test_text_safe_regions_and_semantic_expectations(tmp_path):
    path = pdf(tmp_path, b"BT /F1 12 Tf 5 300 Td (Chapter One) Tj ET")
    report = preflight_pdf(
        path,
        policy(
            text_safe_margin_pt=[20, 20, 20, 20],
            content_expectations=[{"id": "chapter", "page": 1, "text": "Chapter One"}],
        ),
    )
    assert statuses(report, "text_safe") == ["fail"]
    assert statuses(report, "content") == ["pass"]
