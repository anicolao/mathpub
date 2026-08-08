"""Deliver an agent's final work summary to the interactive workspace."""

from __future__ import annotations

import json
import os
import stat
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from mathpub.errors import MathpubError

COMPLETION_HTML_LIMIT = 32_000
COMPLETION_URL_ENV = "MATHPUB_WORKSPACE_COMPLETION_URL"
COMPLETION_TOKEN_ENV = "MATHPUB_WORKSPACE_COMPLETION_TOKEN"


def load_completion_html(*, html: str | None, html_file: str | None) -> str:
    """Load a completion summary from one explicit CLI source."""
    if html is not None:
        summary = html
    elif html_file is not None:
        summary_path = Path(html_file)
        if html_file == "-":
            raise MathpubError(
                "MP-GUI-019",
                "completion HTML must come from --html or a regular UTF-8 file; "
                "interactive stdin is not supported",
            )
        try:
            descriptor = os.open(summary_path, os.O_RDONLY | os.O_NONBLOCK)
            with os.fdopen(descriptor, encoding="utf-8") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise MathpubError(
                        "MP-GUI-019",
                        "completion HTML file must be a regular file, not a pipe or device",
                    )
                summary = stream.read(COMPLETION_HTML_LIMIT + 1)
        except MathpubError:
            raise
        except UnicodeError as error:
            raise MathpubError(
                "MP-GUI-019",
                f"completion summary is not valid UTF-8: {error}",
            ) from error
        except OSError as error:
            raise MathpubError(
                "MP-GUI-019",
                f"could not read completion summary: {error}",
            ) from error
    else:  # argparse requires one source, but keep the function safe for direct callers.
        summary = ""

    if not summary.strip():
        raise MathpubError("MP-GUI-019", "completion summary HTML must not be empty")
    if len(summary.encode("utf-8")) > COMPLETION_HTML_LIMIT:
        raise MathpubError(
            "MP-GUI-019",
            f"completion summary exceeds the {COMPLETION_HTML_LIMIT}-byte limit",
        )
    return summary


def notify_completion(html: str) -> dict[str, object]:
    """Send a bounded HTML summary to the GUI that launched this agent."""
    if not html.strip() or len(html.encode("utf-8")) > COMPLETION_HTML_LIMIT:
        raise MathpubError("MP-GUI-019", "completion summary HTML is empty or too large")

    endpoint = os.environ.get(COMPLETION_URL_ENV, "")
    token = os.environ.get(COMPLETION_TOKEN_ENV, "")
    parsed = urlparse(endpoint)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
        or not parsed.port
        or parsed.path != "/api/agent/completed"
        or not token
    ):
        raise MathpubError(
            "MP-GUI-019",
            "completion reporting is available only to an agent launched by the MathPub workspace",
        )

    body = json.dumps({"html": html}).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            payload = json.loads(error.read().decode("utf-8"))
            detail = payload.get("error", str(error))
        except (json.JSONDecodeError, AttributeError, UnicodeDecodeError):
            detail = str(error)
        raise MathpubError(
            "MP-GUI-019",
            f"workspace rejected completion summary: {detail}",
        ) from error
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
        raise MathpubError(
            "MP-GUI-019",
            f"could not deliver completion summary to the workspace: {error}",
        ) from error

    return {
        "delivered": payload.get("delivered") is True,
        "summary_bytes": len(html.encode("utf-8")),
    }
