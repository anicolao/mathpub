"""Portable before/after review with hash-bound progress and explicit deleted pages."""

from __future__ import annotations

import hashlib
import html
import io
import json
import math
import shutil
from importlib.resources import files
from pathlib import Path

from PIL import Image
from pypdf import PdfReader

from mathpub.config import load_toml
from mathpub.errors import MathpubError
from mathpub.pdf_render import render_page, renderer_versions, text_pages


def _shingles(text: str) -> set:
    words = text.lower().split()
    size = min(5, len(words))
    return {tuple(words[i : i + size]) for i in range(len(words) - size + 1)} if words else set()


def align_pages(before: list[str], after: list[str]) -> list[tuple[int | None, int | None]]:
    """Nearby monotonic text alignment; pixels, not this heuristic, determine changes."""
    pairs = []
    left = right = 0
    a, b = list(map(_shingles, before)), list(map(_shingles, after))
    while left < len(a) and right < len(b):
        candidates = []
        for i in range(left, min(left + 5, len(a))):
            for j in range(right, min(right + 5, len(b))):
                union = a[i] | b[j]
                score = len(a[i] & b[j]) / len(union) if union else 1.0
                candidates.append((score - 0.01 * (i - left + j - right), i, j))
        score, i, j = max(candidates, key=lambda item: (item[0], -item[1], -item[2]))
        if score < 0.4:
            i, j = left, right
        pairs.extend((n, None) for n in range(left, i))
        pairs.extend((None, n) for n in range(right, j))
        pairs.append((i, j))
        left, right = i + 1, j + 1
    pairs.extend((i, None) for i in range(left, len(a)))
    pairs.extend((None, j) for j in range(right, len(b)))
    return pairs


