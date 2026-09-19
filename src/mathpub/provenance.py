"""Artifact-bound, explicitly unsigned source provenance."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from mathpub.errors import MathpubError


def source_snapshot(root: Path) -> dict:
    def git(*args):
        return subprocess.run(["git", *args], cwd=root, capture_output=True, check=False)

    head = git("rev-parse", "HEAD")
    status = git("status", "--porcelain", "-z")
    files = git("ls-files", "--cached", "--others", "--exclude-standard", "-z")
    if any(result.returncode for result in (head, status, files)):
        return {"git_commit": None, "dirty": None, "tree_sha256": None}
    digest = hashlib.sha256()
    for name in sorted(set(files.stdout.split(b"\0")) - {b""}):
        path = root / name.decode()
        digest.update(name + b"\0")
        if path.is_symlink():
            digest.update(str(path.readlink()).encode())
        elif path.is_file():
            digest.update(path.read_bytes())
        else:
            digest.update(b"<missing-or-submodule>")
    return {
        "git_commit": head.stdout.decode().strip(),
        "dirty": bool(status.stdout),
        "tree_sha256": digest.hexdigest(),
    }


def stamp_tex(source: str, stamp: dict, engine: str) -> str:
    data = json.dumps(stamp, sort_keys=True, separators=(",", ":")).encode().hex()
    command = r"\pdfextension info" if engine == "lualatex" else r"\pdfinfo"
    marker = r"\begin{document}"
    return source.replace(marker, f"{command}{{/MathpubProvenance <{data}>}}\n{marker}", 1)


def read_stamp(reader) -> dict:
    value = (reader.metadata or {}).get("/MathpubProvenance")
    if value is None:
        raise MathpubError("MP-PROVENANCE-001", "PDF lacks an embedded MathPub source stamp")
    try:
        return json.loads(value)
    except (ValueError, TypeError) as error:
        raise MathpubError("MP-PROVENANCE-001", "invalid embedded source stamp") from error


def verify_stamp(reader, manifest: dict, projection: str) -> dict:
    stamp = read_stamp(reader)
    expected = {
        "schema": 1,
        "publication_id": manifest["publication_id"],
        "projection": projection,
        "lesson_ids": manifest["lesson_ids"],
        "source": {
            key: manifest["source"].get(key) for key in ("git_commit", "dirty", "tree_sha256")
        },
    }
    if stamp != expected:
        raise MathpubError("MP-PROVENANCE-002", "PDF source stamp does not match its manifest")
    return stamp
