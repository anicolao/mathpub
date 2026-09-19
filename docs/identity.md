# Canonical book identity

Set `identity = "../catalog/book.toml"` in a publication. Title, subtitle and
author then come from that record; redundant descriptor fields must agree.
Catalog discovery, builds, covers, PDF metadata and submission plans consume the
same identity. No source files are rewritten by the drift checker.

```toml
schema = 1
id = "my-book"
title = "The Formal Book Title"
subtitle = "A subtitle"
author = "An Author"
publisher = "An Imprint"
isbn = "9780306406157" # illustrative, not a claim of ownership
edition = "First edition"
year = 2026
collection = "My collection"
[display]
title = "The Formal\nBook Title"
spine_title = "Formal Book Title"
build_label = "review"
```

Display line breaks and short spine wording do not change formal PDF metadata.
Canonical fields are plain text and escaped for TeX. The renderer supplies
`\MathpubTitle`, `\MathpubSubtitle`, `\MathpubAuthor`, `\MathpubPublisher`,
`\MathpubISBN`, `\MathpubEdition`, `\MathpubYear`, `\MathpubCollection`, and
`\MathpubSpineTitle` for authored copyright/cover components. Publication styles
still own placement and typography; no branding or retailer copy is invented.

`mathpub identity catalog/book.toml --pdf interior.pdf --pdf cover.pdf --json`
checks ISBN-13 and compares embedded identity plus formal PDF title/author. It
returns field-level differences and artifact hashes on drift. With no PDFs it
validates the record only. ISBN validity is not ownership or retailer approval.
