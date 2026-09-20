import json
import subprocess

import pytest
from pypdf import PdfReader, PdfWriter

from mathpub.errors import MathpubError
from mathpub.provenance import source_snapshot, stamp_tex, verify_stamp
from mathpub.releases import assemble_release, check_release, verify_release
from tests.test_print_export import edition


def release_config(tmp_path):
    edition(tmp_path)
    config = tmp_path / "release.toml"
    config.write_text("""schema = 1
id = "test-release"
[[books]]
id = "synthetic.book"
required_roles = ["interior"]
[[books.artifacts]]
role = "interior"
manifest = "manifest.json"
projection = "student"
""")
    return config


def test_release_is_portable_and_verifies_without_source_tree(tmp_path):
    config = release_config(tmp_path)
    assert check_release(config)["books"][0]["artifacts"][0]["pages"] == 1
    bundle = tmp_path / "bundle"
    assemble_release(config, bundle)
    (tmp_path / "sample.pdf").unlink()
    (tmp_path / "manifest.json").unlink()
    assert verify_release(bundle)["books"][0]["id"] == "synthetic.book"
    (bundle / "synthetic.book/interior.pdf").write_bytes(b"changed")
    with pytest.raises(MathpubError, match="bytes changed"):
        verify_release(bundle)


def test_missing_roles_and_duplicate_roles_fail(tmp_path):
    config = release_config(tmp_path)
    config.write_text(config.read_text().replace('["interior"]', '["interior", "cover"]'))
    with pytest.raises(MathpubError, match="missing"):
        check_release(config)
    config.write_text(
        config.read_text().replace('["interior", "cover"]', '["interior"]')
        + """
[[books.artifacts]]
role = "interior"
manifest = "manifest.json"
projection = "student"
"""
    )
    with pytest.raises(MathpubError, match="duplicate"):
        check_release(config)


def test_stamp_mismatch_and_unknown_source_rejected(tmp_path):
    manifest_path, pdf = edition(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    assert verify_stamp(PdfReader(pdf), manifest, "student")["source"]["dirty"] is False
    manifest["source"]["git_commit"] = "d" * 40
    with pytest.raises(MathpubError, match="does not match"):
        verify_stamp(PdfReader(pdf), manifest, "student")
    writer = PdfWriter()
    writer.add_blank_page(100, 100)
    writer.write(tmp_path / "unstamped.pdf")
    with pytest.raises(MathpubError, match="lacks"):
        verify_stamp(PdfReader(tmp_path / "unstamped.pdf"), manifest, "student")


def test_source_snapshot_detects_dirty_to_dirty_edits_and_unknown_state(tmp_path):
    assert source_snapshot(tmp_path)["dirty"] is None
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-qm",
            "test",
        ],
        check=True,
    )
    path = tmp_path / "source.tex"
    path.write_text("before")
    before = source_snapshot(tmp_path)
    path.write_text("after")
    after = source_snapshot(tmp_path)
    assert before["dirty"] and after["dirty"]
    assert before["tree_sha256"] != after["tree_sha256"]


def test_stamp_uses_safe_pdf_hex_for_both_tex_engines():
    for engine, command in (("pdflatex", r"\pdfinfo"), ("lualatex", r"\pdfextension info")):
        result = stamp_tex(r"\begin{document}content", {"text": "{unsafe}\\%"}, engine)
        assert command in result
        assert "unsafe" not in result
