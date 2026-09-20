# Durable edition review

```console
mathpub review before.pdf after.pdf --output reviews/revision-b --label "My book" --json
```

Open the resulting `index.html` offline. It retains both exact PDFs and presents
paired page images/contact sheets, physical page numbers and printed labels,
publication/content/changes filters, direct page selection, keyboard navigation and local reviewed
checkboxes. Progress is keyed to both artifact hashes, rendering settings and
scope; changing the edition or excluded margins cannot reuse old checkmarks.
Progress can be exported to JSON. These marks track work, not editorial approval.

Nearby text-shingle alignment is heuristic. Insertions **and deletions** remain
visible as unmatched pages. Pixel comparisons decide unchanged versus modified;
text similarity alone never establishes an unchanged page.

`--page N` (repeatable) scopes the review to physical pages in either edition.
`--crop LEFT TOP RIGHT BOTTOM` explicitly excludes margins, in PDF points, from
pixel comparison only; the viewer still shows the complete pages and displays
the exclusion. No headers or folios are silently ignored. `--dpi` defaults to 150;
`--cache DIRECTORY` reuses renders keyed by PDF hash/page/DPI. The default cache
lives inside the new review. Existing reviews are never overwritten. Browser
storage is local; exported progress is useful when moving between browsers.

The viewer links to the retained full PDFs for surrounding context. Percentage zoom
(10–200%) persists across navigation and reloads; inaccessible or invalid browser
storage falls back safely. Page choices show physical pages and printed labels,
including unmatched/deleted pages. Counts distinguish the filtered selection from
the complete review. The scrollable paired cards remain the contact-sheet view.

Use `--notes "What to check"`, `--baseline-revision REV`, and repeatable
`--attach PATH` to record review context and snapshot supporting evidence, such as
a source diff or validation report. Attachments are copied as non-executable binary
downloads and hashed. Context changes invalidate progress alongside PDF changes.
The revision and attachments are **author-supplied evidence**, not verified PDF
provenance. MathPub does not run Git or capture private/untracked files implicitly.

## Multiple publications

`mathpub review-set review.toml --output reviews/catalog --json` creates one
review with a publication selector and separate frozen PDF pairs:

```toml
schema = 1
label = "Catalog revision"
dpi = 150
[[books]]
label = "Workbook"
before = "baseline/workbook.pdf"
after = "revised/workbook.pdf"
baseline_revision = "AUTHOR_SUPPLIED_REVISION"
notes = "Inspect explanation reflow and unchanged answers."
attachments = ["source.patch"]
[[books]]
label = "Answer key"
before = "baseline/key.pdf"
after = "revised/key.pdf"
```

Paths are relative to the TOML file. Review-set comparisons include full pages;
use individual `review --crop` commands for explicitly cropped comparisons. The
GUI's Publishing tools dialog accepts a review-set TOML or a PDF pair with optional
context. Whole-book fuzzy fallback matching is not introduced by this interface
update: existing monotonic alignment and explicit insertions/deletions are retained.
