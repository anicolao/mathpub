from __future__ import annotations

import subprocess

import pytest

from mathpub.errors import MathpubError
from mathpub.render import compile_pdf


def test_precompiled_format_reuses_auxiliary_state_for_one_pass(tmp_path, monkeypatch):
    generated = tmp_path / "generated"
    output = tmp_path / "output"
    format_dir = tmp_path / "format"
    generated.mkdir()
    output.mkdir()
    format_dir.mkdir()
    tex_path = generated / "preview.tex"
    tex_path.write_text(r"\begin{document}Preview\end{document}")
    (output / "preview.aux").write_text(r"\relax")
    (output / "preview.pdf").write_bytes(b"%PDF fixture")
    format_path = format_dir / "mathpub.fmt"
    format_path.write_bytes(b"format fixture")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="compiled", stderr="")

    monkeypatch.setattr("mathpub.render.subprocess.run", fake_run)
    compile_pdf(
        tex_path,
        output,
        "libertinus",
        projection="student",
        latex_format=format_path,
    )

    assert len(calls) == 1
    assert calls[0][1]["env"]["HOME"] == str(format_dir)


def test_precompiled_format_runs_twice_without_auxiliary_state(tmp_path, monkeypatch):
    generated = tmp_path / "generated"
    output = tmp_path / "output"
    format_dir = tmp_path / "format"
    generated.mkdir()
    output.mkdir()
    format_dir.mkdir()
    tex_path = generated / "preview.tex"
    tex_path.write_text(r"\begin{document}Preview\end{document}")
    (output / "preview.pdf").write_bytes(b"%PDF fixture")
    format_path = format_dir / "mathpub.fmt"
    format_path.write_bytes(b"format fixture")
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="compiled", stderr="")

    monkeypatch.setattr("mathpub.render.subprocess.run", fake_run)
    compile_pdf(
        tex_path,
        output,
        "libertinus",
        projection="student",
        latex_format=format_path,
    )

    assert len(calls) == 2


def test_overfull_hbox_is_a_mapped_fatal_layout_error(tmp_path, monkeypatch):
    tex_path = tmp_path / "preview.tex"
    tex_path.write_text("preamble\ncomponent text\nmore text\n")
    (tmp_path / "preview.pdf").write_bytes(b"%PDF fixture")

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=r"Overfull \hbox (12.5pt too wide) in paragraph at lines 2--3",
            stderr="",
        )

    monkeypatch.setattr("mathpub.render.subprocess.run", fake_run)
    with pytest.raises(MathpubError) as raised:
        compile_pdf(
            tex_path,
            tmp_path,
            "libertinus",
            projection="student",
            generated_source="generated-tex/preview.tex",
            source_map_file="generated-tex/source-map.json",
            source_map=[
                {
                    "component_id": "algebra.example",
                    "fragment": "body",
                    "authored_source": "components/examples/algebra/example/body.tex",
                    "generated_start_line": 2,
                    "generated_end_line": 3,
                }
            ],
        )

    error = raised.value
    assert error.code == "MP-TEX-016"
    assert error.exit_code == 6
    assert error.details["component_id"] == "algebra.example"
    assert error.details["fragment"] == "body"
    assert error.details["generated_line"] == 2
    assert error.details["layout_overflows"] == [
        {
            "axis": "horizontal",
            "amount_pt": 12.5,
            "extent": "wide",
            "generated_start_line": 2,
            "generated_end_line": 3,
        }
    ]
    assert "Do not accept or present a PDF" in error.details["remediation"]
    assert "Reflow or split" in error.message


def test_overfull_vbox_is_fatal_even_without_a_source_line(tmp_path, monkeypatch):
    tex_path = tmp_path / "preview.tex"
    tex_path.write_text("content\n")
    (tmp_path / "preview.pdf").write_bytes(b"%PDF fixture")

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=r"Overfull \vbox (8.25pt too high) has occurred while \output is active [4]",
            stderr="",
        )

    monkeypatch.setattr("mathpub.render.subprocess.run", fake_run)
    with pytest.raises(MathpubError) as raised:
        compile_pdf(tex_path, tmp_path, "libertinus", projection="solutions")

    error = raised.value
    assert error.code == "MP-TEX-016"
    assert error.details["generated_line"] is None
    assert error.details["layout_overflows"][0]["axis"] == "vertical"
    assert error.details["layout_overflows"][0]["page"] == 4
