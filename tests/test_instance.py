from __future__ import annotations

from mathpub.catalog import Catalog
from mathpub.config import find_project
from mathpub.instance import instantiate
from mathpub.question import seed_for
from mathpub.scaffold import init_project, new_question


def test_seed_is_deterministic_and_question_local(tmp_path):
    root = tmp_path / "project"
    init_project(root)
    project = find_project(root)
    new_question(project, "physics.one", "numeric")
    entry = Catalog(project).get("question", "physics.one")
    first = instantiate(entry, "2026", "A")
    second = instantiate(entry, "2026", "A")
    assert first == second
    assert seed_for("2026", "A", "physics.one", 0) != seed_for("2026", "B", "physics.one", 0)
    assert first["checks"][0]["evidence"] == "symbolic-check"
    assert first["display"]["answer"]["kind"] == "integer"
