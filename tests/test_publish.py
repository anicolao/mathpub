from __future__ import annotations

import json
import subprocess

import pytest
from pypdf import PdfReader

from mathpub.config import find_project
from mathpub.errors import MathpubError
from mathpub.publish import build, reproduce
from mathpub.scaffold import init_project, new_question


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


def test_builds_textbook_lessons_with_isolated_answer_projections(tmp_path):
    root = tmp_path / "project"
    init_project(root)
    project = find_project(root)
    lessons = root / "publications" / "lessons" / "variables"
    lessons.mkdir(parents=True)
    (lessons / "content.tex").write_text(
        r"\keyidea{A variable represents a number.}"
        r"\begin{workedexample}Solve $x+2=5$, so $x=3$.\end{workedexample}"
    )
    (lessons / "exercises.tex").write_text(r"\begin{exercises}\item Solve $x+4=9$.\end{exercises}")
    (lessons / "answers.tex").write_text(
        r"\begin{lessonanswers}{Short answers}\item $x=5$.\end{lessonanswers}"
    )
    (lessons / "solutions.tex").write_text(
        r"\begin{lessonanswers}{Worked solutions}\item Subtract $4$: $x=5$.\end{lessonanswers}"
    )
    (lessons / "self-assessment.tex").write_text(
        r"\subsection*{Self-Assessment}Explain how subtraction preserves equality."
    )
    practice = root / "publications" / "lessons" / "practice"
    practice.mkdir()
    (practice / "exercises.tex").write_text(r"\begin{exercises}\item Solve $2x=8$.\end{exercises}")
    (practice / "self-assessment.tex").write_text(
        r"\subsection*{Unit Self-Assessment}Rate your equation-solving evidence."
    )
    (practice / "answers.tex").write_text(
        r"\begin{lessonanswers}{Practice answers}\item $x=4$.\end{lessonanswers}"
    )
    (practice / "solutions.tex").write_text(
        r"\begin{lessonanswers}{Practice solutions}\item Divide by $2$: $x=4$.\end{lessonanswers}"
    )
    publication = root / "publications" / "algebra.toml"
    publication.write_text(
        """schema = 1
id = "algebra.textbook"
kind = "textbook"
title = "Algebra"
profile = "mathpub.exam"
projections = ["student", "answers", "solutions", "validation"]
[[chapters]]
title = "Foundations"
[chapters.practice]
id = "foundations-practice"
title = "Foundations Practice"
exercises = "lessons/practice/exercises.tex"
self_assessment = "lessons/practice/self-assessment.tex"
answers = "lessons/practice/answers.tex"
solutions = "lessons/practice/solutions.tex"
[[chapters.lessons]]
id = "variables"
title = "Variables"
objectives = ["Interpret variables."]
content = "lessons/variables/content.tex"
exercises = "lessons/variables/exercises.tex"
self_assessment = "lessons/variables/self-assessment.tex"
answers = "lessons/variables/answers.tex"
solutions = "lessons/variables/solutions.tex"
"""
    )

    result = build(project, publication, root_seed="42", variant="review")
    edition = root / result["edition"]
    student = next((edition / "generated-tex").glob("*-student.tex")).read_text()
    answers = next((edition / "generated-tex").glob("*-answers.tex")).read_text()
    solutions = next((edition / "generated-tex").glob("*-solutions.tex")).read_text()
    assert "x=5" not in student
    assert "Short answers" in answers
    assert "Worked solutions" in solutions
    assert "Self-Assessment" in student
    assert "Unit Self-Assessment" in student
    assert "Practice solutions" in solutions
    assert len(PdfReader(next(edition.glob("*-student.pdf"))).pages) >= 3

    concrete_result = build(
        project,
        publication,
        root_seed="42",
        variant="concrete",
        projections=["student"],
        font_family="concrete",
    )
    concrete_edition = root / concrete_result["edition"]
    concrete_manifest = json.loads((concrete_edition / "manifest.json").read_text())
    concrete_pdf = concrete_edition / concrete_manifest["outputs"][0]["path"]
    fonts = subprocess.run(
        ["pdffonts", str(concrete_pdf)], capture_output=True, text=True, check=True
    ).stdout
    assert concrete_manifest["font_family"] == "concrete"
    assert concrete_manifest["tex_engine"] == "lualatex"
    assert "CMUConcrete-Roman" in fonts
    assert "CMUConcrete-Bold" in fonts
    assert "Type 3" not in fonts
