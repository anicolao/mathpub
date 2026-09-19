import json

import pytest

from mathpub.config import Project
from mathpub.errors import MathpubError
from mathpub.gui.publishing import publishing_operation, trusted_request
from tests.test_submissions import submission_plan


def test_publishing_requires_same_origin_non_simple_requests():
    headers = {
        "host": "127.0.0.1:8765",
        "origin": "http://127.0.0.1:8765",
        "content-type": "application/json",
        "x-mathpub-publishing": "1",
    }
    assert trusted_request(headers)
    assert not trusted_request({**headers, "origin": "https://evil.invalid"})
    assert not trusted_request({**headers, "x-mathpub-publishing": ""})
    assert not trusted_request({**headers, "host": "evil.invalid", "origin": "http://evil.invalid"})


def test_upload_requires_confirmation_of_exact_plan_and_confines_paths(tmp_path, monkeypatch):
    project = Project(tmp_path, {})
    plan = submission_plan(tmp_path)
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    calls = []
    monkeypatch.setattr("mathpub.kdp.upload_draft", lambda *a, **kw: calls.append((a, kw)) or {})
    payload = {"action": "kdp-upload", "plan": "plan.json", "output": "attempt"}
    with pytest.raises(MathpubError, match="explicitly confirm"):
        publishing_operation(project, payload)
    assert not calls
    publishing_operation(project, {**payload, "confirmation": plan["sha256"]})
    assert len(calls) == 1
    with pytest.raises(MathpubError, match="inside"):
        publishing_operation(project, {**payload, "plan": "../outside.json"})
