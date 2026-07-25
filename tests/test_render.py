from __future__ import annotations

import subprocess

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
