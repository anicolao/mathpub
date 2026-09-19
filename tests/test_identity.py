import json

import pytest
from pypdf import PdfWriter

from mathpub.config import load_toml
from mathpub.errors import MathpubError
from mathpub.identity import check_identity, identity_tex, load_identity


def identity_file(tmp_path):
    path = tmp_path / "identity.toml"
    path.write_text(
        'schema = 1\nid = "book"\ntitle = "Formal Title"\nauthor = "An Author"\n'
        'isbn = "978-0-306-40615-7"\n[display]\ntitle = "Short\\nTitle"\n'
    )
    return path


def test_identity_resolves_without_duplicate_title_and_rejects_drift(tmp_path):
    identity_file(tmp_path)
    path = tmp_path / "book.toml"
    path.write_text(
        'schema=1\nid="book"\nkind="worksheet"\nprofile="test"\n'
        'identity="identity.toml"\n[[sections]]\nquestions=[]\n'
    )
    result = load_toml(path, "publication")
    assert result["title"] == "Formal Title"
    assert result["_display_title"] == "Short\nTitle"
    path.write_text('title="Wrong"\n' + path.read_text())
    with pytest.raises(MathpubError, match="drifts"):
        load_toml(path, "publication")


def test_isbn_checksum_and_pdf_drift(tmp_path):
    path = identity_file(tmp_path)
    identity = load_identity(path)
    assert identity["isbn"] == "9780306406157"
    pdf = tmp_path / "book.pdf"
    writer = PdfWriter()
    writer.add_blank_page(100, 100)
    writer.add_metadata(
        {
            "/Title": identity["title"],
            "/Author": identity["author"],
            "/MathpubIdentity": json.dumps(identity),
        }
    )
    writer.write(pdf)
    assert check_identity(path, [pdf])["passed"]
    writer.add_metadata({"/Title": "Wrong"})
    writer.write(pdf)
    with pytest.raises(MathpubError, match="drift"):
        check_identity(path, [pdf])
    path.write_text(path.read_text().replace("40615-7", "40615-8"))
    with pytest.raises(MathpubError, match="checksum"):
        load_identity(path)


def test_metadata_and_macros_are_not_tex_injection(tmp_path):
    identity = load_identity(identity_file(tmp_path))
    identity["publisher"] = "A & B %"
    source = identity_tex(r"\begin{document}", identity, "lualatex")
    assert r"A \& B \%" in source
    assert r"\MathpubISBN" in source
    assert "/MathpubIdentity" in source


@pytest.mark.parametrize("engine,hyperref", [("pdflatex", False), ("lualatex", True)])
def test_identity_metadata_survives_real_tex_rendering(tmp_path, engine, hyperref):
    from mathpub.render import compile_pdf

    path = identity_file(tmp_path)
    identity = load_identity(path)
    source = (
        r"\documentclass{article}"
        + (r"\usepackage{hyperref}" if hyperref else "")
        + r"\begin{document}Short display title.\end{document}"
    )
    tex = tmp_path / "identity.tex"
    tex.write_text(identity_tex(source, identity, engine))
    pdf, _ = compile_pdf(tex, tmp_path, "computer-modern", tex_engine=engine)
    assert check_identity(path, [pdf])["passed"]
