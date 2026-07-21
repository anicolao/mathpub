from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from mathpub.catalog import Catalog
from mathpub.config import find_project
from mathpub.errors import MathpubError
from mathpub.instance import instantiate_component
from mathpub.publish import build
from mathpub.render import compile_pdf
from mathpub.scaffold import init_project


def _component(root, path, metadata, fragments, generator=None):
    directory = root / "components" / path
    directory.mkdir(parents=True)
    (directory / "component.toml").write_text(metadata)
    for name, source in fragments.items():
        (directory / name).write_text(source)
    if generator:
        (directory / "generate.sage").write_text(generator)


def test_component_catalog_seed_isolation_and_textbook_assembly(tmp_path):
    root = tmp_path / "project"
    init_project(root)
    _component(
        root,
        "concepts/doubling",
        """schema = 1
id = "algebra.doubling"
kind = "concept"
title = "Doubling"
status = "reviewed"
[fragments]
summary = "summary.tex"
""",
        {"summary.tex": "Doubling multiplies a number by $2$.\n"},
    )
    _component(
        root,
        "questions/double",
        """schema = 1
id = "algebra.double"
kind = "question"
title = "Double a number"
status = "reviewed"
concepts = ["algebra.doubling"]
generator = "generate.sage"
[fragments]
prompt = "prompt.tex"
answer = "answer.tex"
solution = "solution.tex"
[workspace]
student = "5mm"
""",
        {
            "prompt.tex": "Double $\\mpvalue{value}$.\n",
            "answer.tex": "$\\mpvalue{answer}$.\n",
            "solution.tex": "$2(\\mpvalue{value})=\\mpvalue{answer}$. "
            "\\textbf{Explanation:} Doubling means multiplying by two.\n",
        },
        """from mathpub.question import generator

@generator
def generate(ctx):
    value = ctx.random.integer(2, 12)
    ctx.parameter("value", value)
    ctx.derived("answer", 2 * value)
    ctx.check_equal("double", value + value, 2 * value)
    ctx.validation_note("double", "Adding a number to itself equals multiplying it by two.")
    ctx.display.integer("value", value)
    ctx.display.integer("answer", 2 * value)
""",
    )
    _component(
        root,
        "objectives/doubling",
        """schema = 1
id = "algebra.doubling-objective"
kind = "objective"
title = "What You Will Learn"
status = "reviewed"
[fragments]
body = "body.tex"
""",
        {"body.tex": "You will connect repeated addition with multiplication.\n"},
    )
    _component(
        root,
        "misconceptions/doubling",
        """schema = 1
id = "algebra.doubling-misconception"
kind = "misconception"
title = "Common Mistakes to Avoid"
status = "reviewed"
[fragments]
body = "body.tex"
""",
        {"body.tex": "Do not add two to the number when you mean to double it.\n"},
    )
    _component(
        root,
        "tips/doubling",
        """schema = 1
id = "algebra.doubling-tip"
kind = "teaching-tip"
title = "Teaching Tips for Tutors \\\\& Parents"
status = "reviewed"
[fragments]
body = "body.tex"
""",
        {"body.tex": "Use two equal groups of counters.\n"},
    )
    _component(
        root,
        "examples/cohesive",
        """schema = 1
id = "algebra.doubling-cohesive-example"
kind = "example"
title = "Cohesive Example"
status = "reviewed"
concepts = ["algebra.doubling"]
[fragments]
body = "body.tex"
""",
        {"body.tex": "Double \\(4\\) to obtain \\(8\\).\n"},
    )
    _component(
        root,
        "examples/structured",
        """schema = 1
id = "algebra.doubling-structured-example"
kind = "example"
title = "Structured Example"
status = "reviewed"
concepts = ["algebra.doubling"]
[fragments]
prompt = "prompt.tex"
result = "result.tex"
""",
        {
            "prompt.tex": "Double \\(7\\).\n",
            "result.tex": "The result is \\(14\\).\n",
        },
    )
    publication = root / "publications/book.toml"
    publication.write_text(
        """schema = 1
id = "algebra.components"
kind = "textbook"
title = "Component Algebra"
profile = "mathpub.exam"
style = "anna"
font = "computer-modern"
projections = ["student", "solutions", "validation"]
[[component_chapters]]
id = "foundations"
title = "Foundations"
[[component_chapters.lessons]]
id = "doubling"
title = "Doubling"
concepts = ["algebra.doubling"]
[[component_chapters.lessons.blocks]]
derive = "concept-summary"
title = "Lesson Summary"
[[component_chapters.lessons.blocks]]
include = "algebra.doubling-objective"
placement = "foundations.doubling.objective"
[[component_chapters.lessons.blocks]]
include = "algebra.doubling-misconception"
placement = "foundations.doubling.misconception"
[[component_chapters.lessons.blocks]]
include = "algebra.doubling-tip"
placement = "foundations.doubling.tip"
[[component_chapters.lessons.blocks]]
heading = "Guided Examples"
[[component_chapters.lessons.blocks]]
include = "algebra.doubling-cohesive-example"
placement = "foundations.doubling.cohesive-example"
[[component_chapters.lessons.blocks]]
include = "algebra.doubling-structured-example"
placement = "foundations.doubling.structured-example"
[[component_chapters.lessons.blocks]]
[component_chapters.lessons.blocks.problem_set]
id = "practice"
title = "Practice"
direction_lines = [
  { label = "Part A:", text = "Show each step." },
  { label = "Part B:", text = "Check each result." },
]
[[component_chapters.lessons.blocks.problem_set.parts]]
id = "mental"
title = "Part A: Mental Math"
directions = "Work without a calculator."
response = "answer-line"
emphasize_answers = true
[[component_chapters.lessons.blocks.problem_set.parts.questions]]
id = "algebra.double"
placement = "foundations.doubling.q1"
[[component_chapters.lessons.blocks.problem_set.parts]]
id = "written"
title = "Part B: Written Work"
[[component_chapters.lessons.blocks.problem_set.parts.questions]]
id = "algebra.double"
placement = "foundations.doubling.q2"
"""
    )
    project = find_project(root)
    catalog = Catalog(project)
    assert set(catalog.components) == {
        "algebra.doubling",
        "algebra.double",
        "algebra.doubling-objective",
        "algebra.doubling-misconception",
        "algebra.doubling-tip",
        "algebra.doubling-cohesive-example",
        "algebra.doubling-structured-example",
    }
    entry = catalog.get("component", "algebra.double")
    first = instantiate_component(entry, "2026", "A", "place.one")
    repeated = instantiate_component(entry, "2026", "A", "place.one")
    second = instantiate_component(entry, "2026", "A", "place.two")
    assert first == repeated
    assert first["sha256"] != second["sha256"]

    result = build(project, publication, root_seed="2026", variant="A")
    edition = root / result["edition"]
    manifest = json.loads((edition / "manifest.json").read_text())
    assert len(manifest["components"]) == 8
    assert {item["placement"] for item in manifest["components"]} >= {
        "foundations.doubling.q1",
        "foundations.doubling.q2",
    }
    student = next((edition / "generated-tex").glob("*-student.tex")).read_text()
    solutions = next((edition / "generated-tex").glob("*-solutions.tex")).read_text()
    validation = next((edition / "generated-tex").glob("*-validation.tex")).read_text()
    source_map = json.loads((edition / "generated-tex/source-map.json").read_text())
    assert "Doubling multiplies" in student
    assert r"\begin{annasummary}{Lesson Summary}" in student
    assert r"\begin{learningbox}[What You Will Learn]" in student
    assert r"\begin{annamistakes}{Common Mistakes to Avoid}" in student
    assert r"\begin{annatips}{Teaching Tips for Tutors \& Parents}" in student
    assert "Guided Examples" in student
    assert "Double \\(4\\) to obtain \\(8\\)." in student
    assert "Double \\(7\\)." in student
    assert "The result is \\(14\\)." in student
    assert "Thought Process." not in student
    assert "Part A: Mental Math" in student
    assert "Work without a calculator." in student
    assert r"\textbf{Part A:} Show each step.\par" in student
    assert r"\textbf{Part B:} Check each result.\par" in student
    assert "Part B: Written Work" in student
    assert "resume=problemset" in student
    assert "rule{0.48\\linewidth}" in student
    assert "Validation and justification" not in student
    assert "2(" in solutions
    assert r"\annaanswer{" in solutions
    assert r"$.}\\*\textit{Explanation:}" in solutions
    assert r"\*\textit{Explanation:}" in solutions
    assert "resume=answerset" in solutions
    assert "Adding a number to itself" in validation
    assert {
        (item["component_id"], item["fragment"]) for item in source_map["projections"]["student"]
    } >= {("algebra.double", "prompt")}
    assert {
        (item["component_id"], item["fragment"]) for item in source_map["projections"]["solutions"]
    } >= {("algebra.double", "solution")}


