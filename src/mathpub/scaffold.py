"""Create complete, agent-friendly mathpub projects and components."""

from __future__ import annotations

import json
from pathlib import Path

from mathpub.config import ID_PATTERN, Project
from mathpub.errors import MathpubError

AGENTS = r"""# Working with mathpub

This is a publication-content repository. Its authored components and publications are separate
from the public mathpub tooling repository. Do not copy private content into the tooling checkout.
Use only the programs supplied by this repository's Nix flake. Enter the environment with
`nix develop`, or run `nix run .#mathpub -- COMMAND`. Never use host Python, Sage, TeX,
formatters, or test runners, and never edit generated files beneath `build/`.

Before authoring, inspect the component catalog:

```console
nix run .#mathpub -- list components --json
nix run .#mathpub -- show component COMPONENT_ID --json
```

Persisted component kinds are singular: `objective`, `misconception`, `teaching-tip`, `example`,
and `question`. Directory names such as `objectives/` and `questions/` are plural because they are
collections. Create reviewed source by copying the closest component, or start a complete scaffold:

```console
nix run .#mathpub -- new component ID --kind objective --concept CONCEPT_ID
nix run .#mathpub -- new component ID --kind misconception --concept CONCEPT_ID
nix run .#mathpub -- new component ID --kind teaching-tip --concept CONCEPT_ID
nix run .#mathpub -- new component ID --kind example --concept CONCEPT_ID
nix run .#mathpub -- new question ID --concept CONCEPT_ID --template numeric
```

A question component has reviewed TOML metadata and separate prompt, short-answer, and worked-
solution fragments. Keep exact mathematical values in `ctx.parameter` and `ctx.derived`; use
`ctx.display.*` only for presentation. Use `ctx.require` for pedagogical suitability and
`ctx.check_*` for mathematical evidence. Attach a reader-friendly explanation to every important
check with `ctx.validation_note(CHECK_ID, NOTE)`. Computational evidence is not a formal proof.

Required loop after changing a question component:

```console
nix run .#mathpub -- check component QUESTION_ID --seeds 20 --json
nix run .#mathpub -- preview QUESTION_ID --seed 2026 --replace --json
nix run .#mathpub -- check publication PUBLICATION_PATH --json
nix run .#mathpub -- build PUBLICATION_PATH --seed 2026 --variant A --replace --json
```

Keep answer and solution content out of `prompt.tex`; source boundaries enforce projection
isolation. Parameterized diagrams must derive coordinates from the same canonical parameters as
the mathematics and validate their measurements with `ctx.check_*`. Do not label student diagrams
with implementation-scale commentary. Preserve explicit seeds in reports and commits.
"""

PROJECT = """schema = 1
project = "{name}"
question_roots = []
component_roots = ["components"]
publication_roots = ["publications"]
profile_roots = ["profiles"]
build_dir = "build"
default_profile = "mathpub.exam"

[generation]
max_attempts = 100
"""

CONTENT_FLAKE = """{{
  description = {description};

  inputs.mathpub.url = {mathpub_url};

  outputs = {{ self, mathpub }}:
    mathpub.lib.mkPublicationProject {{
      src = self;
      projectName = {project_name};
      publicationPaths = {publication_paths};
    }};
}}
"""

CONTENT_README = """# {title}

This repository contains private publication source built with
[mathpub](https://github.com/anicolao/mathpub). The publishing engine is a pinned flake input;
authored components, questions, solutions, and publication assemblies remain in this repository.

## First checkout

```console
nix flake lock
nix develop
nix run .#mathpub -- check project --json
```

Add publication paths to `publicationPaths` in `flake.nix` so `nix flake check` validates them.
Build a publication with an explicit seed and variant:

```console
nix run .#mathpub -- build publications/BOOK.toml \\
  --seed 2026 --variant review --replace --json
```

Generated files beneath `build/` are disposable and must not be committed. Repository visibility,
collaborators, branch protection, backups, and any content licence are controlled by this private
repository's owner.
"""

CONTENT_GITIGNORE = """/build/
/result
/result-*
/.direnv/
/.pytest_cache/
/.ruff_cache/
*.egg-info/
__pycache__/
*.py[cod]
"""

COLLECTIONS = {
    "objective": "objectives",
    "misconception": "misconceptions",
    "teaching-tip": "teaching-tips",
    "example": "examples",
    "question": "questions",
}

DEFAULT_TITLES = {
    "objective": "What You Will Learn",
    "misconception": "Common Mistake to Avoid",
    "teaching-tip": "Teaching Tip for Tutors and Parents",
}

QUESTION_TEMPLATES = ("fixed", "numeric", "symbolic", "tikz")

