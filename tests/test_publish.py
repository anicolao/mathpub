from __future__ import annotations

import json
import subprocess

import pytest
from pypdf import PdfReader

from mathpub.config import find_project
from mathpub.errors import MathpubError
from mathpub.gui.synctex import spatial_index
from mathpub.latex_format import dump_latex_format, find_latex_format
from mathpub.publish import _select_publication_lessons, build, reproduce
from mathpub.scaffold import init_project, new_question


def test_lualatex_format_dump_is_reusable(tmp_path):
    root = tmp_path / "project"
    init_project(root)
    project = find_project(root)
    result = dump_latex_format(
        project,
        style="worksheet",
        font_family="libertinus",
        paper="letter",
    )
    format_path = root / result["format"]
    assert format_path.is_file()
    publication = {"id": "demo", "kind": "worksheet", "paper": "letter"}
    assert find_latex_format(project, publication, "libertinus") == format_path
    reused = dump_latex_format(
        project,
        style="worksheet",
        font_family="libertinus",
        paper="letter",
    )
    assert reused["reused"] is True
    metadata_path = root / result["metadata"]
    metadata = json.loads(metadata_path.read_text())
    metadata["source_sha256"] = "stale"
    metadata_path.write_text(json.dumps(metadata))
    assert find_latex_format(project, publication, "libertinus") is None


def test_builds_mapped_metropolis_presentation(tmp_path):
    root = tmp_path / "project"
    init_project(root)
    project = find_project(root)
    publication_dir = root / "publications"
    slide_dir = publication_dir / "credit-scores"
    slide_dir.mkdir()
    (slide_dir / "01-learning-goals.tex").write_text(
        r"""\begin{itemize}
\item Explain what a credit score summarizes.
\item Read the major sections of a credit report.
\end{itemize}
"""
    )
    (slide_dir / "02-key-facts.tex").write_text(
        r"""Payment history is commonly the largest scoring factor.
\[
  \text{utilization}=\frac{\text{reported revolving balances}}
  {\text{total revolving credit limits}}.
\]
"""
    )
    (slide_dir / "03-example.tex").write_text(
        r"""\begin{columns}[T]
\column{0.55\textwidth}
A card reports a balance of \$450 and a limit of \$1,500. Find its utilization.
\[
  \frac{450}{1500}=0.30=30\%.
\]
\column{0.4\textwidth}
\begin{tikzpicture}[x=3cm,y=0.7cm]
  \draw[rounded corners] (0,0) rectangle (1,1);
  \fill[structure.fg] (0,0) rectangle (0.3,1);
  \node at (0.5,0.5) {30\%};
\end{tikzpicture}
\end{columns}
"""
    )
    publication = publication_dir / "credit-scores.toml"
    publication.write_text(
        """schema = 1
id = "consumer-math.credit-scores"
kind = "presentation"
title = "Understanding Credit Scores and Credit Reports"
course = "Consumer Math 101"
profile = "mathpub.exam"
theme = "metropolis"
aspect_ratio = "169"
font = "libertinus"
projections = ["student"]

[[slides]]
id = "learning-goals"
title = "Learning Goals"
source = "credit-scores/01-learning-goals.tex"

[[slides]]
id = "key-facts"
title = "Key Facts"
source = "credit-scores/02-key-facts.tex"

[[slides]]
id = "utilization-example"
title = "Example and Solution"
source = "credit-scores/03-example.tex"
"""
    )

    result = build(
        project,
        publication,
        root_seed="2026",
        variant="review",
        replace=True,
    )

    edition = root / result["edition"]
    output = result["outputs"][0]
    pdf = PdfReader(edition / output["path"])
    assert len(pdf.pages) == 4
    title_page = pdf.pages[0].extract_text()
    assert "Understanding Credit Scores and Credit Reports" in title_page
    assert "Consumer Math 101" not in title_page
    generated = (
        edition / "generated-tex" / "consumer-math.credit-scores-review-student.tex"
    ).read_text()
    assert r"\usetheme{metropolis}" in generated
    assert r"\begin{tikzpicture}" in generated
    assert "Consumer Math 101" not in generated
    source_map = json.loads((edition / "generated-tex/source-map.json").read_text())
    mappings = source_map["projections"]["student"]
    assert [mapping["component_id"] for mapping in mappings] == [
        "learning-goals",
        "key-facts",
        "utilization-example",
    ]
    assert mappings[0]["authored_source"] == ("publications/credit-scores/01-learning-goals.tex")
    for page, component_id in enumerate(
        ("learning-goals", "key-facts", "utilization-example"),
        start=2,
    ):
        index = spatial_index(
            root,
            "consumer-math.credit-scores",
            "review",
            "student",
            page,
        )
        assert [(box["component_id"], box["fragment"]) for box in index["boxes"]] == [
            (component_id, "slide")
        ]
        box = index["boxes"][0]
        assert box["authored_source"].startswith("publications/credit-scores/")
        assert box["w"] > 0
        assert box["h"] > 0
    manifest = json.loads((edition / "manifest.json").read_text())
    assert set(manifest["source"]["presentation_sources"]) == {
        "learning-goals",
        "key-facts",
        "utilization-example",
    }
    assert manifest["publication_kind"] == "presentation"