def test_tex_failure_reports_authored_component_fragment(tmp_path):
    root = tmp_path / "project"
    init_project(root)
    _component(
        root,
        "questions/broken-answer",
        """schema = 1
id = "algebra.broken-answer"
kind = "question"
title = "Broken answer"
status = "draft"
concepts = ["algebra.broken"]
[fragments]
prompt = "prompt.tex"
answer = "answer.tex"
solution = "solution.tex"
""",
        {
            "prompt.tex": "State the value.\n",
            "answer.tex": "\\definitelyundefined\n",
            "solution.tex": "The value is \\(1/2\\).\n",
        },
    )
    publication = root / "publications/broken.toml"
    publication.write_text(
        """schema = 1
id = "algebra.broken"
kind = "textbook"
title = "Broken"
profile = "mathpub.exam"
projections = ["answers"]
[[component_chapters]]
id = "preview"
title = "Preview"
[[component_chapters.lessons]]
id = "question"
title = "Question"
concepts = ["algebra.broken"]
[[component_chapters.lessons.blocks]]
[component_chapters.lessons.blocks.problem_set]
id = "preview"
title = "Preview"
show_title = false
[[component_chapters.lessons.blocks.problem_set.questions]]
id = "algebra.broken-answer"
placement = "preview.question"
"""
    )

    with pytest.raises(MathpubError) as failure:
        build(find_project(root), publication, root_seed="2026", variant="broken")

    error = failure.value
    assert error.code == "MP-TEX-007"
    assert error.details["projection"] == "answers"
    assert error.details["component_id"] == "algebra.broken-answer"
    assert error.details["fragment"] == "answer"
    assert error.details["authored_source"].endswith("questions/broken-answer/answer.tex")
    assert error.details["generated_line"] > 0
    assert error.details["diagnostic"]
    assert error.details["excerpt"]
    assert (root / error.details["log"]).is_file()
    assert (root / error.details["source_map"]).is_file()


