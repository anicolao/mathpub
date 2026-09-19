"""Derive a separate, conservatively verified print artifact from a manifest."""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
import tempfile
from pathlib import Path

import pypdf
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    ByteStringObject,
    DictionaryObject,
    FloatObject,
    IndirectObject,
    NullObject,
    NumberObject,
    StreamObject,
)

from mathpub import __version__
from mathpub.errors import MathpubError
from mathpub.provenance import verify_stamp

POLICY = "remove-invisible-links-v1"


def _hash(payload):
    return hashlib.sha256(payload).hexdigest()


def manifest_artifact(manifest_path: Path, projection: str):
    """Resolve and hash exactly one complete, clean-source manifest projection.

    Verify historical artifacts independently of today's working tree or HEAD.
    These are consistency checks, not proof that a manifest is authentic.
    """
    payload = manifest_path.read_bytes()
    manifest = json.loads(payload)
    if type(manifest.get("schema")) is not int or manifest["schema"] != 1:
        raise ValueError("unsupported manifest schema")
    if manifest.get("lesson_ids") != [] or manifest.get("publication_id", "").startswith(
        "preview."
    ):
        raise ValueError("print export requires a full publication, not a scoped preview")
    if not manifest.get("publication_id"):
        raise ValueError("manifest is missing publication identity")
    source = manifest.get("source", {})
    revision = source.get("git_commit", "")
    if (
        source.get("dirty") is not False
        or not isinstance(revision, str)
        or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision)
    ):
        raise ValueError("manifest must record a known, clean source revision")
    outputs = [entry for entry in manifest["outputs"] if entry["projection"] == projection]
    if len(outputs) != 1:
        raise ValueError("projection must occur exactly once in the manifest")
    output = outputs[0]
    relative = Path(output["path"])
    base = manifest_path.resolve().parent
    path = (base / relative).resolve()
    if relative.is_absolute() or not path.is_relative_to(base):
        raise ValueError("manifest artifact must stay inside its edition directory")
    pdf = path.read_bytes()
    if _hash(pdf) != output["sha256"]:
        raise ValueError("PDF bytes do not match the manifest hash")
    return manifest, output, pdf, _hash(payload)


def _canonical(value, ancestors=()):
    """Public decoded-stream API; never depend on pypdf's private encoded data."""
    if isinstance(value, IndirectObject):
        value = value.get_object()
    if id(value) in ancestors:
        return {"cycle": True}
    if len(ancestors) >= 128:
        raise ValueError("resource graph is excessively nested")
    ancestors = (*ancestors, id(value))
    if isinstance(value, DictionaryObject):
        skipped = (
            {"/Length", "/Filter", "/DecodeParms"} if isinstance(value, StreamObject) else set()
        )
        result = {
            str(key): _canonical(item, ancestors)
            for key, item in sorted(value.items())
            if key not in skipped
        }
        if isinstance(value, StreamObject):
            result["decoded_sha256"] = _hash(value.get_data())
        return result
    if isinstance(value, ArrayObject):
        return [_canonical(item, ancestors) for item in value]
    if isinstance(value, ByteStringObject):
        return {"bytes": bytes(value).hex()}
    if isinstance(value, BooleanObject):
        return value.value
    if isinstance(value, NullObject):
        return None
    if isinstance(value, (FloatObject, NumberObject)):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("non-finite PDF resource number")
        return result
    if isinstance(value, str):
        return str(value)
    raise ValueError(f"unsupported PDF resource type: {type(value).__name__}")


def _fingerprint(reader):
    return {
        "metadata": dict(reader.metadata or {}),
        "page_labels": reader.page_labels,
        "pages": [
            {
                "boxes": {
                    name: list(getattr(page, name))
                    for name in (
                        "mediabox",
                        "cropbox",
                        "trimbox",
                        "bleedbox",
                        "artbox",
                    )
                },
                "rotation": page.rotation,
                "user_unit": page.user_unit,
                "contents": _canonical(page.get_contents())
                if page.get_contents() is not None
                else None,
                "resources": _canonical(page["/Resources"]) if "/Resources" in page else {},
            }
            for page in reader.pages
        ],
    }


def _check_annotation(annotation):
    annotation = annotation.get_object()
    if annotation.get("/Subtype") != "/Link" or any(
        key in annotation for key in ("/AP", "/StructParent", "/OC")
    ):
        raise ValueError("only untagged links without appearances can be removed")
    # The PDF default link border is visible. Absence does not mean zero width.
    style = annotation.get("/BS")
    border = annotation.get("/Border", [0, 0, 1])
    width = style.get_object().get("/W", 1) if style is not None else border[2]
    if float(width) != 0:
        raise ValueError("link has a visible border; refusing to change printed appearance")


