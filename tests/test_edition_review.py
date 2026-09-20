import hashlib
import os
import sys

import pytest
from pypdf import PdfWriter

from mathpub.edition_review import align_pages, create_review, create_review_set, review_html


def test_alignment_exposes_insertions_and_deletions():
    assert align_pages(["alpha", "beta", "gamma"], ["alpha", "new", "beta"]) == [
        (0, 0),
        (None, 1),
        (1, 2),
        (2, None),
    ]


def test_review_retains_snapshots_and_hash_bound_progress(tmp_path):
    before, after = tmp_path / "before.pdf", tmp_path / "after.pdf"
    writer = PdfWriter()
    writer.add_blank_page(100, 100)
    writer.write(before)
    writer.add_blank_page(100, 100)
    writer.write(after)
    report = create_review(before, after, tmp_path / "review", dpi=36, label="<script>bad</script>")
    assert [pair["status"] for pair in report["pairs"]] == ["unchanged", "inserted"]
    assert (tmp_path / "review/before.pdf").read_bytes() == before.read_bytes()
    assert (tmp_path / "review/after-2.png").is_file()
    page = review_html(report)
    assert "<script>bad</script>" not in page
    assert "&lt;script&gt;" in page
    assert report["key"] in page
    second = create_review(before, after, tmp_path / "cropped", dpi=36, crop_pt=(2, 2, 2, 2))
    assert second["key"] != report["key"]


def test_review_set_snapshots_context_and_escapes_labels(tmp_path):
    writer = PdfWriter()
    writer.add_blank_page(100, 100)
    writer.write(tmp_path / "book.pdf")
    (tmp_path / "source.patch").write_text("<script>private evidence</script>")
    config = tmp_path / "review.toml"
    config.write_text("""schema = 1
dpi = 36
[[books]]
label = "<script>Workbook</script>"
before = "book.pdf"
after = "book.pdf"
notes = "<img onerror=bad>"
baseline_revision = "claimed"
attachments = ["source.patch"]
[[books]]
label = "Answers"
before = "book.pdf"
after = "book.pdf"
""")
    output = tmp_path / "review"
    result = create_review_set(config, output)
    assert len(result["books"]) == len(result["pairs"]) == 2
    evidence = result["books"][0]["context"]["attachments"][0]
    assert (output / evidence["path"]).read_bytes() == (tmp_path / "source.patch").read_bytes()
    assert (
        evidence["sha256"] == hashlib.sha256((tmp_path / "source.patch").read_bytes()).hexdigest()
    )
    document = (output / "index.html").read_text()
    assert 'href="0/before.pdf"' in document
    assert 'href="1/after.pdf"' in document
    assert "<img onerror=bad>" not in document
    assert "<script>Workbook</script>" not in document
    assert "not verified PDF provenance" in document
    (tmp_path / "source.patch").write_text("changed evidence")
    updated = create_review_set(config, tmp_path / "updated")
    assert updated["key"] != result["key"]


def test_review_browser_navigation_zoom_storage_and_pdf_links():
    if (
        not os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
        or os.environ.get("HOME") == "/homeless-shelter"
    ):
        pytest.skip("requires Nix browsers outside the build sandbox")
    from playwright.sync_api import sync_playwright

    report = {
        "label": "Review",
        "key": "test-hash",
        "excluded_margins_pt": [0, 0, 0, 0],
        "books": [
            {"id": "0", "label": "Book", "before": "0/before.pdf", "after": "0/after.pdf"},
            {"id": "1", "label": "Key", "before": "1/before.pdf", "after": "1/after.pdf"},
        ],
        "pairs": [
            {
                "book": "0",
                "status": "modified",
                "text": "alpha",
                "before": {"page": 1, "label": "i", "image": "before-1.png"},
                "after": {"page": 1, "label": "i", "image": "after-1.png"},
            },
            {
                "book": "1",
                "status": "deleted",
                "text": "beta",
                "before": {"page": 2, "label": "ii", "image": "before-2.png"},
                "after": None,
            },
        ],
    }
    with sync_playwright() as runtime:
        browser_type = runtime.webkit if sys.platform == "darwin" else runtime.chromium
        browser = browser_type.launch(headless=True)
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route(
            "**/*", lambda route: route.fulfill(content_type="text/html", body=review_html(report))
        )
        page.goto("http://review.test/")
        assert page.locator("#zoom").input_value() == "100"
        assert page.locator('a[href="0/before.pdf"]').count() == 1
        assert "printed ii" in page.locator("#page option").nth(1).inner_text()
        page.locator("#zoom").select_option("60")
        page.locator("#next").click()
        assert page.locator("#page").input_value() == "1"
        page.locator("#book").select_option("1")
        page.locator('[data-id="1"]').check()
        assert "1 reviewed in selection" in page.locator("#count").inner_text()
        page.reload()
        assert page.locator("#zoom").input_value() == "60"
        assert page.locator('[data-id="1"]').is_checked()
        page.locator("#page").select_option("1")
        page.locator("#filter").fill("no results")
        assert page.locator("#next").is_disabled()
        assert page.locator("#page").is_disabled()
        page.evaluate("localStorage.setItem('mathpub-review-zoom','broken')")
        page.reload()
        assert page.locator("#zoom").input_value() == "100"
        page.add_init_script(
            "Storage.prototype.getItem = () => {throw Error('disabled')}; "
            "Storage.prototype.setItem = () => {throw Error('disabled')}"
        )
        page.reload()
        page.locator("#zoom").select_option("80")
        assert page.locator("#zoom").input_value() == "80"
        assert not errors
        browser.close()
