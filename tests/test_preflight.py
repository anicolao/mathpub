import hashlib
import json

import pytest
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    RectangleObject,
)

from mathpub.cli import main
from mathpub.errors import MathpubError
from mathpub.preflight import inspect_pdf, preflight_pdf


def pdf(tmp_path, content=b"", *, width=432, height=648, configure=None):
    writer = PdfWriter()
    page = writer.add_blank_page(width, height)
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {
                    NameObject("/F1"): DictionaryObject(
                        {
                            NameObject("/Type"): NameObject("/Font"),
                            NameObject("/Subtype"): NameObject("/Type1"),
                            NameObject("/BaseFont"): NameObject("/Helvetica"),
                        }
                    ),
                }
            ),
        }
    )
    stream = DecodedStreamObject()
    stream.set_data(content)
    page.replace_contents(stream)
    if configure:
        configure(page)
    path = tmp_path / "sample.pdf"
    writer.write(path)
    return path


def policy(**kwargs):
    return {"schema": 1, "id": "synthetic-test", **kwargs}


def statuses(report, rule):
    return [check["status"] for check in report["checks"] if check["rule"] == rule]


def test_inspection_is_hash_bound_read_only_and_has_no_printer_defaults(tmp_path):
    path = pdf(tmp_path)
    original = path.read_bytes()
    report = preflight_pdf(path)
    assert report["passed"]
    assert report["checked_rules"] == []
    assert len(report["skipped_rules"]) == 9
    assert report["artifact"]["sha256"] == hashlib.sha256(original).hexdigest()
    assert report["artifact"]["bytes"] == len(original)
    assert report["pages"][0]["trim_width_pt"] == 432
    assert path.read_bytes() == original
    assert sorted(p.name for p in tmp_path.iterdir()) == ["sample.pdf"]


@pytest.mark.parametrize("width,height", [(432, 648), (576, 720), (210, 297)])
def test_trim_policy_is_not_book_specific(tmp_path, width, height):
    path = pdf(tmp_path, width=width, height=height)
    assert preflight_pdf(path, policy(width_pt=width, height_pt=height))["passed"]
    report = preflight_pdf(path, policy(width_pt=width + 1, height_pt=height, page_count=2))
    assert not report["passed"]
    assert statuses(report, "trim") == ["fail"]
    assert statuses(report, "page_count") == ["fail"]


def test_trim_uses_offsets_rotation_and_user_units(tmp_path):
    def configure(page):
        page[NameObject("/TrimBox")] = RectangleObject([10, 20, 110, 220])
        page[NameObject("/UserUnit")] = FloatObject(2)
        page.rotate(90)

    path = pdf(tmp_path, configure=configure)
    report = preflight_pdf(path, policy(width_pt=400, height_pt=200))
    assert report["passed"]
    assert report["pages"][0]["boxes_pt"]["trimbox"] == [20, 40, 220, 440]


def test_text_matrix_and_graphics_state_scale_font_size(tmp_path):
    path = pdf(tmp_path, b"q 2 0 0 3 0 0 cm BT /F1 10 Tf 0 1 -1 0 0 0 Tm (Hello) Tj ET Q")
    report = preflight_pdf(path, policy(min_font_pt=21, require_embedded_fonts=True))
    assert report["pages"][0]["fonts"][0]["size_pt"] == 20
    assert statuses(report, "min_font") == ["fail"]
    assert statuses(report, "embedded_fonts") == ["fail"]


def test_embedded_font_descriptor_is_recognized(tmp_path):
    def configure(page):
        # Synthetic stream tests embedding presence, not font-program validity.
        font_file = DecodedStreamObject()
        font_file.set_data(b"synthetic font program")
        page["/Resources"]["/Font"]["/F1"][NameObject("/FontDescriptor")] = DictionaryObject(
            {
                NameObject("/FontFile"): font_file,
            }
        )

    path = pdf(tmp_path, b"BT /F1 12 Tf (Hello) Tj ET", configure=configure)
    assert preflight_pdf(path, policy(require_embedded_fonts=True, min_font_pt=12))["passed"]


