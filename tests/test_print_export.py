import hashlib
import json

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    RectangleObject,
    TextStringObject,
)

from mathpub.cli import main
from mathpub.errors import MathpubError
from mathpub.print_export import POLICY, _fingerprint, export_print
from tests.test_preflight import pdf


def edition(tmp_path, *, configure=None, patch=None):
    path = pdf(tmp_path, b"0.5 w 0 0 m 20 20 l S BT /F1 12 Tf (Example) Tj ET", configure=configure)
    writer = PdfWriter(clone_from=path)
    stamp = {
        "schema": 1,
        "publication_id": "synthetic.book",
        "projection": "student",
        "lesson_ids": [],
        "source": {"git_commit": "a" * 40, "dirty": False, "tree_sha256": "c" * 64},
    }
    writer.add_metadata({"/MathpubProvenance": json.dumps(stamp)})
    writer.write(path)
    manifest = {
        "source_stable": True,
        "schema": 1,
        "publication_id": "synthetic.book",
        "lesson_ids": [],
        "source": stamp["source"],
        "outputs": [
            {"projection": "answers", "path": "not-selected.pdf", "sha256": "b" * 64, "pages": 2},
            {
                "projection": "student",
                "path": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "pages": 1,
            },
        ],
    }
    if patch:
        patch(manifest)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    return manifest_path, path


def link(page, *, width=0, subtype="/Link", appearance=False):
    annotation = DictionaryObject(
        {
            NameObject("/Subtype"): NameObject(subtype),
            NameObject("/Rect"): RectangleObject([0, 0, 20, 20]),
            NameObject("/Border"): ArrayObject(
                [NumberObject(0), NumberObject(0), NumberObject(width)]
            ),
            NameObject("/A"): DictionaryObject(
                {
                    NameObject("/S"): NameObject("/URI"),
                    NameObject("/URI"): TextStringObject("https://example.invalid"),
                }
            ),
        }
    )
    if appearance:
        annotation[NameObject("/AP")] = DictionaryObject()
    page[NameObject("/Annots")] = ArrayObject([annotation])


def test_export_selects_projection_preserves_input_and_records_derivation(tmp_path):
    manifest, original = edition(tmp_path, configure=link)
    before = original.read_bytes()
    output = tmp_path / "export"
    receipt = export_print(manifest, "student", output, policy=POLICY)
    assert original.read_bytes() == before
    assert PdfReader(original).pages[0]["/Annots"]
    exported = PdfReader(output / "print.pdf")
    assert "/Annots" not in exported.pages[0]
    assert _fingerprint(exported) == _fingerprint(PdfReader(original))
    assert receipt["removed_links"] == 1
    assert receipt["input"]["sha256"] == hashlib.sha256(before).hexdigest()
    assert (
        receipt["output"]["sha256"]
        == hashlib.sha256((output / "print.pdf").read_bytes()).hexdigest()
    )
    assert json.loads((output / "receipt.json").read_text()) == receipt
    assert receipt["source"]["git_commit"] == "a" * 40


@pytest.mark.parametrize(
    "kwargs",
    [
        {"width": 1},
        {"subtype": "/Text"},
        {"appearance": True},
    ],
)
def test_appearance_changing_annotations_are_rejected(tmp_path, kwargs):
    manifest, _ = edition(tmp_path, configure=lambda page: link(page, **kwargs))
    output = tmp_path / "export"
    with pytest.raises(MathpubError):
        export_print(manifest, "student", output, policy=POLICY)
    assert not output.exists()


def test_default_border_is_visible(tmp_path):
    def configure(page):
        link(page)
        del page["/Annots"][0]["/Border"]

    manifest, _ = edition(tmp_path, configure=configure)
    with pytest.raises(MathpubError, match="visible border"):
        export_print(manifest, "student", tmp_path / "export", policy=POLICY)


@pytest.mark.parametrize(
    "patch",
    [
        lambda m: m["source"].update(dirty=True),
        lambda m: m["source"].update(dirty=None),
        lambda m: m["source"].update(git_commit=None),
        lambda m: m.update(lesson_ids=["lesson-one"]),
        lambda m: m.update(publication_id="preview.example"),
        lambda m: m["outputs"][1].update(sha256="0" * 64),
        lambda m: m["outputs"][1].update(pages=2),
        lambda m: m["outputs"].append(m["outputs"][1]),
        lambda m: m["outputs"][1].update(path="../escape.pdf"),
    ],
)
def test_invalid_provenance_or_manifest_is_rejected(tmp_path, patch):
    manifest, _ = edition(tmp_path, patch=patch)
    with pytest.raises(MathpubError):
        export_print(manifest, "student", tmp_path / "export", policy=POLICY)
    assert not (tmp_path / "export").exists()


