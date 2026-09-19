# Durable edition review

```console
mathpub review before.pdf after.pdf --output reviews/revision-b --label "My book" --json
```

Open the resulting `index.html` offline. It retains both exact PDFs and presents
paired page images/contact sheets, physical page numbers and printed labels,
content/changes filters, click-to-zoom, keyboard navigation and local reviewed
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
