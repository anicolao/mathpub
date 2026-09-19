# QR and PDF navigation

`mathpub qr 'https://example.invalid/resource' --output resource.tex --size-pt 72`
creates an actual-size TikZ QR asset for normal component rendering. `.pdf` and
`.svg` outputs are also supported. The renderer includes four quiet-zone modules,
uses medium error correction, and never overwrites an existing asset.

`mathpub audit-navigation book.pdf --expectations navigation.toml --json` audits
the final rendered PDF. For example:

```toml
schema = 1
dpi = 300
[[qr]]
id = "lesson-one.resource"
page = 3
payload = "https://example.invalid/resource"
count = 1
box_pt = [30, 30, 120, 120] # optional mapped placement box, top-left MediaBox coordinates
[[links]]
id = "lesson-one.link"
page = 3
uri = "https://example.invalid/resource"
[[bookmarks]]
id = "answers"
title = "Answers"
page = 20
text = "Answer Key" # optional destination-text heuristic
```

Each included family is an exact occurrence inventory: missing, unexpected and
duplicate values fail, including codes outside expected placement crops. Omitted
families are explicitly skipped; an empty array requires zero occurrences.
Placement IDs must be unique. Internal links use `destination_page` instead of
`uri`. Library source maps can supply `box_pt`; no caption or domain parser is
built in. Reports bind results to PDF and expectation hashes and record DPI.

Decoding at the selected resolution is not a phone-camera guarantee. Destination
text is a heuristic, not proof of the exact anchor. Run bookmark/link policies on
the navigable edition, not an intentionally stripped print export.
