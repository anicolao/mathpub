from __future__ import annotations

import json
from pathlib import Path

from mathpub.cli import main


def invoke(monkeypatch, capsys, root: Path, arguments: list[str]):
    monkeypatch.chdir(root)
    code = main([*arguments, "--json"])
    output = capsys.readouterr()
    return code, json.loads(output.out)


def test_init_and_agent_instructions(tmp_path, monkeypatch, capsys):
    project = tmp_path / "course"
    code = main(["init", str(project), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "ok"
    assert (project / "mathpub.toml").is_file()
    instructions = (project / "AGENTS.md").read_text()
    assert "never edit generated files beneath `build/`" in instructions

    code, payload = invoke(
        monkeypatch,
        capsys,
        project,
        [
            "new",
            "question",
            "physics.energy.ramp",
            "--concept",
            "physics.energy",
            "--template",
            "numeric",
        ],
    )
    assert code == 0
    assert payload["data"]["id"] == "physics.energy.ramp"
    assert payload["data"]["kind"] == "question"
    question = project / "components/questions/physics/energy/ramp"
    assert {path.name for path in question.iterdir()} == {
        "component.toml",
        "generate.sage",
        "prompt.tex",
        "answer.tex",
        "solution.tex",
    }

    code, payload = invoke(
        monkeypatch, capsys, project, ["check", "component", "physics.energy.ramp"]
    )
    assert code == 0
    assert len(payload["data"]["checked"]) == 4


def test_discovery_is_structured_and_relative(tmp_path, monkeypatch, capsys):
    project = tmp_path / "course"
    assert main(["init", str(project)]) == 0
    capsys.readouterr()
    monkeypatch.chdir(project)
    assert main(["new", "question", "physics.fixed", "--concept", "physics.measurement"]) == 0
    capsys.readouterr()
    code, payload = invoke(
        monkeypatch, capsys, project, ["list", "components", "--kind", "question"]
    )
    assert code == 0
    assert payload["schema"] == 1
    assert payload["data"][0]["path"] == "components/questions/physics/fixed"


def test_component_scaffolds_are_complete_and_canonical(tmp_path, monkeypatch, capsys):
    project = tmp_path / "course"
    assert main(["init", str(project)]) == 0
    capsys.readouterr()
    instructions = (project / "AGENTS.md").read_text()
    assert "Persisted component kinds are singular" in instructions
    assert "check component QUESTION_ID" in instructions
    assert not (project / "questions").exists()

    cases = (
        ("course.goal", "objective", ["--concept", "course.idea"]),
        ("course.error", "misconception", ["--concept", "course.idea"]),
        ("course.tip", "teaching-tip", ["--concept", "course.idea"]),
        ("course.example", "example", ["--concept", "course.idea"]),
        ("course.question", "question", ["--concept", "course.idea"]),
    )
    for identifier, kind, extra in cases:
        code, payload = invoke(
            monkeypatch,
            capsys,
            project,
            ["new", "component", identifier, "--kind", kind, *extra],
        )
        assert code == 0
        assert payload["data"]["kind"] == kind

    code, payload = invoke(monkeypatch, capsys, project, ["check", "project"])
    assert code == 0
    assert payload["data"]["components"] == len(cases)


def test_invalid_component_kind_suggests_canonical_singular(tmp_path, monkeypatch, capsys):
    project = tmp_path / "course"
    assert main(["init", str(project)]) == 0
    capsys.readouterr()
    source = project / "components/mistake/component.toml"
    source.parent.mkdir(parents=True)
    source.write_text(
        """schema = 1
id = "course.mistake"
kind = "misconceptions"
title = "Mistake"
"""
    )

    code, payload = invoke(monkeypatch, capsys, project, ["check", "project"])
    assert code == 3
    assert payload["error"]["code"] == "MP-SRC-003"
    assert payload["error"]["details"]["suggestion"] == "misconception"
    assert "did you mean 'misconception'?" in payload["error"]["message"]


def test_invalid_project_returns_stable_error(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code = main(["list", "questions", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 3
    assert payload["error"]["code"] == "MP-SRC-004"


def test_component_question_preview_builds_isolated_projections(tmp_path, monkeypatch, capsys):
    project = tmp_path / "course"
    assert main(["init", str(project)]) == 0
    capsys.readouterr()
    question = project / "components/algebra/double"
    question.mkdir(parents=True)
    (question / "component.toml").write_text(
        """schema = 1
id = "algebra.double"
kind = "question"
title = "Double a number"
status = "reviewed"
concepts = ["algebra.doubling"]
[fragments]
prompt = "prompt.tex"
answer = "answer.tex"
solution = "solution.tex"
[fragment_modes]
answer = "math"
"""
    )
    (question / "prompt.tex").write_text("Double \\(6\\).\n")
    (question / "answer.tex").write_text("12\n")
    (question / "solution.tex").write_text("\\(2\\cdot6=12\\).\n")

    code, payload = invoke(
        monkeypatch,
        capsys,
        project,
        ["preview", "algebra.double", "--seed", "2026", "--replace"],
    )

    assert code == 0
    assert payload["data"]["question"] == {
        "id": "algebra.double",
        "placement": "preview.question",
        "source_model": "component",
    }
    edition = project / payload["data"]["edition"]
    manifest = json.loads((edition / "manifest.json").read_text())
    assert {output["projection"] for output in manifest["outputs"]} == {
        "student",
        "answers",
        "solutions",
        "validation",
    }
    assert manifest["components"][0]["placement"] == "preview.question"
    student = next((edition / "generated-tex").glob("*-student.tex")).read_text()
    answers = next((edition / "generated-tex").glob("*-answers.tex")).read_text()
    assert "Double \\(6\\)." in student
    assert "2\\cdot6=12" not in student
    assert r"\item \(12\)" in answers


def test_fragment_modes_reject_ambiguous_math_before_compilation(tmp_path, monkeypatch, capsys):
    project = tmp_path / "course"
    assert main(["init", str(project)]) == 0
    capsys.readouterr()

    def question(identifier: str, answer: str, mode: str):
        directory = project / "components" / identifier
        directory.mkdir(parents=True)
        (directory / "component.toml").write_text(
            f'''schema = 1
id = "algebra.{identifier}"
kind = "question"
title = "Invalid answer"
concepts = ["algebra.invalid"]
[fragments]
prompt = "prompt.tex"
answer = "answer.tex"
solution = "solution.tex"
[fragment_modes]
answer = "{mode}"
'''
        )
        (directory / "prompt.tex").write_text("State the answer.\n")
        (directory / "answer.tex").write_text(answer)
        (directory / "solution.tex").write_text("A solution.\n")

    question("double-delimited", "$x^2$\n", "math")
    question("math-outside-mode", "\\frac{1}{2}\n", "mixed-tex")

    for identifier in ("double-delimited", "math-outside-mode"):
        code, payload = invoke(
            monkeypatch,
            capsys,
            project,
            ["check", "component", f"algebra.{identifier}"],
        )
        assert code == 3
        assert payload["error"]["code"] == "MP-TEX-012"
        assert payload["error"]["details"]["fragment_mode"] in {"math", "mixed-tex"}
