# Sudoku library tools: candidates for MathPub

Survey date: 2026-09-19.

## Scope and recommendation

This is a read-only source survey of `../sudoku-challenges`, compared with the
current MathPub checkout. It recommends capabilities to extract, not wholesale
copies of the library's scripts or private publication content.

The strongest additions are **PDF preflight, verified print export, release-set
validation, cover geometry, and persistent before/after review**. These solve
publishing problems independent of Sudoku. Catalog identity and rendered QR
verification are also good candidates. **KDP draft uploading should be a supported
MathPub integration**, using verified releases and canonical book identity.
Diagram inspection and curriculum reports
have reusable infrastructure, but their domain rules should stay in libraries.

MathPub was inspected at `73597685dfaae5cf17810c2004991cf87c0d592c`.
The Sudoku library's HEAD was `01feefb365c5e2bab11a4e0f1a21213c61040c4e`;
its working tree was dirty, so findings include the files present at inspection,
not just that commit. The library's pinned `capabilities` command was read with
lock-file writes disabled. No library generators, audits, builds, browser sessions,
or release commands were run. Claims below describe inspected implementation,
not newly verified test results or current printer requirements.

Links into `../sudoku-challenges` are local evidence references; readers without
that sibling checkout will need access to the library to follow them.

## Existing MathPub foundation

- [publish.py](src/mathpub/publish.py) already records source revision/status,
  source and toolchain hashes, instance hashes, output hashes, and page counts;
  it also supports manifest-based reproduction. Its `_inspect_pdf` check is
  comparatively narrow: nonempty output, title presence, page count, and hash.
- [render.py](src/mathpub/render.py) already rejects TeX overflows and certain
  font substitutions. Rendered-PDF checks should complement these diagnostics.
- [watch.py](src/mathpub/gui/watch.py) fingerprints rendered pages and produces
  changed-page images. [app.js](src/mathpub/gui/static/app.js) already offers
  keyboard navigation, direct page jumps, and recent changed-page shortcuts.
- Custom styles, mapped components, projections, and incremental builds already
  provide the authoring foundation. New tools should use these rather than create
  a second publishing pipeline.

## Candidates to add

### 1. Configurable rendered-PDF preflight — first priority

**Evidence:** [advent/preflight.py](../sudoku-challenges/tools/advent/preflight.py),
[start_here/pdf_audit.py](../sudoku-challenges/tools/start_here/pdf_audit.py),
[check_cover.py](../sudoku-challenges/tools/check_cover.py), and
[check_review_layout.py](../sudoku-challenges/tests/check_review_layout.py).

The library measures actual PDF page geometry, text bounds, embedded fonts,
transformed font sizes, and stroked line widths. It also checks blank pages,
folios, grayscale output, and content grouping. The Advent measurement code
walks nested PDF Form XObjects for strokes, making it a particularly useful
starting point beyond checks of TeX source sizes.

**Proposed MathPub addition:** a shared PDF inspection API and opt-in publication
preflight profiles. Reports should identify the PDF hash, physical page, measured
value, expected range, and rule. Separate reusable measurements from requirements
such as trim, text-safe regions, permitted blanks, minimum type size, and minimum
line weight. Libraries should be able to supply semantic layout expectations.

**Boundary:** fixed page counts, chapter phrases, 6×9/8×10 assumptions, and the
current 7-point/0.75-point thresholds are book/profile policy. Text bounding boxes
do not prove all artwork stays inside safe regions; raster grayscale checks do
not establish PDF color-space compliance. Font/stroke transforms need broader
fixtures before extraction, including rotation and nonuniform scaling. Avoid
advertising these checks as PDF/X certification or printer acceptance.

### 2. Verified print export with a receipt — first priority

**Evidence:** [export_print.py](../sudoku-challenges/tools/export_print.py).

The exporter derives a separate print PDF from a complete, clean-source edition.
It checks the source manifest hash and embedded provenance, excludes annotations
and page actions, rejects forms, and verifies page counts, MediaBox/CropBox,
metadata, decoded drawing instructions, and encoded font/image/form resource
streams. Its receipt records source/output hashes, byte sizes, revision, exporter
hash, and pypdf version.

**Proposed MathPub addition:** an explicit export operation with named output
policies and a machine-readable derivation receipt. Keep the original review PDF
and its navigation intact. Validate staged output before publishing the export.
Resolve the chosen projection in the manifest explicitly rather than assuming
`outputs[0]` is the correct source.

