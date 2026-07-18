"""Create complete, agent-friendly mathpub projects and questions."""

from __future__ import annotations

from pathlib import Path

from mathpub.config import ID_PATTERN, Project
from mathpub.errors import MathpubError

AGENTS = """# AGENTS.md

This is a mathpub project. Edit authored TOML, Sage, and TeX files; never edit `build/`.

Before creating content, run `mathpub list questions --json` and reuse an existing question
when it already represents the requested mathematics. Create new content with
`mathpub new question ID --kind KIND`.

Required loop for every question change:

1. `mathpub check question ID --json`
2. `mathpub preview ID --seed SEED --json`
3. `mathpub check publication PATH --json` when the question belongs to a publication
4. `mathpub build PATH --seed SEED --variant NAME --json`

Use `ctx.require` for suitability constraints, `ctx.check_*` for mathematical evidence,
and `ctx.display.*` only for presentation. Preserve explicit seeds and never describe a
symbolic or numerical check as a formal proof.
"""

PROJECT = """schema = 1
project = "{name}"
question_roots = ["questions"]
publication_roots = ["publications"]
profile_roots = ["profiles"]
build_dir = "build"
default_profile = "mathpub.exam"

[generation]
max_attempts = 100
"""

QUESTION = """schema = 1
id = "{identifier}"
title = "New {kind} question"
kind = "{kind}"
points = 1
tags = []
prompt = "prompt.tex"
answer = "answer.tex"
solution = "solution.tex"
{generator}
[workspace]
student = "35mm"

[testing]
sample_seeds = 20
max_attempts = 100
"""

GENERATORS = {
    "numeric": """from mathpub.question import generator

@generator
def generate(ctx):
    value = ctx.random.integer(2, 12)
    ctx.parameter("value", value)
    ctx.derived("answer", value * 2)
    ctx.require("positive", value > 0)
    ctx.check_equal("doubling", value * 2, 2 * value)
    ctx.display.integer("value", value)
    ctx.display.integer("answer", value * 2)
""",
    "symbolic": """from mathpub.question import generator

@generator
def generate(ctx):
    coefficient = ctx.random.integer(2, 9)
    x = var("x")
    expression = coefficient * x^2
    derivative = diff(expression, x)
    ctx.parameter("coefficient", coefficient)
    ctx.derived("expression", expression)
    ctx.derived("derivative", derivative)
    ctx.check_equal("differentiate", diff(expression, x), derivative)
    ctx.display.math("expression", expression)
    ctx.display.math("answer", derivative)
""",
    "tikz": """from mathpub.question import generator

@generator
def generate(ctx):
    length = ctx.random.integer(2, 8)
    ctx.parameter("length", length)
    ctx.derived("answer", length^2)
    ctx.check_equal("square", length * length, length^2)
    ctx.display.integer("length", length)
    ctx.display.integer("answer", length^2)
""",
}


def _write_new(path: Path, content: str) -> None:
    if path.exists():
        raise MathpubError("MP-SRC-009", f"refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def init_project(directory: Path) -> dict[str, str]:
    root = directory.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if (root / "mathpub.toml").exists():
        raise MathpubError("MP-SRC-010", f"already a mathpub project: {root}")
    name = root.name.lower().replace("_", "-")
    _write_new(root / "mathpub.toml", PROJECT.format(name=name))
    if not (root / "AGENTS.md").exists():
        _write_new(root / "AGENTS.md", AGENTS)
    for child in ("questions", "publications", "profiles"):
        (root / child).mkdir(exist_ok=True)
    return {"root": str(root), "config": "mathpub.toml", "instructions": "AGENTS.md"}


def new_question(project: Project, identifier: str, kind: str) -> dict[str, str]:
    if not ID_PATTERN.fullmatch(identifier):
        raise MathpubError("MP-SRC-006", f"invalid question ID: {identifier}")
    if kind not in {"fixed", *GENERATORS}:
        raise MathpubError("MP-SRC-011", f"unsupported question kind: {kind}")
    directory = project.question_roots[0] / Path(*identifier.split("."))
    generator_line = 'generator = "generate.sage"\n' if kind != "fixed" else ""
    _write_new(
        directory / "question.toml",
        QUESTION.format(identifier=identifier, kind=kind, generator=generator_line),
    )
    if kind != "fixed":
        _write_new(directory / "generate.sage", GENERATORS[kind])
        prompt = (
            "Compute twice $\\mpvalue{value}$."
            if kind == "numeric"
            else "Compute the requested value: $\\mpvalue{expression}$."
        )
        if kind == "tikz":
            prompt = """Find the area of the square.
\\begin{center}
\\begin{tikzpicture}
  \\draw (0,0) rectangle (2,2);
  \\node[below] at (1,0) {$\\mpvalue{length}$};
\\end{tikzpicture}
\\end{center}
"""
        _write_new(directory / "prompt.tex", prompt + "\n")
        _write_new(directory / "answer.tex", "$\\mpvalue{answer}$\n")
        _write_new(directory / "solution.tex", "The result is $\\mpvalue{answer}$.\n")
    else:
        _write_new(directory / "prompt.tex", "State and justify your answer.\n")
        _write_new(directory / "answer.tex", "A reviewed fixed answer.\n")
        _write_new(directory / "solution.tex", "A reviewed fixed solution.\n")
    return {"id": identifier, "kind": kind, "path": directory.relative_to(project.root).as_posix()}
