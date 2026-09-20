# Publishing tools

The generic additions proposed in `SUDOKU_TOOLS_SURVEY.md` are implemented as
opt-in commands. Existing authoring builds remain mapped production builds.

The ultimate goal of this print workflow is **print-ready PDFs for KDP**: a complete
interior and a **separate full-wrap cover PDF**, linked by artifact metadata and
delivered with release evidence. Previews, title pages and dimension proofs are
intermediate or different artifacts, not the final cover deliverable. This goal
does not broaden the author's current request or authorize uploads or publication.

## Print pipeline

1. Author and review incrementally using mapped components. Establish canonical
   bibliographic identity and explicit printer settings; do not invent dimensions
   or paper/spine multipliers. Preserve review originals and inspect changes.
2. Finalize the interior, then build its complete intended projection from clean,
   stable source with `--require-clean`. Preflight the PDF. Use its actual manifest
   to prepare cover geometry rather than estimating the page count.
3. Author a separate full-wrap cover: **back cover + spine + front cover** on one
   wide page, with profile-defined bleed, safe regions and barcode reservation.
   Use `cover_spec` so its manifest records the exact interior link. Do not upload
   the dimension proof or substitute an interior title page.
4. Once final authored changes are committed, build the interior **first**, then
   prepare/check geometry and build the cover from the **same clean revision and
   source tree**. Keep incremental caches. Committing cover work can change the
   interior's embedded provenance, so refresh its hash link even if pagination is
   unchanged. Check the wrap and identity consistency. Keep generated artifacts
   out of authored source where appropriate so builds do not dirty their inputs.
5. Export the chosen interior and cover projections separately using `export-print`.
   Preserve each receipt and run suitable preflight checks on the exported PDFs.
   Assemble and verify a release declaring required `interior` and `cover` roles.
   Its metadata binds the cover to the exact source interior; receipts connect
   those source artifacts to the delivered print bytes. Matching filenames are
   not adequate evidence.
6. Hand off both print PDFs, release metadata and receipts. Only with explicit
   authorization, prepare a KDP submission plan, check the exact draft/account/
   settings, and upload to that existing paperback draft. A persisted upload is
   not completed retailer processing, Previewer approval or publication.

"Print-ready" describes preparation and validation against the chosen printer
requirements; MathPub does not guarantee KDP acceptance. Consult the matching
topic manuals through `mathpub capabilities --topic cover`, `export-print`,
`release`, and `kdp`. Both default capability formats include this pipeline.

## Tools

| Survey entry | Commands and documentation |
| --- | --- |
| 1. PDF preflight | [Preflight](pdf-preflight.md): geometry, fonts, strokes, rendered text, blank pages, color and content expectations |
| 2. Print export | [Print export](print-export.md): separate validated outputs and derivation receipts |
| 3. Release sets | [Releases](releases.md): source provenance, required roles, immutable bundles and historical verification |
| 4. Cover geometry | [Covers](covers.md): interior-derived dimensions, profiles, proofs and artwork checks |
| 5. Edition review | [Edition review](edition-review.md): retained PDFs, paired pages, contact sheets and hash-bound progress |
| 6. Bibliographic identity | [Identity](identity.md): canonical records, TeX fields and metadata drift checks |
| 7. QR and navigation | [Navigation audits](navigation-audit.md): vector QR assets, rendered decoding, links and bookmarks |
| 8. Layout assurance | [Layout tools](layout-tools.md): placement invariants, library evidence and production specimens |
| 9. KDP submission | [KDP](kdp.md): verified release plans and guarded uploads to an existing paperback draft |

The workspace's **Publishing tools** control exposes edition review and KDP
planning, manual login, explicit upload confirmation and receipt-based recovery.
CLI help describes the full command interfaces.

## Boundaries

These tools do not certify PDF/X compliance, printer acceptance, editorial approval
or successful KDP processing. KDP uploads require a manually authenticated session,
matching draft/account/print settings and explicit confirmation. They never publish
a book. Draft creation, ISBN requests and listing reconciliation remain the survey's
separate follow-on operations; no live retailer submission is part of the test suite.

Sudoku generation, puzzle-specific quality metrics, private catalog/account data and
book-specific design choices remain library concerns, as listed in the survey's
exclusions. Library-specific expectations can be supplied as declarative checks.