GENERATORS = {
    "numeric": r"""from mathpub.question import generator

@generator
def generate(ctx):
    value = ctx.random.integer(2, 12)
    answer = 2 * value
    ctx.parameter("value", value)
    ctx.derived("answer", answer)
    ctx.require("positive-input", value > 0)
    ctx.check_equal("doubling", value + value, answer)
    ctx.validation_note(
        "doubling",
        "Adding a number to itself gives the same result as multiplying it by two.",
    )
    ctx.display.integer("value", value)
    ctx.display.integer("answer", answer)
""",
    "symbolic": r"""from mathpub.question import generator

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
    ctx.validation_note(
        "differentiate",
        "Independent differentiation reproduces the displayed derivative.",
    )
    ctx.display.math("expression", expression)
    ctx.display.math("answer", derivative)
""",
    "tikz": r"""from mathpub.question import generator

@generator
def generate(ctx):
    length = ctx.random.integer(2, 5)
    endpoint_x = length
    endpoint_y = length
    area = length^2
    ctx.parameter("length", length)
    ctx.derived("endpoint_x", endpoint_x)
    ctx.derived("endpoint_y", endpoint_y)
    ctx.derived("answer", area)
    ctx.check_equal("area", length * length, area)
    ctx.validation_note("area", "The area is the product of the two generated side lengths.")
    ctx.check_equal("diagram-width", endpoint_x, length)
    ctx.validation_note(
        "diagram-width",
        "The horizontal diagram coordinate equals the generated side length.",
    )
    ctx.check_equal("diagram-height", endpoint_y, length)
    ctx.validation_note(
        "diagram-height",
        "The vertical diagram coordinate equals the generated side length.",
    )
    ctx.display.integer("length", length)
    ctx.display.integer("endpoint_x", endpoint_x)
    ctx.display.integer("endpoint_y", endpoint_y)
    ctx.display.integer("answer", area)
""",
}


