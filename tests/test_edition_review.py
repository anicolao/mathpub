from pypdf import PdfWriter

from mathpub.edition_review import align_pages, create_review, review_html


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
