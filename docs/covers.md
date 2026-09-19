# Paperback cover geometry

Printer policy is explicit and dated, never a built-in stock multiplier:

```toml
schema = 1
id = "my-stock-v1"
profile_date = "2026-09-19"
interior_manifest = "build/book/A/manifest.json"
projection = "student"
trim_width_pt = 432
trim_height_pt = 648
spine_per_page_pt = 0.16 # illustrative, NOT a retailer specification
bleed_pt = 9
safe_pt = 18
round_pages_to = 2
min_pages = 1
max_pages = 800
barcode_box_pt = [30, 30, 174, 102] # bottom-left PDF coordinates on the back panel
[printing]
format = "paperback"
ink = "BW"
paper = "WHITE"
bleed = false
finish = "MATTE"
```

`mathpub cover prepare cover.toml --output cover-preparation --json` verifies the
interior hash/count/trim on every page, rounds the manufacturing page count, and
computes wrap size, spine, folds, panel text-safe areas and reserved barcode area.
It creates a geometry report, TeX preamble, and a clearly marked dimension-proof
PDF, never upload artwork. An existing preparation is not overwritten.

Add `cover_spec = "../cover.toml"` to a normal component-backed publication. Its
normal style/render/source-map workflow is retained; the geometry preamble sets
the physical page dimensions and the manifest records the exact interior link.
Use a single-page cover assembly (for example the `anna` base without an automatic
title/contents page). Typography, art and placement remain authored components.
Canonical `identity` and its TeX macros can supply cover wording.

`mathpub cover check cover.toml --artwork cover.pdf --prepared cover-preparation/geometry.json --json`
checks one-page wrap dimensions, stale preparation, text-safe panels and reserved
barcode overlap. Omit `--prepared` when no saved preparation needs comparing.
All dimensions are PDF points. Text checks do not certify artwork bleed, barcode
readability, or printer acceptance. Validate printer rules independently before
putting them in the profile; this example is deliberately not a KDP specification.
