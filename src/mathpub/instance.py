"""Orchestrate isolated Sage question generation."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from mathpub.catalog import Entry
from mathpub.errors import MathpubError, timeout_transcript


def canonical_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"


def instance_hash(data: Any) -> str:
    return hashlib.sha256(canonical_json(data).encode()).hexdigest()


def instantiate(
    entry: Entry,
    root_seed: str,
    variant: str,
    max_attempts: int | None = None,
    overrides: dict[str, Any] | None = None,
    seed_key: str | None = None,
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
        "seed_key": seed_key or entry.metadata["id"],
        "generator": str((entry.path / generator).resolve()),
        "root_seed": str(root_seed),
        "variant": str(variant),
        "max_attempts": attempts,
        "overrides": overrides or {},
    }
    runner = Path(__file__).with_name("sage_runner.py")
    # Sage 10.9 asks GAP to print its root paths and assumes the answer occupies
    # one line. GAP wraps that line when Nix's sandbox gives HOME a long path,
    # so keep the isolated generator home short as well as writable.
    with tempfile.TemporaryDirectory(prefix="mathpub-sage-", dir="/tmp") as temporary:
        request_path = Path(temporary) / "request.json"
        output_path = Path(temporary) / "instance.json"
        request_path.write_text(canonical_json(request), encoding="utf-8")
        command = ["sage", "--python", str(runner), str(request_path), str(output_path)]
        try:
            process = subprocess.run(
                command,
                cwd=temporary,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
                env={
                    **os.environ,
                    "HOME": temporary,
                    "XDG_CACHE_HOME": str(Path(temporary) / ".cache"),
                },
            )
        except subprocess.TimeoutExpired as error:
            transcript = timeout_transcript(error).strip()
            raise MathpubError(
                "MP-GEN-008",
                f"Sage generation timed out after 120 seconds for {entry.metadata['id']}",
                exit_code=4,
                details={
                    "question_id": entry.metadata["id"],
                    "generator": str((entry.path / generator).resolve()),
                    "timeout_seconds": 120,
                    "diagnostic": transcript[-2000:] or "Sage produced no output before timeout",
                },
            ) from error
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
        diagnostic = result.get("traceback") or result.get("error")
        raise MathpubError(
            "MP-GEN-001",
            f"Sage runner failed for {entry.metadata['id']}: {diagnostic}",
            exit_code=1,
        )
    result["sha256"] = instance_hash(result)
    return result


def instantiate_component(
    entry: Entry,
    root_seed: str,
    variant: str,
    placement_id: str,
    *,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Instantiate a component with placement-isolated deterministic randomness."""
    result = instantiate(
        entry,
        root_seed,
        variant,
        overrides=overrides,
        seed_key=f"{entry.metadata['id']}@{placement_id}",
    )
    result = {
        **{key: value for key, value in result.items() if key != "sha256"},
        "component_id": entry.metadata["id"],
        "placement_id": placement_id,
    }
    result["sha256"] = instance_hash(result)
    return result