**Boundary:** annotation removal is a policy choice, not a universal cleanup.
Reject or explicitly handle annotations with visible appearances. Preserve or
deliberately account for page labels, tagging, additional page boxes, rotation,
and other document-level structures: copying drawing streams alone does not prove
that all document semantics survive. Replace private pypdf `_data` access and
bare assertions with supported APIs and structured errors where possible.

### 3. Release sets and artifact-bound provenance — first priority

**Evidence:** [check_proof_set.py](../sudoku-challenges/tools/check_proof_set.py),
[advent/release.py](../sudoku-challenges/tools/advent/release.py),
[build_catalog_release.py](../sudoku-challenges/tools/build_catalog_release.py),
[export_catalog_print.py](../sudoku-challenges/tools/export_catalog_print.py),
[kdp/preflight.py](../sudoku-challenges/tools/kdp/preflight.py), and the library's
[flake.nix](../sudoku-challenges/flake.nix) source-stamping wrapper.

These tools distinguish full books from scoped previews, match cover/interior
revisions, check PDF bytes against manifests, separate dimension proofs from
upload files, and stage catalog exports while retaining the previous print tree.
Single-book updates retain other books' exports and record per-book revisions
instead of asserting that the whole catalog came from one commit. KDP preflight
can verify an existing clean export even when today's source tree is dirty.

**Proposed MathPub addition:** declarative release sets with artifact roles,
required projections, completeness checks, and per-book provenance. Extend the
existing manifest rather than introduce competing source records. Supply build
provenance directly to TeX/PDF metadata so libraries need not wrap every app with
environment variables. Record an unknown source state explicitly; capture and
check the source state around release builds.

**Boundary:** distinguish “build a release from current clean source” from
“verify this previously exported release.” The latter should not require current
HEAD to equal the artifact's revision. Matching metadata and hashes establish
consistency, not signed authenticity. Fixed catalog lists, seed 2026, particular
variants, and projection choices belong in release configuration.

### 4. Paperback cover geometry and interior linkage — high priority

**Evidence:** [cover_common.py](../sudoku-challenges/tools/cover_common.py),
[prepare_cover.py](../sudoku-challenges/tools/prepare_cover.py),
[check_cover.py](../sudoku-challenges/tools/check_cover.py), and
[covers/README.md](../sudoku-challenges/covers/README.md).

The library derives wrap dimensions from the actual interior's physical page
count, checks trim on every page, calculates spine/bleed/folds, generates a guided
proof, and checks text-safe and barcode areas. Preparation records interior
provenance and detects stale generated cover source. Its current implementation
uses supported textbook styles because MathPub has no native cover kind.

**Proposed MathPub addition:** a reusable cover specification and dimension engine,
with interior artifact references, printer-profile inputs, geometry reports, and
separate artwork/proof outputs. Preserve source mapping and normal MathPub builds.
A dedicated cover publication kind is worth considering, but not necessary for
the first extraction of geometry and validation.

**Boundary:** stock multipliers, page limits, bleed, and barcode rules need dated,
maintainable printer profiles; their present values were not independently
verified for this survey. The series artwork, palettes, panel typography, and
embedded Sudoku puzzle stay local. Text/geometry fingerprints can avoid needless
regeneration after PDF ID changes, but cannot detect every artwork change; retain
exact artifact hashes and relevant component/style dependencies too.

### 5. Persistent before/after edition review — high priority

**Evidence:** [teaching_review/review.py](../sudoku-challenges/tools/teaching_review/review.py),
[answer_review.py](../sudoku-challenges/tools/answer_review.py),
[colour_review.py](../sudoku-challenges/tools/colour_review.py),
[minor_rule_review.py](../sudoku-challenges/tools/minor_rule_review.py), and
[catalog_review.py](../sudoku-challenges/tools/catalog_review.py).

The reviewers retain before/after editions, render page pairs and contact sheets,
filter by book or affected content, show physical page numbers and printed labels,
offer zoom, and persist local reviewed checkmarks. Body-image hashes suppress
header/folio-only differences. When pagination changes, text shingles provide
approximate nearby-page matching. The answer reviewer caches renders by PDF hash.

**Proposed MathPub addition:** extend the existing page-review machinery with a
saved baseline, paired comparison, contact sheets, review scope, and progress
bound to artifact hashes. An exportable HTML review would also be useful outside
the live workspace. The new value is durable comparison across editions, not
another implementation of arrow keys or recent-page navigation.