def test_invisible_text_and_unused_fonts_are_not_measured(tmp_path):
    path = pdf(tmp_path, b"BT /F1 1 Tf 3 Tr (hidden) Tj ET")
    report = preflight_pdf(path, policy(require_embedded_fonts=True, min_font_pt=10))
    assert report["passed"]
    assert statuses(report, "min_font") == ["not-applicable"]


def test_nested_forms_inherit_transform_width_and_font_resources(tmp_path):
    def configure(page):
        inner = DecodedStreamObject()
        inner.set_data(b"0 0 m 10 10 l S BT /F1 10 Tf (inside) Tj ET")
        inner[NameObject("/Subtype")] = NameObject("/Form")
        inner[NameObject("/BBox")] = RectangleObject([0, 0, 100, 100])
        inner[NameObject("/Matrix")] = ArrayObject([NumberObject(v) for v in (2, 0, 0, 2, 0, 0)])
        outer = DecodedStreamObject()
        outer.set_data(b"/Inner Do")
        outer[NameObject("/Subtype")] = NameObject("/Form")
        outer[NameObject("/BBox")] = RectangleObject([0, 0, 100, 100])
        page["/Resources"][NameObject("/XObject")] = DictionaryObject(
            {
                NameObject("/Inner"): inner,
                NameObject("/Outer"): outer,
            }
        )

    path = pdf(tmp_path, b"q 3 0 0 3 0 0 cm 0.25 w /Outer Do Q", configure=configure)
    report = preflight_pdf(path, policy(min_font_pt=60, min_stroke_pt=1.5))
    assert report["passed"]
    assert report["pages"][0]["fonts"][0]["size_pt"] == 60
    assert report["pages"][0]["strokes"] == [{"min_pt": 1.5, "max_pt": 1.5}]


@pytest.mark.parametrize(
    "matrix,minimum,status",
    [
        ("0 1 -1 0", 1, "pass"),
        ("1 0 0 1", 1.1, "fail"),
        ("1 0 0 2", 1.5, "unresolved"),
        ("1 0 1 1", 0.9, "unresolved"),
        ("1 0 1 1", 0.5, "pass"),
    ],
)
def test_stroke_bounds_handle_rotation_nonuniform_scaling_and_shear(
    tmp_path, matrix, minimum, status
):
    path = pdf(tmp_path, f"{matrix} 0 0 cm 1 w 0 0 m 10 0 l S".encode())
    report = preflight_pdf(path, policy(min_stroke_pt=minimum))
    assert statuses(report, "min_stroke") == [status]
    assert report["passed"] is (status == "pass")


def test_graphics_state_restore_and_extgstate_line_width(tmp_path):
    def configure(page):
        page["/Resources"][NameObject("/ExtGState")] = DictionaryObject(
            {
                NameObject("/Thin"): DictionaryObject({NameObject("/LW"): FloatObject(0.1)}),
            }
        )

    path = pdf(tmp_path, b"q /Thin gs 0 0 m 10 0 l S Q 0 0 m 10 0 l S", configure=configure)
    report = preflight_pdf(path, policy(min_stroke_pt=0.5))
    assert statuses(report, "min_stroke") == ["fail", "pass"]


def test_device_hairline_is_not_print_safe(tmp_path):
    path = pdf(tmp_path, b"0 w 0 0 m 10 0 l S")
    assert not preflight_pdf(path, policy(min_stroke_pt=0.5))["passed"]
    assert not preflight_pdf(path, policy(min_stroke_pt=0.001))["passed"]


def test_every_page_is_checked(tmp_path):
    writer = PdfWriter()
    writer.add_blank_page(432, 648)
    writer.add_blank_page(576, 720)
    path = tmp_path / "mixed.pdf"
    writer.write(path)
    report = preflight_pdf(path, policy(width_pt=432, height_pt=648, page_count=2))
    assert statuses(report, "trim") == ["pass", "fail"]
    assert report["checks"][-1]["page"] == 2


def test_excessive_form_nesting_is_a_structured_error(tmp_path):
    def configure(page):
        form = None
        for _ in range(34):
            parent = DecodedStreamObject()
            parent[NameObject("/Subtype")] = NameObject("/Form")
            parent[NameObject("/BBox")] = RectangleObject([0, 0, 10, 10])
            if form is not None:
                parent.set_data(b"/Nested Do")
                parent[NameObject("/Resources")] = DictionaryObject(
                    {
                        NameObject("/XObject"): DictionaryObject({NameObject("/Nested"): form}),
                    }
                )
            else:
                parent.set_data(b"")
            form = parent
        page["/Resources"][NameObject("/XObject")] = DictionaryObject({NameObject("/Top"): form})

    path = pdf(tmp_path, b"/Top Do", configure=configure)
    with pytest.raises(MathpubError, match="excessively nested"):
        inspect_pdf(path)


