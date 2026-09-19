"""Declarative, immutable release sets with per-book provenance."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import tempfile
from pathlib import Path

from pypdf import PdfReader

from mathpub.config import load_toml
from mathpub.errors import MathpubError
from mathpub.print_export import manifest_artifact
from mathpub.provenance import verify_stamp


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inside(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    if Path(name).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError(f"artifact escapes its bundle: {name}")
    return path


def check_release(config_path: Path) -> dict:
    try:
        config = load_toml(config_path, "release")
        books = []
        ids = set()
        for book in config["books"]:
            if book["id"] in ids:
                raise ValueError("duplicate book identity")
            ids.add(book["id"])
            artifacts, roles, revisions = [], set(), set()
            for item in book["artifacts"]:
                if item["role"] in roles:
                    raise ValueError("duplicate artifact role")
                roles.add(item["role"])
                manifest_path = (config_path.parent / item["manifest"]).resolve()
                manifest, output, data, manifest_hash = manifest_artifact(
                    manifest_path, item["projection"]
                )
                if manifest.get("source_stable") is not True:
                    raise ValueError("release requires a source-stable build")
                if not manifest["source"].get("tree_sha256"):
                    raise ValueError("release requires a known source tree fingerprint")
                stamp = verify_stamp(PdfReader(io.BytesIO(data)), manifest, item["projection"])
                path = inside(manifest_path.parent, output["path"])
                receipt_hash = None
                if "receipt" in item:
                    receipt_path = (config_path.parent / item["receipt"]).resolve()
                    receipt_data = receipt_path.read_bytes()
                    receipt = json.loads(receipt_data)
                    if (
                        receipt["manifest_sha256"] != manifest_hash
                        or receipt["projection"] != item["projection"]
                        or receipt["input"]["sha256"] != output["sha256"]
                    ):
                        raise ValueError(
                            "export receipt does not derive from this manifest projection"
                        )
                    path = inside(receipt_path.parent, receipt["output"]["path"])
                    data = path.read_bytes()
                    if sha256(data) != receipt["output"]["sha256"]:
                        raise ValueError("export bytes do not match receipt")
                    verify_stamp(PdfReader(io.BytesIO(data)), manifest, item["projection"])
                    receipt_hash = sha256(receipt_data)
                revisions.add((stamp["source"]["git_commit"], stamp["source"]["tree_sha256"]))
                reader = PdfReader(io.BytesIO(data))
                if len(reader.pages) != output["pages"]:
                    raise ValueError("page count differs from manifest")
                artifacts.append(
                    {
                        "role": item["role"],
                        "path": str(path),
                        "sha256": sha256(data),
                        "bytes": len(data),
                        "pages": len(reader.pages),
                        "stamp": stamp,
                        "manifest_sha256": manifest_hash,
                        "receipt_sha256": receipt_hash,
                    }
                )
            if len(revisions) != 1:
                raise ValueError(
                    "cover/interior artifacts must have the same source revision and tree"
                )
            if not set(book["required_roles"]).issubset(roles):
                raise ValueError("release is missing a required artifact role")
            books.append(
                {"id": book["id"], "required_roles": book["required_roles"], "artifacts": artifacts}
            )
        return {
            "schema": 1,
            "id": config["id"],
            "config_sha256": sha256(config_path.read_bytes()),
            "books": books,
            "limitations": ["Unsigned consistency evidence, not authenticity."],
        }
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise MathpubError("MP-RELEASE-001", f"invalid release: {error}") from error


def assemble_release(config_path: Path, destination: Path) -> dict:
    report = check_release(config_path)
    if destination.exists():
        raise MathpubError("MP-RELEASE-002", "release destination already exists")
    try:
        with tempfile.TemporaryDirectory(
            prefix=".mathpub-release-", dir=destination.parent
        ) as temp:
            staging = Path(temp) / "bundle"
            staging.mkdir()
            for book in report["books"]:
                folder = staging / book["id"]
                folder.mkdir()
                for artifact in book["artifacts"]:
                    path = folder / f"{artifact['role']}.pdf"
                    shutil.copyfile(artifact["path"], path)
                    artifact["path"] = str(path.relative_to(staging))
            (staging / "release.json").write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n"
            )
            verify_release(staging)
            # Reserve rather than overwrite a previous nonempty bundle.
            destination.mkdir()
            try:
                for child in staging.iterdir():
                    child.rename(destination / child.name)
            except OSError:
                # An incomplete bundle never has a valid set of artifact hashes.
                raise
        return report
    except OSError as error:
        raise MathpubError("MP-RELEASE-002", f"cannot publish release: {error}") from error


def verify_release(directory: Path) -> dict:
    try:
        report = json.loads((directory / "release.json").read_text())
        if report["schema"] != 1 or not report["books"]:
            raise ValueError("unsupported or empty release index")
        ids = set()
        for book in report["books"]:
            if book["id"] in ids:
                raise ValueError("duplicate book")
            ids.add(book["id"])
            roles, sources = set(), set()
            for artifact in book["artifacts"]:
                if artifact["role"] in roles:
                    raise ValueError("duplicate role")
                roles.add(artifact["role"])
                data = inside(directory, artifact["path"]).read_bytes()
                if sha256(data) != artifact["sha256"] or len(data) != artifact["bytes"]:
                    raise ValueError("release artifact bytes changed")
                stamp = artifact["stamp"]
                manifest = {**stamp, "source_stable": True}
                reader = PdfReader(io.BytesIO(data))
                verify_stamp(reader, manifest, stamp["projection"])
                if stamp["lesson_ids"] or stamp["source"]["dirty"] is not False:
                    raise ValueError("release contains scoped or dirty-source artifact")
                if len(reader.pages) != artifact["pages"]:
                    raise ValueError("release page count mismatch")
                sources.add(json.dumps(stamp["source"], sort_keys=True))
            if len(sources) != 1 or not set(book["required_roles"]).issubset(roles):
                raise ValueError("incomplete or mixed-source book")
        return report
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise MathpubError("MP-RELEASE-003", f"cannot verify release: {error}") from error