def _write_new(path: Path, content: str) -> None:
    if path.exists():
        raise MathpubError("MP-SRC-009", f"refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _toml_array(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=False)


def _default_title(identifier: str, kind: str) -> str:
    if kind in DEFAULT_TITLES:
        return DEFAULT_TITLES[kind]
    return identifier.rsplit(".", 1)[-1].replace("-", " ").title()


def _nix_list(values: list[str]) -> str:
    return "[ " + " ".join(json.dumps(value) for value in values) + " ]"


def init_project(
    directory: Path,
    *,
    mathpub_url: str = "github:anicolao/mathpub",
    publication_paths: list[str] | None = None,
) -> dict[str, str]:
    root = directory.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if (root / "mathpub.toml").exists():
        raise MathpubError("MP-SRC-010", f"already a mathpub project: {root}")
    name = root.name.lower().replace("_", "-")
    if not ID_PATTERN.fullmatch(name):
        raise MathpubError("MP-SRC-006", f"invalid project name derived from directory: {name}")
    publication_paths = publication_paths or []
    for publication_path in publication_paths:
        path = Path(publication_path)
        if path.is_absolute() or ".." in path.parts:
            raise MathpubError(
                "MP-SRC-005", f"publication path must stay inside the repository: {path}"
            )
    _write_new(root / "mathpub.toml", PROJECT.format(name=name))
    if not (root / "AGENTS.md").exists():
        _write_new(root / "AGENTS.md", AGENTS)
    if not (root / "flake.nix").exists():
        _write_new(
            root / "flake.nix",
            CONTENT_FLAKE.format(
                description=json.dumps(f"Private mathpub publication: {name}"),
                mathpub_url=json.dumps(mathpub_url),
                project_name=json.dumps(name),
                publication_paths=_nix_list(publication_paths),
            ),
        )
    if not (root / ".gitignore").exists():
        _write_new(root / ".gitignore", CONTENT_GITIGNORE)
    if not (root / "README.md").exists():
        _write_new(root / "README.md", CONTENT_README.format(title=root.name))
    for child in ("components", "publications", "profiles"):
        (root / child).mkdir(exist_ok=True)
    return {
        "root": str(root),
        "config": "mathpub.toml",
        "instructions": "AGENTS.md",
        "flake": "flake.nix",
        "readme": "README.md",
    }


def _question_sources(template: str) -> tuple[str, str, str]:
    if template == "fixed":
        return (
            "State and justify your answer.\n",
            "A reviewed fixed answer.\n",
            "Explain the reasoning that leads to the answer, and check it against the question.\n",
        )
    if template == "numeric":
        return (
            r"Compute twice \(\mpvalue{value}\)." "\n",
            r"\mpvalue{answer}" "\n",
            r"Doubling means multiplying by two: \(2(\mpvalue{value})=\mpvalue{answer}\)." "\n",
        )
    if template == "symbolic":
        return (
            r"Differentiate \(\mpvalue{expression}\) with respect to \(x\)." "\n",
            r"\mpvalue{answer}" "\n",
            r"Apply the power rule to obtain \(\mpvalue{answer}\)." "\n",
        )
    return (
        r"""Find the area of the square.
\begin{center}
\begin{tikzpicture}[x=1cm,y=1cm]
  \draw (0,0) rectangle (\mpvalue{endpoint_x},\mpvalue{endpoint_y});
  \node[below] at (\mpvalue{endpoint_x}/2,0) {\(\mpvalue{length}\)};
\end{tikzpicture}
\end{center}
""",
        r"\mpvalue{answer}" "\n",
        r"A square with side \(\mpvalue{length}\) has area \(\mpvalue{length}^2=\mpvalue{answer}\)."
        "\n",
    )


def new_component(
    project: Project,
    identifier: str,
    kind: str,
    *,
    concepts: list[str] | None = None,
    title: str | None = None,
    template: str = "fixed",
    form: str = "cohesive",
) -> dict[str, str]:
    """Create one complete component using the canonical component schema."""
    if not ID_PATTERN.fullmatch(identifier):
        raise MathpubError("MP-SRC-006", f"invalid component ID: {identifier}")
    if kind not in COLLECTIONS:
        raise MathpubError("MP-SRC-011", f"unsupported scaffold component kind: {kind}")
    concepts = concepts or []
    if not concepts:
        raise MathpubError("MP-SRC-015", f"new {kind} requires at least one --concept ID")
    invalid_concept = next((value for value in concepts if not ID_PATTERN.fullmatch(value)), None)
    if invalid_concept:
        raise MathpubError("MP-SRC-006", f"invalid concept ID: {invalid_concept}")
    if kind != "question" and template != "fixed":
        raise MathpubError("MP-SRC-011", "--template is only valid for question components")
    if template not in QUESTION_TEMPLATES:
        raise MathpubError("MP-SRC-011", f"unsupported question template: {template}")
    if kind != "example" and form != "cohesive":
        raise MathpubError("MP-SRC-011", "--form is only valid for example components")

    directory = project.component_roots[0] / COLLECTIONS[kind] / Path(*identifier.split("."))
    metadata_title = title or _default_title(identifier, kind)
    common = (
        "schema = 1\n"
        f"id = {json.dumps(identifier)}\n"
        f"kind = {json.dumps(kind)}\n"
        f"title = {json.dumps(metadata_title)}\n"
        'status = "draft"\n'
    )

    if kind == "question":
        generator = 'generator = "generate.sage"\n' if template != "fixed" else ""
        answer_mode = "plain-text" if template == "fixed" else "math"
        metadata = (
            common
            + f"concepts = {_toml_array(concepts)}\n"
            + "points = 1\n"
            + generator
            + "[fragments]\n"
            + 'prompt = "prompt.tex"\nanswer = "answer.tex"\nsolution = "solution.tex"\n'
            + "[fragment_modes]\n"
            + f'prompt = "mixed-tex"\nanswer = "{answer_mode}"\nsolution = "mixed-tex"\n'
            + '[workspace]\nstudent = "35mm"\n'
            + "[testing]\nsample_seeds = 20\nmax_attempts = 100\n"
        )
        _write_new(directory / "component.toml", metadata)
        if template != "fixed":
            _write_new(directory / "generate.sage", GENERATORS[template])
        prompt, answer, solution = _question_sources(template)
        _write_new(directory / "prompt.tex", prompt)
        _write_new(directory / "answer.tex", answer)
        _write_new(directory / "solution.tex", solution)
    elif kind == "example":
        if form not in {"cohesive", "structured"}:
            raise MathpubError("MP-SRC-011", f"unsupported example form: {form}")
        metadata = common + f"concepts = {_toml_array(concepts)}\n[fragments]\n"
        if form == "cohesive":
            metadata += 'body = "body.tex"\n[fragment_modes]\nbody = "mixed-tex"\n'
            _write_new(directory / "component.toml", metadata)
            _write_new(
                directory / "body.tex",
                "Work through a concrete example here, explaining why each "
                "mathematical step is valid.\n",
            )
        else:
            metadata += (
                'prompt = "prompt.tex"\nresult = "result.tex"\n'
                '[fragment_modes]\nprompt = "mixed-tex"\nresult = "mixed-tex"\n'
            )
            _write_new(directory / "component.toml", metadata)
            _write_new(directory / "prompt.tex", "State the example problem here.\n")
            _write_new(directory / "result.tex", "Show and explain the result here.\n")
    else:
        audiences = (
            'audiences = ["parent", "teacher"]\n'
            if kind == "teaching-tip"
            else 'audiences = ["student"]\n'
        )
        metadata = (
            common
            + f"concepts = {_toml_array(concepts)}\n"
            + audiences
            + '[fragments]\nbody = "body.tex"\n'
            + '[fragment_modes]\nbody = "mixed-tex"\n'
        )
        body = {
            "objective": "After this lesson, you will be able to explain and apply this idea.\n",
            "misconception": (
                "Watch for this common error, and use the original conditions to check your work.\n"
            ),
            "teaching-tip": (
                "Ask the student to explain the idea in their own words before introducing a "
                "shortcut.\n"
            ),
        }[kind]
        _write_new(directory / "component.toml", metadata)
        _write_new(directory / "body.tex", body)

    return {
        "id": identifier,
        "kind": kind,
        "path": directory.relative_to(project.root).as_posix(),
    }


def new_question(
    project: Project,
    identifier: str,
    template: str,
    concepts: list[str],
    title: str | None = None,
) -> dict[str, str]:
    """Convenience command backed by the one component scaffolder."""
    result = new_component(
        project,
        identifier,
        "question",
        concepts=concepts,
        title=title,
        template=template,
    )
    result["template"] = template
    return result
