"""Stable, user-facing mathpub errors."""

from __future__ import annotations


class MathpubError(Exception):
    """An expected failure with a stable code and process exit status."""

    def __init__(self, code: str, message: str, *, exit_code: int = 3) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code
