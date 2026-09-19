# Verified print export

Derive a separate print PDF from a selected manifest projection:

```console
nix run .#mathpub -- export-print build/my-book/A/manifest.json \
  --projection student --output print/my-book-A \
  --policy remove-invisible-links-v1 --json
```

The output's parent directory must exist; the output directory itself must **not**
exist. The command never overwrites a previous export. It works independently of
the current project or Git checkout: a previously built clean edition can be
exported while today's authoring tree is dirty or has moved to another revision.

The manifest must record a known clean source revision, an unscoped publication
(`lesson_ids = []`, not a question preview), and exactly one matching projection.
The PDF's bytes and page count must match that manifest. The chosen projection is
explicit: the first output is not assumed to be the student or print edition.

## Policy and receipt

The initial, deliberately narrow `remove-invisible-links-v1` policy removes link
annotations only when they have no appearance stream, visible border, tagging, or
optional-content association. All other annotations are rejected. Page actions,
document open/additional actions, and the JavaScript name tree are also removed.
Forms, tagged PDFs, and signed/restricted documents require future distinct
policies and are rejected rather than silently losing their semantics.

The exporter clones the document, then verifies the staged output before exposing
the final PDF. It compares decoded drawing instructions and resource streams,
all five page boxes, rotation, UserUnit, metadata, and page labels. It preserves
the original PDF and its review links. It does not use private pypdf stream data.

An export contains `print.pdf` and `receipt.json`. The receipt is written last as
the completion marker; an interrupted export without it is incomplete. A hard
interruption may leave staging files or an incomplete destination: inspect it and
choose a new export directory rather than treating it as a release. Ordinary
validation failures leave no export behind.

The receipt records the input/manifest/output hashes, byte sizes, source record,
projection, policy, removed link count, tool versions, exporter source hash, and
verification scope. Errors use `MP-EXPORT-001` and exit code 3.

## Limits

These checks establish consistency with an **unsigned manifest**, not authenticity.
An embedded source stamp and source-stable build are now required; rebuild legacy
editions first. Use [release sets](releases.md) to check all required cover/proof
artifacts; exporting one full student projection does not establish that completeness.

Decoded resources, not compression bytes or rendered pixels, are compared. This
is not a security sanitizer: surviving document structures may contain actions.
Nor is export a PDF/X, printer-acceptance, or editorial certificate. Run the
appropriate [preflight policy](pdf-preflight.md) on the resulting print PDF too.
No retailer session is opened and no upload is attempted.