**Boundary:** replace fixed pixel crops, commit IDs, book lists, monkey-patching,
and HTML string substitutions with configuration and shared templates. Treat
alignment as heuristic; expose unmatched insertions and deletions. The current
review loop visits revised pages and is not a complete deleted-page detector.
Header exclusions must be explicit because metadata and folios can matter.
Review checkmarks are progress records, not editorial approval.

### 6. Canonical publication and catalog identity — high priority

**Evidence:** [catalog_identity.py](../sudoku-challenges/tools/catalog_identity.py),
[catalog/README.md](../sudoku-challenges/catalog/README.md), and
[catalog_review.py](../sudoku-challenges/tools/catalog_review.py).

A canonical identity record feeds publication descriptors, title/copyright pages,
cover wording, PDF metadata, and local submission configurations. It validates
ISBN-13 checksums and offers a non-mutating drift check. Formal titles are kept
distinct from display line breaks, short spine titles, and build labels.

**Proposed MathPub addition:** shared bibliographic metadata and catalog references,
with display overrides and consistency checks across editions and cover/interior
pairs. This also addresses the library's workaround for MathPub's literal title
presence check when composed display titles differ from the formal PDF title.

**Boundary:** integrate at schema/render boundaries rather than rewriting TOML and
TeX with regular expressions. ISBN checksum validity does not establish ownership.
Publisher branding, listing copy, retailer field limits, and series membership
choices remain library data or adapter policy.

### 7. Rendered QR and PDF navigation verification — useful shared service

**Evidence:** [check_release_proof.py](../sudoku-challenges/tests/check_release_proof.py),
[start_here/pdf_audit.py](../sudoku-challenges/tools/start_here/pdf_audit.py),
[check_pdf_navigation.py](../sudoku-challenges/tests/check_pdf_navigation.py), and
[sudoku_qr.py](../sudoku-challenges/tools/sudoku_qr.py).

The library decodes QR codes from 300-dpi page renders and checks payloads against
expected data. Dense indexes use caption-located crops to verify individual codes.
Bookmark checks resolve destinations and compare destination-page text. A separate
helper emits compact vector QR paths for LuaTeX.

**Proposed MathPub addition:** expected link/QR records keyed by placement, generic
QR rendering, and optional PDF audits of payloads, counts, and destinations.
Report missing, unexpected, and duplicate occurrences, not merely set membership.
Use mapped placement geometry where available instead of parsing book captions.

**Boundary:** Sudoku URL serialization, replay protocols, website domains, and
chapter-specific bookmark inventories stay local. Raster decoding establishes
readability under the tested rendering conditions, not phone-camera success.
Text matching at a destination is a useful heuristic, not proof of the exact
anchor. Bookmark expectations apply to navigable editions, not stripped exports.

### 8. Layout-change invariants and actual-size specimens — selective extraction

**Evidence:** [teaching_review/validate.py](../sudoku-challenges/tools/teaching_review/validate.py),
[answer_review_validate.py](../sudoku-challenges/tools/answer_review_validate.py),
[grid_sampler/inventory.py](../sudoku-challenges/tools/grid_sampler/inventory.py),
and [grid_sampler/render.py](../sudoku-challenges/tools/grid_sampler/render.py).

The tools verify that layout trials preserve diagram contents, marks, occurrence
counts, and link destinations while changing only intended size distributions.
An actual-size specimen book uses the production renderer, and a PDF inventory
cross-checks detected diagrams against generated source occurrences.

**Proposed MathPub addition:** a report interface for library-supplied invariants,
plus a style/component specimen generator using normal projections and rendering.
Compare canonical instance and placement data where possible. Include source
references and physical measurements in reports for review.

**Boundary:** ten-by-ten rule detection is a Sudoku-grid recognizer, not a generic
diagram detector. TeX macro parsers, board-state legality, approved grid sizes,
and domain-specific equivalence remain library code. Multiset equality alone
does not prove that each question still has the correct adjacent answer; generic
checks should retain placement identity.

### 9. KDP draft upload and submission verification — supported integration

