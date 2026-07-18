from __future__ import annotations

import pytest

from mathpub.catalog import Catalog
from mathpub.config import find_project
from mathpub.errors import MathpubError
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


def test_constraint_exhaustion_and_failed_check_are_distinct(tmp_path):
    root = tmp_path / "project"
    init_project(root)
    project = find_project(root)
    new_question(project, "physics.failure", "numeric")
    directory = root / "questions/physics/failure"
    generator = directory / "generate.sage"
    entry = Catalog(project).get("question", "physics.failure")

    generator.write_text(
        """from mathpub.question import generator
@generator
def generate(ctx):
    ctx.require("impossible", False)
"""
    )
    with pytest.raises(MathpubError) as exhausted:
        instantiate(entry, "7", "A", max_attempts=3)
    assert exhausted.value.code == "MP-GEN-004"
    assert "impossible" in exhausted.value.message

    generator.write_text(
        """from mathpub.question import generator
@generator
def generate(ctx):
    ctx.check_equal("false-identity", 1, 2)
"""
    )
    with pytest.raises(MathpubError) as failed:
        instantiate(entry, "7", "A", max_attempts=3)
    assert failed.value.code == "MP-CHECK-001"
    assert "false-identity" in failed.value.message


def test_finite_domain_overrides_are_recorded(tmp_path):
    root = tmp_path / "project"
    init_project(root)
    project = find_project(root)
    new_question(project, "physics.domain", "numeric")
    directory = root / "questions/physics/domain"
    (directory / "generate.sage").write_text(
        """from mathpub.question import generator
@generator
def generate(ctx):
    value = ctx.domain("value", [2, 4, 6])
    ctx.parameter("value", value)
    ctx.derived("answer", value * 2)
    ctx.check_equal("double", value * 2, 2 * value)
    ctx.display.integer("value", value)
    ctx.display.integer("answer", value * 2)
"""
    )
    entry = Catalog(project).get("question", "physics.domain")
    instance = instantiate(entry, "exhaustive", "finite", overrides={"value": 4})
    assert instance["parameters"]["value"] == {"type": "integer", "value": 4}