def export_print(manifest_path: Path, projection: str, destination: Path, *, policy: str):
    """Stage, verify, then publish a new directory; never replace an existing export.

    receipt.json is the completion marker. The destination is reserved with mkdir
    (not an overwriting rename), and no PDF is published until verification passes.
    """
    reserved = False
    published = []
    try:
        if policy != POLICY:
            raise ValueError(f"unsupported export policy: {policy}")
        if destination.exists():
            raise ValueError("export destination already exists; choose a new directory")
        manifest, output, source_bytes, manifest_hash = manifest_artifact(manifest_path, projection)
        reader = PdfReader(io.BytesIO(source_bytes), strict=True)
        if reader.is_encrypted:
            raise ValueError("encrypted PDFs are not supported")
        if not reader.pages or len(reader.pages) != output["pages"]:
            raise ValueError("PDF page count does not match the manifest")
        if manifest.get("source_stable") is not True:
            raise ValueError("export requires a source-stable build; rebuild legacy editions")
        verify_stamp(reader, manifest, projection)
        root = reader.root_object
        if any(key in root for key in ("/AcroForm", "/StructTreeRoot", "/Perms")):
            raise ValueError(
                "forms, tagged PDFs, and signed/restricted PDFs need a separate policy"
            )
        annotations = 0
        for page in reader.pages:
            for annotation in page.get("/Annots", []):
                _check_annotation(annotation)
                annotations += 1
        before = _fingerprint(reader)
        writer = PdfWriter(clone_from=reader)
        for page in writer.pages:
            for key in ("/Annots", "/AA"):
                if key in page:
                    del page[key]
        for key in ("/OpenAction", "/AA"):
            if key in writer.root_object:
                del writer.root_object[key]
        names = writer.root_object.get("/Names")
        if names is not None and "/JavaScript" in names.get_object():
            del names.get_object()["/JavaScript"]
        with tempfile.TemporaryDirectory(prefix=".mathpub-export-", dir=destination.parent) as work:
            staging = Path(work)
            staged_pdf = staging / "print.pdf"
            writer.write(staged_pdf)
            result = staged_pdf.read_bytes()
            exported = PdfReader(io.BytesIO(result), strict=True)
            if _fingerprint(exported) != before:
                raise ValueError(
                    "export changed drawing resources, page geometry, labels, or metadata"
                )
            if any(page.get("/Annots") or page.get("/AA") for page in exported.pages):
                raise ValueError("export retained annotations or page actions")
            receipt = {
                "schema": 1,
                "policy": policy,
                "publication_id": manifest["publication_id"],
                "projection": projection,
                "source": manifest["source"],
                "manifest_sha256": manifest_hash,
                "input": {"sha256": _hash(source_bytes), "bytes": len(source_bytes)},
                "output": {
                    "path": "print.pdf",
                    "sha256": _hash(result),
                    "bytes": len(result),
                    "pages": len(exported.pages),
                },
                "tools": {
                    "mathpub": __version__,
                    "pypdf": pypdf.__version__,
                    "exporter_sha256": _hash(Path(__file__).read_bytes()),
                },
                "removed_links": annotations,
                "verified": [
                    "manifest_hash",
                    "clean_source_record",
                    "complete_publication",
                    "page_count",
                    "all_page_boxes",
                    "rotation",
                    "user_unit",
                    "decoded_content_and_resources",
                    "metadata",
                    "page_labels",
                ],
                "limitations": [
                    "Manifest and embedded provenance are unsigned consistency evidence.",
                    "Decoded resources are compared, not compression bytes or rendered pixels.",
                    "This is not a security sanitizer or a printer-acceptance certification.",
                    "A full projection does not establish a complete multi-artifact release.",
                ],
            }
            staged_receipt = staging / "receipt.json"
            staged_receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
            destination.mkdir()
            reserved = True
            for source in (staged_pdf, staged_receipt):
                target = destination / source.name
                source.rename(target)
                published.append(target)
            return receipt
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        IndexError,
        AttributeError,
        RecursionError,
        OverflowError,
        NotImplementedError,
        pypdf.errors.PyPdfError,
    ) as error:
        if reserved:
            for path in published:
                path.unlink(missing_ok=True)
            destination.rmdir()
        raise MathpubError("MP-EXPORT-001", f"cannot export print PDF: {error}") from error
