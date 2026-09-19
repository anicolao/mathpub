# Publishing tools

The generic additions proposed in `SUDOKU_TOOLS_SURVEY.md` are implemented as
opt-in commands. Existing authoring builds remain mapped production builds.

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