@pytest.mark.parametrize("content", [b"Q", b"q", b"BT /Missing 12 Tf (Hi) Tj ET"])
def test_malformed_drawing_state_is_a_structured_error(tmp_path, content):
    with pytest.raises(MathpubError) as caught:
        inspect_pdf(pdf(tmp_path, content))
    assert caught.value.code == "MP-PREFLIGHT-001"


def test_stroked_text_is_not_silently_omitted(tmp_path):
    path = pdf(tmp_path, b"BT /F1 12 Tf 1 Tr (outlined) Tj ET")
    report = preflight_pdf(path, policy(min_stroke_pt=1))
    assert not report["passed"]
    assert "stroked text glyphs" in report["pages"][0]["unsupported_content"]


def test_transform_changed_during_path_is_unresolved(tmp_path):
    path = pdf(tmp_path, b"0 0 m 2 0 0 2 0 0 cm 10 10 l S")
    report = preflight_pdf(path, policy(min_stroke_pt=0.5))
    assert "unresolved" in statuses(report, "min_stroke")
    assert not report["passed"]


def test_annotation_appearances_are_explicitly_unresolved(tmp_path):
    def configure(page):
        page[NameObject("/Annots")] = ArrayObject(
            [
                DictionaryObject(
                    {
                        NameObject("/Subtype"): NameObject("/Text"),
                        NameObject("/Rect"): RectangleObject([0, 0, 10, 10]),
                    }
                )
            ]
        )

    path = pdf(tmp_path, configure=configure)
    report = preflight_pdf(path, policy(require_embedded_fonts=True))
    assert not report["passed"]
    assert "annotation appearances" in report["pages"][0]["unsupported_content"]


@pytest.mark.parametrize(
    "values",
    [
        {"width_pt": 0, "height_pt": 10},
        {"width_pt": 20},
        {"page_count": True},
        {"min_stroke_pt": -1},
        {"tolerance_pt": float("nan")},
        {"unknown": True},
    ],
)
def test_invalid_policies_are_rejected(tmp_path, values):
    with pytest.raises(MathpubError):
        preflight_pdf(pdf(tmp_path), policy(**values))


@pytest.mark.parametrize("content", [b"not a PDF", b"%PDF-1.7\ntruncated"])
def test_invalid_pdf_is_a_structured_error(tmp_path, content):
    path = tmp_path / "broken.pdf"
    path.write_bytes(content)
    with pytest.raises(MathpubError) as caught:
        inspect_pdf(path)
    assert caught.value.code == "MP-PREFLIGHT-001"


def test_encrypted_pdf_is_rejected(tmp_path):
    writer = PdfWriter()
    writer.add_blank_page(100, 100)
    writer.encrypt("password")
    path = tmp_path / "locked.pdf"
    writer.write(path)
    with pytest.raises(MathpubError, match="encrypted"):
        inspect_pdf(path)


def test_cli_operates_outside_a_project_and_returns_failure_report(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    path = pdf(tmp_path)
    assert main(["preflight", str(path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["artifact"]["sha256"]
    profile = tmp_path / "policy.toml"
    profile.write_text('schema = 1\nid = "two-pages"\npage_count = 2\n')
    assert main(["preflight", str(path), "--profile", str(profile), "--json"]) == 3
    error = json.loads(capsys.readouterr().out)["error"]
    assert error["code"] == "MP-PREFLIGHT-003"
    assert not error["details"]["report"]["passed"]


def test_invalid_profile_cli_reports_source_error(tmp_path, capsys):
    profile = tmp_path / "policy.toml"
    profile.write_text('schema = 1\nid = "typo"\nmin_storke_pt = 1\n')
    assert main(["preflight", str(pdf(tmp_path)), "--profile", str(profile), "--json"]) == 3
    assert json.loads(capsys.readouterr().out)["status"] == "error"
