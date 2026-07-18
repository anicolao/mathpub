from __future__ import annotations

import json

from pypdf import PdfReader

from mathpub.config import find_project
from mathpub.publish import build, reproduce
from mathpub.scaffold import init_project, new_question


def test_builds_isolated_projections_and_reproduces(tmp_path):
    root = tmp_path / "project"
    init_project(root)
    project = find_project(root)
    new_question(project, "physics.fixed", "fixed")
    publication = root / "publications/physics.toml"
    publication.write_text(
        """schema = 1
id = "physics.practice"
kind = "worksheet"
title = "Physics Practice"
course = "Physics"
profile = "mathpub.exam"
paper = "letter"
projections = ["student", "answers", "solutions"]

[[sections]]
title = "Review"
[[sections.questions]]
id = "physics.fixed"
points = 2
"""
    )
    result = build(project, publication, root_seed="42", variant="A")
    edition = root / result["edition"]
    manifest = json.loads((edition / "manifest.json").read_text())
    assert {output["projection"] for output in manifest["outputs"]} == {
        "student",
        "answers",
        "solutions",
    }
    for output in manifest["outputs"]:
        assert len(PdfReader(edition / output["path"]).pages) >= 1
    student_tex = next((edition / "generated-tex").glob("*-student.tex")).read_text()
    assert "A reviewed fixed answer" not in student_tex
    assert "A reviewed fixed solution" not in student_tex

    reproduced = reproduce(project, edition / "manifest.json", replace=True)
    assert (root / reproduced["manifest"]).is_file()
