"""Orchestrate isolated Sage question generation."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from mathpub.catalog import Entry
from mathpub.errors import MathpubError


def canonical_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"


def instance_hash(data: Any) -> str:
    return hashlib.sha256(canonical_json(data).encode()).hexdigest()


def instantiate(
    entry: Entry, root_seed: str, variant: str, max_attempts: int | None = None
) -> dict[str, Any]:
    generator = entry.metadata.get("generator")
    if not generator:
        result = {
            "schema": 1,
            "status": "ok",
            "question_id": entry.metadata["id"],
            "attempt": 0,
            "rng_algorithm": "none",
            "parameters": {},
            "derived": {},
            "display": {},
            "checks": [],
            "rejections": {},
        }
        result["sha256"] = instance_hash(result)
        return result
    attempts = max_attempts or entry.metadata.get("testing", {}).get("max_attempts", 100)
    request = {
        "question_id": entry.metadata["id"],
        "generator": str((entry.path / generator).resolve()),
        "root_seed": str(root_seed),
        "variant": str(variant),
        "max_attempts": attempts,
    }
    runner = Path(__file__).with_name("sage_runner.py")
    with tempfile.TemporaryDirectory(prefix="mathpub-sage-") as temporary:
        request_path = Path(temporary) / "request.json"
        output_path = Path(temporary) / "instance.json"
        request_path.write_text(canonical_json(request), encoding="utf-8")
        process = subprocess.run(
            ["sage", "--python", str(runner), str(request_path), str(output_path)],
            cwd=temporary,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if not output_path.exists():
            raise MathpubError(
                "MP-GEN-001",
                f"Sage runner failed for {entry.metadata['id']}: {process.stderr}",
                exit_code=1,
            )
        result = json.loads(output_path.read_text(encoding="utf-8"))
    if result["status"] == "exhausted":
        raise MathpubError(
            "MP-GEN-004",
            f"generation exhausted {attempts} attempts for "
            f"{entry.metadata['id']}: {result['rejections']}",
            exit_code=4,
        )
    if result["status"] == "check-failed":
        raise MathpubError(
            "MP-CHECK-001",
            f"mathematical check failed for {entry.metadata['id']}: {result['evidence']['id']}",
            exit_code=5,
        )
    if result["status"] != "ok":
        raise MathpubError(
            "MP-GEN-001",
            f"Sage runner failed for {entry.metadata['id']}: {result.get('error')}",
            exit_code=1,
        )
    result["sha256"] = instance_hash(result)
    return result
