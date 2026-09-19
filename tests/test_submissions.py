import json

import pytest

from mathpub.errors import MathpubError
from mathpub.releases import sha256
from mathpub.submissions import execute_submission, plan_hash


def submission_plan(tmp_path):
    files = []
    for role in ("interior", "cover"):
        path = tmp_path / f"{role}.pdf"
        data = f"synthetic {role} bytes".encode()
        path.write_bytes(data)
        files.append(
            {
                "role": role,
                "path": str(path),
                "sha256": sha256(data),
                "bytes": len(data),
                "filename": f"{role}-{sha256(data)}.pdf",
            }
        )
    plan = {
        "target": {"url": "https://example.invalid/draft", "title": "Synthetic Book"},
        "files": files,
    }
    plan["sha256"] = plan_hash(plan)
    return plan


class FakeAdapter:
    def __init__(self, *, wrong=False, fail=None, autosaved=True):
        self.wrong, self.fail, self.autosaved = wrong, fail, autosaved
        self.names, self.uploads = {}, []

    def open(self, plan):
        self.plan = plan

    def observe(self):
        return {
            "target": {**self.plan["target"], **({"title": "Wrong Book"} if self.wrong else {})},
            "filenames": self.names.copy(),
        }

    def screenshot(self, path):
        pass

    def stage(self, item, path):
        return {"sha256": sha256(path.read_bytes()), "bytes": path.stat().st_size}

    def submit(self, item):
        self.uploads.append(item["role"])
        if self.fail == item["role"]:
            raise RuntimeError("connection lost SECRET-MUST-NOT-BE-LOGGED")
        self.names[item["role"]] = item["filename"]

    def acknowledge(self, item):
        if self.fail == "acknowledgment":
            raise TimeoutError("processing still pending")

    def save(self):
        if self.fail == "save":
            raise RuntimeError("connection lost after save")
        return not self.autosaved

    def reload(self):
        if self.fail == "reload":
            self.names = {}

    def close(self):
        pass


def test_wrong_book_fails_before_mutations(tmp_path):
    adapter = FakeAdapter(wrong=True)
    with pytest.raises(MathpubError, match="identity"):
        execute_submission(submission_plan(tmp_path), tmp_path / "attempt", adapter)
    assert not adapter.uploads


def test_autosave_and_reload_are_distinct_from_processing_complete(tmp_path):
    result = execute_submission(submission_plan(tmp_path), tmp_path / "attempt", FakeAdapter())
    assert result["status"] == "draft-persisted"
    assert not result["processing_complete"]
    assert not result["save_clicked"]
    assert all(item["browser_verified"] for item in result["files"])


def test_partial_upload_requires_explicit_retry_and_does_not_replace_persisted_interior(tmp_path):
    plan, adapter = submission_plan(tmp_path), FakeAdapter(fail="cover")
    attempt = tmp_path / "attempt"
    with pytest.raises(MathpubError):
        execute_submission(plan, attempt, adapter)
    assert "SECRET" not in (attempt / "receipt.json").read_text()
    adapter.fail = None
    with pytest.raises(MathpubError, match="uncertain"):
        execute_submission(plan, attempt, adapter, resume=True)
    result = execute_submission(plan, attempt, adapter, resume=True, retry_uncertain=True)
    assert result["status"] == "draft-persisted"
    assert adapter.uploads == ["interior", "cover", "cover"]


@pytest.mark.parametrize("failure", ["acknowledgment", "save", "reload"])
def test_uncertain_ack_save_or_persistence_has_durable_receipt(tmp_path, failure):
    plan, attempt = submission_plan(tmp_path), tmp_path / "attempt"
    with pytest.raises(MathpubError):
        execute_submission(plan, attempt, FakeAdapter(fail=failure))
    receipt = json.loads((attempt / "receipt.json").read_text())
    assert receipt["status"] == "needs-review"
    assert not receipt["processing_complete"]


def test_file_changed_since_plan_is_not_submitted(tmp_path):
    plan, adapter = submission_plan(tmp_path), FakeAdapter()
    (tmp_path / "interior.pdf").write_bytes(b"different")
    with pytest.raises(MathpubError, match="file changed"):
        execute_submission(plan, tmp_path / "attempt", adapter)
    assert not adapter.uploads


def test_resume_rejects_modified_receipt_file_identity(tmp_path):
    plan, attempt = submission_plan(tmp_path), tmp_path / "attempt"
    execute_submission(plan, attempt, FakeAdapter())
    path = attempt / "receipt.json"
    receipt = json.loads(path.read_text())
    receipt["files"][0]["path"] = receipt["files"][1]["path"]
    path.write_text(json.dumps(receipt))
    with pytest.raises(MathpubError, match="receipt files"):
        execute_submission(plan, attempt, FakeAdapter(), resume=True)


def test_attempt_lock_prevents_concurrent_resume(tmp_path):
    plan, attempt = submission_plan(tmp_path), tmp_path / "attempt"

    class ConcurrentAdapter(FakeAdapter):
        def open(self, plan):
            super().open(plan)
            with pytest.raises(MathpubError, match="already running"):
                execute_submission(plan, attempt, FakeAdapter(), resume=True)

    assert execute_submission(plan, attempt, ConcurrentAdapter())["status"] == "draft-persisted"