def create_review(
    before: Path,
    after: Path,
    output: Path,
    *,
    dpi: int = 150,
    crop_pt: tuple[float, float, float, float] = (0, 0, 0, 0),
    pages: list[int] | None = None,
    cache: Path | None = None,
    label: str = "Edition comparison",
    notes: str = "",
    baseline_revision: str = "",
    attachments: list[Path] | None = None,
) -> dict:
    if (
        not 36 <= dpi <= 300
        or len(crop_pt) != 4
        or any(not math.isfinite(v) or v < 0 for v in crop_pt)
    ):
        raise MathpubError("MP-REVIEW-001", "invalid review DPI or crop margins")
    if output.exists():
        raise MathpubError("MP-REVIEW-001", "review output already exists")
    try:
        data = [before.read_bytes(), after.read_bytes()]
        hashes = [hashlib.sha256(value).hexdigest() for value in data]
        extracted = [text_pages(value) for value in data]
        readers = [PdfReader(io.BytesIO(value)) for value in data]
        versions = renderer_versions()
        evidence = [(path.name, path.read_bytes()) for path in attachments or []]
        context = {
            "notes": notes,
            "baseline_revision": baseline_revision,
            "provenance_note": (
                "Author-supplied context and attachments; not verified PDF provenance."
            ),
            "attachments": [
                {
                    "label": name,
                    "path": f"evidence-{i}.bin",
                    "sha256": hashlib.sha256(value).hexdigest(),
                    "bytes": len(value),
                }
                for i, (name, value) in enumerate(evidence)
            ],
        }
        render_key = hashlib.sha256(json.dumps(versions, sort_keys=True).encode()).hexdigest()[:16]
        key = hashlib.sha256(
            json.dumps([hashes, dpi, crop_pt, pages, versions, context]).encode()
        ).hexdigest()
        report = {
            "schema": 1,
            "label": label,
            "key": key,
            "pdf_sha256": hashes,
            "dpi": dpi,
            "tools": versions,
            "excluded_margins_pt": crop_pt,
            "pairs": [],
            "context": context,
            "alignment": "Nearby text-shingle heuristic; inspect unmatched and modified pages.",
            "progress": "Local reviewed marks are progress records, not editorial approval.",
        }
        output.mkdir()
        for record, (_, value) in zip(context["attachments"], evidence, strict=True):
            (output / record["path"]).write_bytes(value)
        for name, value in zip(("before.pdf", "after.pdf"), data, strict=True):
            (output / name).write_bytes(value)
        cache = cache or output / "cache"
        cache.mkdir(parents=True, exist_ok=True)
        fingerprints = {}

        def page_image(side, index):
            if index is None:
                return None
            name = f"{('before', 'after')[side]}-{index + 1}.png"
            cached = cache / f"{hashes[side]}-{index + 1}-{dpi}-{render_key}.png"
            if not cached.is_file():
                render_page(output / ("before.pdf", "after.pdf")[side], index + 1, cached, dpi)
            shutil.copyfile(cached, output / name)
            with Image.open(cached) as image:
                left, top, right, bottom = (round(v * dpi / 72) for v in crop_pt)
                if left + right >= image.width or top + bottom >= image.height:
                    raise ValueError("crop removes the whole page")
                cropped = image.convert("RGB").crop(
                    (left, top, image.width - right, image.height - bottom)
                )
                fingerprints[side, index] = hashlib.sha256(
                    str(cropped.size).encode() + cropped.tobytes()
                ).hexdigest()
            return {"page": index + 1, "label": readers[side].page_labels[index], "image": name}

        for i, j in align_pages(*[[page["text"] for page in side] for side in extracted]):
            if pages and not any(index is not None and index + 1 in pages for index in (i, j)):
                continue
            a, b = page_image(0, i), page_image(1, j)
            status = (
                "inserted"
                if i is None
                else "deleted"
                if j is None
                else "unchanged"
                if fingerprints[0, i] == fingerprints[1, j]
                else "modified"
            )
            report["pairs"].append(
                {
                    "before": a,
                    "after": b,
                    "status": status,
                    "text": " ".join(
                        extracted[side][index]["text"]
                        for side, index in enumerate((i, j))
                        if index is not None
                    ),
                }
            )
        (output / "review.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        (output / "index.html").write_text(review_html(report))
        return report
    except (OSError, ValueError, KeyError) as error:
        raise MathpubError("MP-REVIEW-001", f"cannot create edition review: {error}") from error


def review_html(report: dict) -> str:
    cards = []
    for number, pair in enumerate(report["pairs"]):
        images = []
        for side in ("before", "after"):
            page = pair[side]
            images.append(
                f"<figure><figcaption>{side}: physical {page['page']}, label "
                f'{html.escape(str(page["label"]))}</figcaption><img loading="lazy" '
                f'src="{page["image"]}" alt="{side} page {page["page"]}"></figure>'
                if page
                else f"<figure>{side}: no matching page</figure>"
            )
        book = str(pair.get("book", "0"))
        description = " / ".join(
            f"{side}: PDF {pair[side]['page']}, printed {pair[side]['label']}"
            for side in ("before", "after")
            if pair[side]
        )
        cards.append(
            f'<section data-book="{html.escape(book, quote=True)}" '
            f'data-description="{html.escape(description, quote=True)}" '
            f'data-status="{pair["status"]}" '
            f'data-text="{html.escape(pair["text"].lower(), quote=True)}">'
            f'<h2>{number + 1}: {pair["status"]} <label><input type="checkbox" '
            f'data-id="{number}">Reviewed</label></h2><div class="pair">'
            + "".join(images)
            + "</div></section>"
        )
    books = report.get(
        "books",
        [
            {
                "id": "0",
                "label": report["label"],
                "before": "before.pdf",
                "after": "after.pdf",
                "context": report.get("context", {}),
            }
        ],
    )
    links = []
    for book in books:
        context = book.get("context", {})
        evidence_links = " ".join(
            f'<a download href="{html.escape(a["path"], quote=True)}">'
            f"{html.escape(a['label'])}</a> (SHA-256 {a['sha256']})"
            for a in context.get("attachments", [])
        )
        links.append(
            f"<li>{html.escape(book['label'])}: "
            f'<a href="{book["before"]}">Full before PDF</a> · '
            f'<a href="{book["after"]}">Full after PDF</a>'
            f"<p>{html.escape(context.get('notes', ''))}</p>"
            f"<p>Baseline revision (author supplied): "
            f"{html.escape(context.get('baseline_revision', '') or 'not supplied')}</p>"
            f"<p>{html.escape(context.get('provenance_note', ''))}</p>{evidence_links}</li>"
        )
    options = "".join(
        f'<option value="{book["id"]}">{html.escape(book["label"])}</option>' for book in books
    )
    document = (
        """<!doctype html><meta charset="utf-8"><title>Edition review</title>
<style>body{font:16px system-ui;margin:2em;background:#eee}header{position:sticky;top:0;
background:white;padding:1em;z-index:1}.pair{display:flex;gap:1em}figure{flex:1;margin:0}
img{width:100%;cursor:zoom-in}section{background:white;padding:1em;margin:1em 0}
section{width:calc(100% * var(--zoom,1));box-sizing:border-box}
h2{font-size:1em}label{margin-left:1em}[hidden]{display:none}</style>
<header><h1>"""
        + html.escape(report["label"])
        + """</h1>
<p>Local progress, not editorial approval. Alignment is heuristic.</p>
<p>Excluded margins (left/top/right/bottom PDF pt): """
        + html.escape(str(report["excluded_margins_pt"]))
        + "</p><details><summary>Complete PDFs and review context</summary><ul>"
        + "".join(links)
        + "</ul></details>"
        + '<label>Publication <select id="book"><option value="">All publications</option>'
        + options
        + "</select></label>"
        + """<label>Page <select id="page"></select></label>
<label>Zoom <select id="zoom"></select></label>
<input id="filter" placeholder="Filter page content"><label><input id="changed" type="checkbox">
Changes only</label><button id="prev">Previous</button><button id="next">Next</button>
<button id="export">Export progress</button><span id="count"></span></header>"""
        + "".join(cards)
    )
    # Keep interaction logic testable while retaining a self-contained offline HTML artifact.
    script = files("mathpub").joinpath("review_viewer.js").read_text(encoding="utf-8")
    return (
        document
        + "<script>const key="
        + json.dumps("mathpub-review-" + report["key"])
        + ";\n"
        + script
        + "</script>"
    )


def create_review_set(config_path: Path, output: Path, *, allowed_root: Path | None = None) -> dict:
    config = load_toml(config_path, "review-set")
    if allowed_root is not None:
        for book in config["books"]:
            for value in [book["before"], book["after"], *book.get("attachments", [])]:
                if (
                    not (config_path.parent / value)
                    .resolve()
                    .is_relative_to(allowed_root.resolve())
                ):
                    raise MathpubError(
                        "MP-REVIEW-001", "review inputs must stay inside the library"
                    )
    if output.exists():
        raise MathpubError("MP-REVIEW-001", "review output already exists")
    output.mkdir()
    books, pairs, keys = [], [], []
    for i, book in enumerate(config["books"]):
        folder = str(i)
        report = create_review(
            config_path.parent / book["before"],
            config_path.parent / book["after"],
            output / folder,
            label=book["label"],
            dpi=config.get("dpi", 150),
            notes=book.get("notes", ""),
            baseline_revision=book.get("baseline_revision", ""),
            attachments=[config_path.parent / p for p in book.get("attachments", [])],
        )
        keys.append(report["key"])
        context = report["context"]
        for item in context["attachments"]:
            item["path"] = f"{folder}/{item['path']}"
        books.append(
            {
                "id": folder,
                "label": book["label"],
                "before": f"{folder}/before.pdf",
                "after": f"{folder}/after.pdf",
                "context": context,
            }
        )
        for pair in report["pairs"]:
            pair["book"] = folder
            for side in ("before", "after"):
                if pair[side]:
                    pair[side]["image"] = f"{folder}/{pair[side]['image']}"
            pairs.append(pair)
    result = {
        "schema": 1,
        "label": config.get("label", "Publication review"),
        "books": books,
        "pairs": pairs,
        "excluded_margins_pt": [0, 0, 0, 0],
        "key": hashlib.sha256(json.dumps(keys).encode()).hexdigest(),
    }
    (output / "review.json").write_text(json.dumps(result, indent=2) + "\n")
    (output / "index.html").write_text(review_html(result))
    return result