def test_existing_export_is_never_overwritten(tmp_path):
    manifest, _ = edition(tmp_path)
    output = tmp_path / "export"
    output.mkdir()
    preserved = output / "receipt.json"
    preserved.write_text("prior export")
    with pytest.raises(MathpubError, match="already exists"):
        export_print(manifest, "student", output, policy=POLICY)
    assert preserved.read_text() == "prior export"


@pytest.mark.parametrize("key", ["/AcroForm", "/StructTreeRoot", "/Perms"])
def test_document_structures_requiring_distinct_policy_are_rejected(tmp_path, key):
    manifest, original = edition(tmp_path)
    writer = PdfWriter(clone_from=original)
    writer.root_object[NameObject(key)] = DictionaryObject()
    writer.write(original)
    data = json.loads(manifest.read_text())
    data["outputs"][1]["sha256"] = hashlib.sha256(original.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(data))
    with pytest.raises(MathpubError, match="separate policy"):
        export_print(manifest, "student", tmp_path / "export", policy=POLICY)


def test_page_boxes_rotation_labels_metadata_and_resources_survive(tmp_path):
    def configure(page):
        page.rotate(90)
        page[NameObject("/TrimBox")] = RectangleObject([10, 20, 400, 600])

    manifest, original = edition(tmp_path, configure=configure)
    writer = PdfWriter(clone_from=original)
    writer.add_metadata({"/Title": "Synthetic book", "/Author": "Test Author"})
    writer.set_page_label(0, 0, prefix="preface-")
    writer.write(original)
    data = json.loads(manifest.read_text())
    data["outputs"][1]["sha256"] = hashlib.sha256(original.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(data))
    receipt = export_print(manifest, "student", tmp_path / "export", policy=POLICY)
    assert receipt["output"]["pages"] == 1
    assert _fingerprint(PdfReader(original)) == _fingerprint(
        PdfReader(tmp_path / "export/print.pdf")
    )


def test_drawing_change_is_detected_before_publication(tmp_path, monkeypatch):
    manifest, _ = edition(tmp_path)
    real_write = PdfWriter.write

    def corrupt(self, path):
        self.pages[0]["/Contents"].set_data(b"0 0 m 100 100 l S")
        return real_write(self, path)

    monkeypatch.setattr(PdfWriter, "write", corrupt)
    with pytest.raises(MathpubError, match="changed drawing"):
        export_print(manifest, "student", tmp_path / "export", policy=POLICY)
    assert not (tmp_path / "export").exists()
    assert not list(tmp_path.glob(".mathpub-export-*"))


def test_page_actions_are_removed(tmp_path):
    def configure(page):
        page[NameObject("/AA")] = DictionaryObject(
            {
                NameObject("/O"): DictionaryObject(
                    {
                        NameObject("/S"): NameObject("/JavaScript"),
                        NameObject("/JS"): TextStringObject("app.alert('synthetic');"),
                    }
                ),
            }
        )

    manifest, original = edition(tmp_path, configure=configure)
    export_print(manifest, "student", tmp_path / "export", policy=POLICY)
    assert "/AA" in PdfReader(original).pages[0]
    assert "/AA" not in PdfReader(tmp_path / "export/print.pdf").pages[0]


def test_receipt_publication_failure_rolls_back_own_output(tmp_path, monkeypatch):
    from pathlib import Path

    manifest, _ = edition(tmp_path)
    real_rename = Path.rename

    def fail_receipt(self, target):
        if self.name == "receipt.json":
            raise OSError("synthetic receipt write failure")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", fail_receipt)
    with pytest.raises(MathpubError, match="receipt write failure"):
        export_print(manifest, "student", tmp_path / "export", policy=POLICY)
    assert not (tmp_path / "export").exists()
    assert not list(tmp_path.glob(".mathpub-export-*"))


def test_cli_requires_explicit_policy_and_works_outside_project(tmp_path, monkeypatch, capsys):
    manifest, _ = edition(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert (
        main(
            [
                "export-print",
                str(manifest),
                "--projection",
                "student",
                "--output",
                "export",
                "--policy",
                POLICY,
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["data"]["projection"] == "student"
