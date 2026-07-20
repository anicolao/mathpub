"""Stable, user-facing mathpub errors."""

from __future__ import annotations

import subprocess
from typing import Any


class MathpubError(Exception):
    """An expected failure with a stable code and process exit status."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        exit_code: int = 3,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code
        self.details = details or {}


def timeout_transcript(error: subprocess.TimeoutExpired) -> str:
    """Normalize captured timeout output across text and byte subprocess modes."""

    def text(value: str | bytes | None) -> str:
        if isinstance(value, bytes):
            return value.decode(errors="replace")
        return value or ""

    return text(error.stdout or error.output) + "\n" + text(error.stderr)
