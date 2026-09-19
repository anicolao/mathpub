import pytest
from pypdf import PdfWriter
from pypdf.annotations import Link

from mathpub.errors import MathpubError
from mathpub.navigation_audit import audit_navigation, render_qr


def test_vector_qr_decodes_and_missing_duplicate_unexpected_counts_fail(tmp_path):
    pdf = tmp_path / "qr.pdf"
    render_qr("https://example.invalid/check", pdf, 100)
    expected = tmp_path / "expected.toml"
    expected.write_text("""schema=1
[[qr]]
id="question-one"
page=1
payload="https://example.invalid/check"
box_pt=[0,0,100,100]
""")
    assert audit_navigation(pdf, expected)["passed"]
    expected.write_text(expected.read_text().replace("page=1", "page=1\ncount=2"))
    with pytest.raises(MathpubError, match="audit failed"):
        audit_navigation(pdf, expected)
    expected.write_text("schema=1\nqr=[]\n")
    with pytest.raises(MathpubError, match="audit failed"):
        audit_navigation(pdf, expected)


def test_links_and_bookmarks_resolve_destinations(tmp_path):
    writer = PdfWriter()
    writer.add_blank_page(100, 100)
    writer.add_blank_page(100, 100)
    writer.add_annotation(0, Link(rect=(0, 0, 30, 30), url="https://example.invalid"))
    writer.add_outline_item("Answers", 1)
    pdf = tmp_path / "book.pdf"
    writer.write(pdf)
    expected = tmp_path / "expected.toml"
    expected.write_text("""schema=1
[[links]]
id="external"
page=1
uri="https://example.invalid"
[[bookmarks]]
id="answers"
title="Answers"
page=2
""")
    assert audit_navigation(pdf, expected)["passed"]
    expected.write_text(expected.read_text().replace("page=2", "page=1"))
    with pytest.raises(MathpubError):
        audit_navigation(pdf, expected)