def test_single_lesson_filter_preserves_only_requested_content():
    publication = {
        "id": "demo",
        "kind": "textbook",
        "component_chapters": [
            {
                "id": "chapter",
                "title": "Chapter",
                "lessons": [
                    {"id": "one", "title": "One", "blocks": []},
                    {"id": "two", "title": "Two", "blocks": []},
                ],
            }
        ],
    }
    filtered = _select_publication_lessons(publication, ["two"])
    assert [lesson["id"] for lesson in filtered["component_chapters"][0]["lessons"]] == ["two"]
    assert len(publication["component_chapters"][0]["lessons"]) == 2


def test_incremental_build_reuses_unchanged_question_instances(tmp_path, monkeypatch):
    root = tmp_path / "project"
    init_project(root)
    project = find_project(root)
    new_question(project, "physics.fixed", "fixed", ["physics.review"])
    publication = root / "publications/physics.toml"
    publication.write_text(
        """schema = 1
id = "physics.cache"
kind = "worksheet"
title = "Physics Cache"
profile = "mathpub.exam"
projections = ["student", "answers"]
[[sections]]
title = "Review"
[[sections.questions]]
id = "physics.fixed"
"""
    )

    def fake_compile(tex_path, output_dir, *args, **kwargs):
        pdf_path = output_dir / f"{tex_path.stem}.pdf"
        log_path = output_dir / f"{tex_path.stem}.build.log"
        pdf_path.write_bytes(b"%PDF cache fixture")
        (output_dir / f"{tex_path.stem}.synctex.gz").write_bytes(b"synctex")
        log_path.write_text("compiled")
        return pdf_path, log_path

    monkeypatch.setattr("mathpub.publish.compile_pdf", fake_compile)
    monkeypatch.setattr(
        "mathpub.publish._inspect_pdf",
        lambda *args, **kwargs: {"pages": 1, "sha256": "fixture"},
    )
    first = build(
        project,
        publication,
        root_seed="42",
        variant="A",
        incremental=True,
    )
    assert first["instance_cache"]["questions_regenerated"] == 1
    first_manifest = json.loads((root / first["manifest"]).read_text())
    first_answers = next(
        output for output in first_manifest["outputs"] if output["projection"] == "answers"
    )
    answers_bytes = (root / first["edition"] / first_answers["path"]).read_bytes()
    prompt_path = next((root / "components").rglob("prompt.tex"))
    prompt_path.write_text(prompt_path.read_text() + "\nClarify the wording.\n")
    second = build(
        project,
        publication,
        root_seed="42",
        variant="A",
        projections=["student"],
        replace=True,
        incremental=True,
    )
    assert second["instance_cache"] == {
        "questions_reused": 1,
        "questions_regenerated": 0,
        "components_reused": 0,
        "components_regenerated": 0,
    }
    second_manifest = json.loads((root / second["manifest"]).read_text())
    assert {output["projection"] for output in second_manifest["outputs"]} == {
        "student",
        "answers",
    }
    assert (root / second["edition"] / first_answers["path"]).read_bytes() == answers_bytes