**Evidence:** [upload-extension.mjs](../sudoku-challenges/tools/kdp/upload-extension.mjs),
[preflight.py](../sudoku-challenges/tools/kdp/preflight.py),
[guards.mjs](../sudoku-challenges/tools/kdp/guards.mjs),
[file-bytes.mjs](../sudoku-challenges/tools/kdp/file-bytes.mjs),
[extension-client.mjs](../sudoku-challenges/tools/kdp/extension-client.mjs),
[create-draft.mjs](../sudoku-challenges/tools/kdp/create-draft.mjs), and
[KDP workflow documentation](../sudoku-challenges/tools/kdp/README.md).

Uploading a finished book is a common publishing need and a reasonable part of
MathPub's supported workflow. The library already has substantial implementation
to draw from: it validates a selected release, connects to an authenticated browser
profile, checks the exact book title/URL/ISBN and printing settings, stages the
interior and cover, and checks hashes before transfer and inside the browser.
It submits through the page's file inputs, waits for acknowledgments naming each
file, saves the draft when the control is enabled, and reloads the page to verify
both filenames persist. Receipts and screenshots record the reached stage.

The library README reports a successful live draft-upload test on 19 September
2026. This survey did not repeat it. The observed success criterion is persisted
filenames plus browser-verified input bytes; it is not a server-side checksum,
completed print processing, Previewer approval, or publication.

**Proposed MathPub addition:** a maintained, optional KDP integration exposed
through the CLI and GUI. Its first supported operation should upload a verified
interior/cover pair to an existing paperback draft and return a durable receipt.
Give the author a concrete submission plan containing the target book, release
revision, file hashes, and expected manufacturing settings. Explicit upload
invocation should carry that plan through to verified draft persistence, with
status and recovery guidance if the operation stops midway. Ordinary preview
builds should remain independent of retailer sessions.

Use a generic release/submission model for artifact identity, attempt status, and
receipts, with KDP-specific browser behavior behind an adapter. This is a packaging
boundary within a supported MathPub feature, not a reason to leave authors to
maintain their own upload scripts. Draft creation, metadata updates, saved-listing
export, and reconciliation are sensible follow-on operations. Preview approval,
proof ordering, and publication need distinct explicit actions and outcomes.

**Challenges in making it generic:**

| Area | Current assumption or limitation | Generalization needed |
| --- | --- | --- |
| Book and account identity | Six allowed book slugs, exact content URLs, and a default `Profile 6`. | Resolve any configured publication/release to a persisted KDP title ID, format, and account/session binding. Verify the destination before mutations; title text alone is not unique. |
| Print configuration | The uploader branches on `learners-guide` for ink; preflight selects one of two trims and assumes paperback, white stock, and no bleed. | Derive expected settings from the release's printer profile. Declare supported combinations and reject unsupported ones. Hardcover and ebooks require separate workflows rather than inheriting paperback assumptions. |
| Browser setup and authentication | The extension bridge hard-codes a macOS Chrome executable and uses a local extension token. | Make browser/profile selection explicit and platform-aware, package compatible dependencies, protect credentials, and support reconnecting to the intended session. Login, MFA, and session expiry need a user-resumable flow. |
| UI and endpoint changes | English text, DOM selectors, upload alerts, and parsed MCP result headings drive the uploader; listing export also uses an internal KDP endpoint. | Isolate and version the adapter, declare supported locale/browser combinations, detect unfamiliar pages, and maintain fixtures plus supervised live smoke checks. Do not treat the observed endpoint as a stable public API. |
| PDF transfer | The extension path sends each whole PDF as base64, reconstructs a browser `File`, and checks its SHA-256. | Retain byte verification while testing realistic large books, message limits, memory use, and timeouts. Evaluate chunked transfer or a supported direct upload path where available; avoid putting file payloads or session secrets in logs. |
| Partial success and retries | Receipts record progress, but a failure can follow one successful upload or an uncertain save; fixed polling windows can expire during processing. | Use a persisted attempt state machine. Reinspect remote filenames/status before resuming, distinguish failed from unknown outcomes, and prevent duplicate drafts or unnecessary replacement uploads. Keep submitted, acknowledged, draft-persisted, and processing-complete states separate. |
| ISBN and metadata lifecycle | Draft creation records the URL before requesting a free ISBN; catalog scripts then synchronize printed identity. | Support existing/author-owned ISBNs and explicitly chosen assignment paths. Persist acquired identifiers immediately, then require a matching rebuilt release if printed identity changes. Avoid silently choosing imprint, pricing, categories, or disclosure answers. |
| Reconciliation and evidence | Local configurations, observed listings, and upload receipts are separate; filename hash prefixes connect remote observations to local releases. | Preserve desired versus observed state, timestamps, full hashes, and field-level differences. State exactly what remote observations establish; filename persistence cannot prove server-side PDF byte identity. |