def test_example_cannot_mix_cohesive_and_structured_fragments(tmp_path):
    root = tmp_path / "project"
    init_project(root)
    _component(
        root,
        "examples/mixed",
        """schema = 1
id = "algebra.mixed-example"
kind = "example"
title = "Mixed Example"
concepts = ["algebra.mixed"]
[fragments]
body = "body.tex"
prompt = "prompt.tex"
result = "result.tex"
""",
        {
            "body.tex": "A cohesive example.\n",
            "prompt.tex": "A structured prompt.\n",
            "result.tex": "A structured result.\n",
        },
    )

    with pytest.raises(MathpubError) as invalid:
        Catalog(find_project(root))

    assert invalid.value.code == "MP-SRC-003"


def test_tex_timeout_preserves_a_structured_log(tmp_path, monkeypatch):
    tex_path = tmp_path / "question.tex"
    tex_path.write_text("\\documentclass{article}\\begin{document}x\\end{document}\n")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 180, output="partial TeX output")

    monkeypatch.setattr("mathpub.render.subprocess.run", timeout)
    with pytest.raises(MathpubError) as failure:
        compile_pdf(tex_path, tmp_path, "libertinus", projection="answers")

    error = failure.value
    assert error.code == "MP-TEX-007"
    assert error.details["timeout_seconds"] == 180
    assert error.details["projection"] == "answers"
    assert error.details["diagnostic"] == "TeX compilation timed out after 180 seconds"
    assert Path(error.details["log"]).read_text().strip() == "partial TeX output"
