"""Durable, adapter-independent submission attempts; never silently retry ambiguity."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from mathpub.errors import MathpubError
from mathpub.releases import sha256


def plan_hash(plan: dict) -> str:
    return sha256(
        json.dumps(
            {k: v for k, v in plan.items() if k != "sha256"}, sort_keys=True, separators=(",", ":")
        ).encode()
    )


def write_receipt(path: Path, data: dict):
    data["updated_at"] = datetime.now(UTC).isoformat()
    with tempfile.NamedTemporaryFile(
        mode="w", dir=path.parent, prefix=".receipt-", delete=False
    ) as file:
        temporary = Path(file.name)
        json.dump(data, file, indent=2, sort_keys=True)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())
    temporary.replace(path)


def execute_submission(
    plan: dict, directory: Path, adapter, *, resume=False, retry_uncertain=False
) -> dict:
    if plan.get("sha256") != plan_hash(plan):
        raise MathpubError("MP-SUBMIT-001", "submission plan changed after preparation")
    if any(
        Path(item["filename"]).name != item["filename"] or item["filename"] in (".", "..")
        for item in plan["files"]
    ):
        raise MathpubError("MP-SUBMIT-001", "unsafe submission filename")
    if not resume:
        try:
            directory.mkdir(mode=0o700)
        except OSError as error:
            raise MathpubError("MP-SUBMIT-001", "attempt directory must be new") from error
    if not directory.is_dir():
        raise MathpubError("MP-SUBMIT-001", "resume needs an existing attempt directory")
    with (directory / ".lock").open("a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise MathpubError("MP-SUBMIT-001", "submission attempt is already running") from error
        return _execute_submission(
            plan, directory, adapter, resume=resume, retry_uncertain=retry_uncertain
        )


def _execute_submission(plan, directory, adapter, *, resume, retry_uncertain):
    receipt_path = directory / "receipt.json"
    if resume:
        try:
            receipt = json.loads(receipt_path.read_text())
        except (OSError, ValueError) as error:
            raise MathpubError("MP-SUBMIT-001", "cannot resume without a valid receipt") from error
        if receipt.get("plan_sha256") != plan["sha256"]:
            raise MathpubError("MP-SUBMIT-001", "receipt belongs to a different submission plan")
        files = receipt.get("files", [])
        if len(files) != len(plan["files"]) or any(
            any(record.get(key) != value for key, value in planned.items())
            for record, planned in zip(files, plan["files"], strict=True)
        ):
            raise MathpubError("MP-SUBMIT-001", "receipt files no longer match the submission plan")
    else:
        receipt = {
            "schema": 1,
            "plan_sha256": plan["sha256"],
            "target": plan["target"],
            "status": "planned",
            "processing_complete": False,
            "files": [
                {**file, "status": "planned", "browser_verified": False} for file in plan["files"]
            ],
            "limitations": [
                "Persisted filenames are not server-side checksums.",
                "No preview approval, proof order, pricing or publication action.",
            ],
        }
    write_receipt(receipt_path, receipt)

    def verify_observed():
        observed = adapter.observe()
        differences = {
            key: {"expected": value, "observed": observed["target"].get(key)}
            for key, value in plan["target"].items()
            if observed["target"].get(key) != value
        }
        receipt["observed"] = observed
        if differences:
            raise MathpubError(
                "MP-SUBMIT-002",
                "destination identity or printing settings changed",
                details={"differences": differences},
            )
        return observed

    try:
        adapter.open(plan)
        observed = verify_observed()
        adapter.screenshot(directory / "before.png")
        for item in receipt["files"]:
            payload = Path(item["path"]).read_bytes()
            if sha256(payload) != item["sha256"] or len(payload) != item["bytes"]:
                raise MathpubError("MP-SUBMIT-001", "release file changed after planning")
            observed = verify_observed()
            if (
                item["browser_verified"]
                and observed["filenames"].get(item["role"]) == item["filename"]
            ):
                # Reinspect before resuming, without needlessly replacing persisted bytes.
                if item["status"] not in ("acknowledged", "draft-persisted"):
                    adapter.acknowledge(item)
                item["status"] = "acknowledged"
                write_receipt(receipt_path, receipt)
                continue
            if (
                item["status"] in ("submitting", "submitted", "acknowledged", "draft-persisted")
                and not retry_uncertain
            ):
                raise MathpubError(
                    "MP-SUBMIT-003",
                    "uncertain prior upload; inspect the draft before --retry-uncertain",
                )
            staged = directory / item["filename"]
            if staged.exists() and sha256(staged.read_bytes()) != item["sha256"]:
                raise MathpubError("MP-SUBMIT-001", "staged file differs from plan")
            if not staged.exists():
                with staged.open("xb") as file:
                    file.write(payload)
            delivered = adapter.stage(item, staged)
            if delivered != {"sha256": item["sha256"], "bytes": item["bytes"]}:
                raise MathpubError(
                    "MP-SUBMIT-001", "browser byte verification failed before submission"
                )
            item["browser_verified"] = True
            item["status"] = "submitting"
            write_receipt(receipt_path, receipt)
            verify_observed()
            adapter.submit(item)
            item["status"] = "submitted"
            write_receipt(receipt_path, receipt)
            adapter.acknowledge(item)
            item["status"] = "acknowledged"
            write_receipt(receipt_path, receipt)
        verify_observed()
        receipt["save_clicked"] = adapter.save()
        receipt["status"] = "acknowledged"
        write_receipt(receipt_path, receipt)
        adapter.reload()
        observed = verify_observed()
        if any(
            observed["filenames"].get(item["role"]) != item["filename"] for item in receipt["files"]
        ):
            raise MathpubError("MP-SUBMIT-003", "uploaded filenames did not persist after reload")
        for item in receipt["files"]:
            item["status"] = "draft-persisted"
        receipt["status"] = "draft-persisted"
        receipt["finished_at"] = datetime.now(UTC).isoformat()
        adapter.screenshot(directory / "after-reload.png")
        write_receipt(receipt_path, receipt)
        return receipt
    except Exception as error:
        receipt["status"] = "needs-review"
        # Browser exceptions may contain cookies, entered text or script arguments.
        receipt["error"] = {
            "code": error.code if isinstance(error, MathpubError) else "MP-SUBMIT-004",
            "message": error.message
            if isinstance(error, MathpubError)
            else "Browser operation interrupted; inspect the draft and resume.",
        }
        write_receipt(receipt_path, receipt)
        raise MathpubError(
            receipt["error"]["code"],
            receipt["error"]["message"],
            details={"receipt": str(receipt_path), "status": "needs-review"},
        ) from error
    finally:
        with contextlib.suppress(Exception):
            adapter.close()