def test_builds_isolated_projections_and_reproduces(tmp_path):
    root = tmp_path / "project"
    init_project(root)
    project = find_project(root)
    new_question(project, "physics.fixed", "fixed", ["physics.review"])
    publication = root / "publications/physics.toml"
    publication.write_text(
        """schema = 1
id = "physics.practice"
kind = "textbook"
title = "Physics Practice"
profile = "mathpub.exam"
paper = "letter"
projections = ["student", "answers", "solutions", "validation"]

[[component_chapters]]
id = "review"
title = "Review"
[[component_chapters.lessons]]
id = "review"
title = "Physics Practice"
concepts = ["physics.review"]
[[component_chapters.lessons.blocks]]
[component_chapters.lessons.blocks.problem_set]
id = "review"
title = "Review"
[[component_chapters.lessons.blocks.problem_set.questions]]
id = "physics.fixed"
placement = "review.fixed"
"""
    )
    result = build(project, publication, root_seed="42", variant="A")
    edition = root / result["edition"]
    manifest = json.loads((edition / "manifest.json").read_text())
    assert manifest["font_family"] == "libertinus"
    assert manifest["tex_engine"] == "lualatex"
    assert {output["projection"] for output in manifest["outputs"]} == {
        "student",
        "answers",
        "solutions",
        "validation",
    }
    for output in manifest["outputs"]:
        assert len(PdfReader(edition / output["path"]).pages) >= 1
        assert (edition / output["synctex"]).is_file()
    student_pdf = next(
        output for output in manifest["outputs"] if output["projection"] == "student"
    )
    fonts = subprocess.run(
        ["pdffonts", str(edition / student_pdf["path"])],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "LMRoman" not in fonts
    assert "LibertinusSerif-Regular" in fonts
    assert "LibertinusSerif-Bold" in fonts
    assert "Type 3" not in fonts
    student_tex = next((edition / "generated-tex").glob("*-student.tex")).read_text()
    assert r"\newcommand{\mpNaturals}{\mathds{N}}" in student_tex
    assert "A reviewed fixed answer" not in student_tex
    assert "A reviewed fixed solution" not in student_tex
    validation_source = next((edition / "generated-tex").glob("*-validation.tex")).read_text()
    assert "Validation and justification" in validation_source
    assert "computational evidence" in validation_source

    original_instances = {
        path.name: path.read_bytes() for path in (edition / "instances").iterdir()
    }
    original_outputs = {
        output["projection"]: [
            page.extract_text() for page in PdfReader(edition / output["path"]).pages
        ]
        for output in manifest["outputs"]
    }
    reproduced = reproduce(project, edition / "manifest.json", replace=True)
    assert (root / reproduced["manifest"]).is_file()
    rebuilt_manifest = json.loads((root / reproduced["manifest"]).read_text())
    assert {
        path.name: path.read_bytes() for path in (edition / "instances").iterdir()
    } == original_instances
    assert {
        output["projection"]: [
            page.extract_text() for page in PdfReader(edition / output["path"]).pages
        ]
        for output in rebuilt_manifest["outputs"]
    } == original_outputs

    rebuilt_manifest["toolchain"]["sagemath"] = "different"
    (edition / "manifest.json").write_text(json.dumps(rebuilt_manifest))
    with pytest.raises(MathpubError) as mismatch:
        reproduce(project, edition / "manifest.json", replace=True)
    assert mismatch.value.code == "MP-REPRO-001"


def test_build_rejects_raw_tex_textbook_before_creating_an_edition(tmp_path):
    root = tmp_path / "project"
    init_project(root)
    project = find_project(root)
    publication = root / "publications" / "algebra.toml"
    publication.write_text(
        """schema = 1
id = "algebra.textbook"
kind = "textbook"
title = "Algebra"
profile = "mathpub.exam"
[[chapters]]
title = "Foundations"
[[chapters.lessons]]
id = "variables"
title = "Variables"
content = "lessons/variables/content.tex"
exercises = "lessons/variables/exercises.tex"
answers = "lessons/variables/answers.tex"
solutions = "lessons/variables/solutions.tex"
"""
    )

    with pytest.raises(MathpubError) as raised:
        build(project, publication, root_seed="42", variant="review")

    assert raised.value.code == "MP-SRC-016"
    assert raised.value.details["required_source_model"] == "component_chapters"
    assert not (root / "build/algebra.textbook/review").exists()
