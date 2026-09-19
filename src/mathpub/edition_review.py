"""Portable before/after review with hash-bound progress and explicit deleted pages."""

from __future__ import annotations

import hashlib
import html
import io
import json
import shutil
from pathlib import Path

from PIL import Image
from pypdf import PdfReader

from mathpub.errors import MathpubError
from mathpub.pdf_render import render_page, text_pages


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
) -> dict:
    if not 36 <= dpi <= 300 or len(crop_pt) != 4 or any(v < 0 for v in crop_pt):
        raise MathpubError("MP-REVIEW-001", "invalid review DPI or crop margins")
    if output.exists():
        raise MathpubError("MP-REVIEW-001", "review output already exists")
    try:
        data = [before.read_bytes(), after.read_bytes()]
        hashes = [hashlib.sha256(value).hexdigest() for value in data]
        extracted = [text_pages(value) for value in data]
        readers = [PdfReader(io.BytesIO(value)) for value in data]
        key = hashlib.sha256(json.dumps([hashes, dpi, crop_pt, pages]).encode()).hexdigest()
        report = {
            "schema": 1,
            "label": label,
            "key": key,
            "pdf_sha256": hashes,
            "dpi": dpi,
            "excluded_margins_pt": crop_pt,
            "pairs": [],
            "alignment": "Nearby text-shingle heuristic; inspect unmatched and modified pages.",
            "progress": "Local reviewed marks are progress records, not editorial approval.",
        }
        output.mkdir()
        for name, value in zip(("before.pdf", "after.pdf"), data, strict=True):
            (output / name).write_bytes(value)
        cache = cache or output / "cache"
        cache.mkdir(parents=True, exist_ok=True)
        fingerprints = {}

        def page_image(side, index):
            if index is None:
                return None
            name = f"{('before', 'after')[side]}-{index + 1}.png"
            cached = cache / f"{hashes[side]}-{index + 1}-{dpi}.png"
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
        cards.append(
            f'<section data-status="{pair["status"]}" '
            f'data-text="{html.escape(pair["text"].lower(), quote=True)}">'
            f'<h2>{number + 1}: {pair["status"]} <label><input type="checkbox" '
            f'data-id="{number}">Reviewed</label></h2><div class="pair">'
            + "".join(images)
            + "</div></section>"
        )
    return (
        """<!doctype html><meta charset="utf-8"><title>Edition review</title>
<style>body{font:16px system-ui;margin:2em;background:#eee}header{position:sticky;top:0;
background:white;padding:1em;z-index:1}.pair{display:flex;gap:1em}figure{flex:1;margin:0}
img{width:100%;cursor:zoom-in}section{background:white;padding:1em;margin:1em 0}
section.zoom{width:1800px}h2{font-size:1em}label{margin-left:1em}[hidden]{display:none}</style>
<header><h1>"""
        + html.escape(report["label"])
        + """</h1>
<p>Local progress, not editorial approval. Alignment is heuristic. Click a page to zoom.</p>
<p>Excluded margins (left/top/right/bottom PDF pt): """
        + html.escape(str(report["excluded_margins_pt"]))
        + """</p>
<input id="filter" placeholder="Filter page content"><label><input id="changed" type="checkbox">
Changes only</label><button id="prev">Previous</button><button id="next">Next</button>
<button id="export">Export progress</button><span id="count"></span></header>"""
        + "".join(cards)
        + """
<script>
const key="mathpub-review-"+"""
        + json.dumps(report["key"])
        + """;
let done={};try{done=JSON.parse(localStorage.getItem(key)||'{}')}catch(e){}
const cards=[...document.querySelectorAll('section')];let index=0;
const count=()=>document.querySelector('#count').textContent=
Object.values(done).filter(Boolean).length+' reviewed';
document.querySelectorAll('[data-id]').forEach(input=>{input.checked=!!done[input.dataset.id];
input.onchange=()=>{done[input.dataset.id]=input.checked;
try{localStorage.setItem(key,JSON.stringify(done))}catch(e){}count()}});
const filter=()=>cards.forEach(card=>card.hidden=(document.querySelector('#changed').checked
&&card.dataset.status==='unchanged')
||!card.dataset.text.includes(document.querySelector('#filter').value.toLowerCase()));
document.querySelector('#filter').oninput=filter;document.querySelector('#changed').onchange=filter;
const move=d=>{const visible=cards.filter(c=>!c.hidden);
index=Math.max(0,Math.min(visible.length-1,index+d));visible[index]?.scrollIntoView()};
document.querySelector('#prev').onclick=()=>move(-1);document.querySelector('#next').onclick=()=>move(1);
document.onkeydown=e=>{if(e.target.tagName==='INPUT')return;
if(e.key==='ArrowLeft')move(-1);if(e.key==='ArrowRight')move(1)};
document.querySelectorAll('img').forEach(img=>
img.onclick=()=>img.closest('section').classList.toggle('zoom'));
document.querySelector('#export').onclick=()=>{const a=document.createElement('a');
a.href=URL.createObjectURL(new Blob([JSON.stringify({key,done})],{type:'application/json'}));
a.download='review-progress.json';a.click();URL.revokeObjectURL(a.href)};count();
</script>"""
    )