**Validation before adoption:** retain the existing transport/guard unit tests and
add synthetic browser fixtures for wrong-book selection, settings mismatch,
expired sessions, disabled Save after autosave, one-file success, delayed processing,
and lost connections around submission. Test large-file transfer and resume
behavior. Live draft-upload checks should use designated test drafts and remain
separate from routine build tests. None of those live actions were performed for
this survey.

## Exclusions and integration boundaries

| Tool family | Why excluded; reusable boundary if any |
| --- | --- |
| `start_here/{logic,search,select,difficulty,symmetric_solution,verify}.py`; `candidates_done/{search,select,targeted,difficulty}.py` | Sudoku deduction, clue selection, candidate notation, and teaching progression. Keep in a Sudoku package/library; consume its validation results through a generic report interface. |
| `practice_xwing/{core,pool,select,validate,report}.py`; `mastery/{logic,pool,select,diversity,equivalence,validate,report}.py` | Technique requirements, search-budget evidence, equivalence under Sudoku symmetries, and difficulty estimates are domain models. Coverage/diversity summaries are interesting future report inputs, but do not yet justify a universal MathPub difficulty engine. |
| `advent/{sudoku,difficulty,curation,generate,drawing,assembly,numbering,labels,art,reduce_art,repair_seams,example}.py`; `make_advent.py` | A specific calendar, puzzle, tile-assembly, drawing, and art-production workflow. Extract the independently useful PDF measurements, not the annual generator or artwork logic. |
| `advent/preview.py`, `preview_core.js`, `preview.html` | Interactive Sudoku/drawing review tied to the Advent dataset. Offline review is reusable in principle, but this renderer is not a general MathPub viewer. |
| Book-family `render.py`, `print.py`, `cover.py`, `links.py`; Sudoku-specific portions of `check_guide_print.py` and `tests/check_*.py` | Fixed assemblies, prose markers, answer arrangements, brands, page numbers, and solver checks. Extract shared inspection/export primitives; keep publication policy and content local. |
| KDP upload, draft creation, and browser transport tools | Included as the supported integration proposed in §9. Exclude their fixed profile, browser path, book names, and manufacturing defaults from the reusable implementation. The retained CDP prototype is not an additional required transport. |
| `kdp/{export-listings,verify-listings,render-summary}.mjs`, `reconcile-listings.py`, listing-update and disclosure scripts | Candidates for follow-on KDP support. Extract observed-state export and reconciliation; exclude this catalog's fixed copy, baseline commits, series choices, and disclosure answers. Keep retailer fields in the adapter. |
| `kdp/books/`, `kdp/listings/`, catalog identities and listing revisions, cover copy/assets, preserved review editions | Private configuration, observations, creative content, or generated artifacts—not engine tools to copy. Use synthetic fixtures for any extraction. |

## Suggested implementation order and extraction conditions

1. Build shared PDF inspection and artifact-validation APIs on the existing
   manifest. Extract print export and release-set checks first: these remove the
   broadest duplicated plumbing and make later outputs easier to verify.
2. Add cover specifications and canonical identity, with explicit artifact roles
   and configurable printer profiles.
3. Add KDP upload to existing drafts using verified release pairs and canonical
   identity. Establish durable receipts and recovery before adding draft creation
   and listing management.
4. Extend GUI/offline edition comparison using existing rendered-page services;
   add QR/navigation audits as optional report producers.
5. Introduce invariant/specimen extension points only around demonstrated library
   needs. Keep Sudoku mathematics local and retailer-specific behavior in the
   supported integration adapter.

Across these additions, replace hard-coded roots and book inventories with
declarative inputs, bare assertions with stable diagnostics, import-time writes
with explicit operations, and generated-report mutation with immutable inputs.
Keep external tools in Nix and invoke expensive raster/QR checks intentionally.
Reports should record artifact hashes, tool/profile versions, checked scope,
skipped checks, and unresolved limitations. Test extracted primitives with
synthetic publications covering multiple trims, projections, pagination changes,
and incomplete/stale artifacts; do not import the private books as fixtures.

This survey changes no implementation and makes no claim that the existing
library scripts are ready to move unchanged.
