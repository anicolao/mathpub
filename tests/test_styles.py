from __future__ import annotations

import json
from pathlib import Path

import pytest

from mathpub.cli import main
from mathpub.config import find_project
from mathpub.errors import MathpubError
from mathpub.render import textbook_tex
from mathpub.styles import StyleCatalog, prepare_publication_style


def invoke(monkeypatch, capsys, root: Path, arguments: list[str]):
    monkeypatch.chdir(root)
    code = main([*arguments, "--json"])
    return code, json.loads(capsys.readouterr().out)


def test_builtin_styles_are_discoverable(tmp_path, monkeypatch, capsys):
    project = tmp_path / "course"
    assert main(["init", str(project)]) == 0
    capsys.readouterr()

    code, payload = invoke(monkeypatch, capsys, project, ["list", "styles"])

    assert code == 0
    assert [(item["id"], item["source"]) for item in payload["data"]] == [
        ("mathpub", "built-in"),
        ("anna", "built-in"),
    ]


def test_new_style_is_discovered_and_customizes_its_inherited_renderer(
    tmp_path, monkeypatch, capsys
):
    root = tmp_path / "course"
    assert main(["init", str(root)]) == 0
    capsys.readouterr()
    code, payload = invoke(
        monkeypatch,
        capsys,
        root,
        ["new", "style", "credit-series", "--extends", "anna", "--title", "Credit Series"],
    )
    assert code == 0
    assert payload["data"]["path"] == "styles/credit-series"
    style_tex = root / "styles/credit-series/style.tex"
    style_tex.write_text(
        "\\usepackage{helvet}\n"
        "\\renewcommand{\\familydefault}{\\sfdefault}\n"
        "\\geometry{margin=0.75in}\n"
    )

    code, payload = invoke(monkeypatch, capsys, root, ["show", "style", "credit-series"])
    assert code == 0
    assert payload["data"]["base"] == "anna"
    assert payload["data"]["source"] == "library"
    assert payload["data"]["tex"] == ["styles/credit-series/style.tex"]

    project = find_project(root)
    publication = {
        "kind": "textbook",
        "title": "Credit",
        "style": "credit-series",
    }
    prepare_publication_style(project, publication)
    source = textbook_tex(publication, "student", [r"\annachapter{1}{Reports}"], "libertinus")
    assert r"\documentclass[12pt,letterpaper]{article}" in source
    assert "% Library style customization" in source
    assert r"\usepackage{helvet}" in source
    assert source.index(r"\usepackage{helvet}") < source.index(r"\begin{document}")


def test_capabilities_include_library_styles(tmp_path, monkeypatch, capsys):
    root = tmp_path / "course"
    assert main(["init", str(root)]) == 0
    capsys.readouterr()
    invoke(monkeypatch, capsys, root, ["new", "style", "house", "--extends", "mathpub"])

    code, payload = invoke(monkeypatch, capsys, root, ["capabilities"])

    assert code == 0
    assert payload["data"]["refresh_command"] == "nix run .#mathpub -- capabilities"
    assert [item["id"] for item in payload["data"]["styles"]] == ["mathpub", "anna", "house"]
    assert payload["data"]["style_authoring"]["publication_setting"] == 'style = "STYLE_ID"'
    authoring = payload["data"]["publication_authoring"]
    assert authoring["textbook_source_model"] == "component_chapters"
    assert authoring["raw_textbook_chapters_supported"] is False
    assert "fatal build errors" in authoring["layout_overflow_policy"]
    completion = payload["data"]["task_completion"]
    assert completion["availability"] == "GUI-launched agent sessions only"
    assert completion["stdin_command"] == "mathpub complete --html-file - --json"


def test_style_catalog_rejects_document_ownership_commands(tmp_path, monkeypatch, capsys):
    root = tmp_path / "course"
    assert main(["init", str(root)]) == 0
    capsys.readouterr()
    invoke(monkeypatch, capsys, root, ["new", "style", "unsafe"])
    (root / "styles/unsafe/style.tex").write_text(r"\documentclass{article}" + "\n")

    project = find_project(root)
    with pytest.raises(MathpubError) as raised:
        StyleCatalog(project)
    assert raised.value.code == "MP-TEX-008"
