# KDP existing-draft submission

MathPub supports an optional, explicit **existing paperback draft** workflow. It
does not create titles, request ISBNs, change listing metadata/disclosures, approve
Previewer, order proofs, set prices, or publish. Those are separate future actions,
not implied by upload. Ordinary builds never open a retailer session.

## Prepare

The two upload files are the complete **interior PDF** and a separate **full-wrap
cover PDF** (back cover + spine + front cover on one wide page). An interior title
page, a front-only cover image, or a geometry proof is not the cover upload.
Follow the [print pipeline](publishing-tools.md#print-pipeline); retain manifests,
release metadata and receipts connecting the cover to the exact interior.

Build source-stable clean editions with canonical identity, an ISBN, and a linked
cover specification. Export both print artifacts, then assemble a verified release
with `interior` and `cover` roles and the export receipts. Set explicit printing
fields in the cover profile: `format`, `ink`, `paper`, `bleed`, and `finish`.
Examples in the cover documentation are not retailer requirements.

Create a KDP configuration:

```toml
schema = 1
locale = "en-US"
url = "https://kdp.amazon.com/en_US/title-setup/paperback/YOUR_TITLE_ID/content"
profile_dir = "browser-profile" # relative to this config; use a dedicated profile
account_selector = "YOUR_UNIQUE_ACCOUNT_CONTROL_SELECTOR"
account_text = "EXACT VISIBLE ACCOUNT TEXT"
timeout_seconds = 600
# browser_executable = "/explicit/path/to/compatible/chromium"
```

Account controls vary across KDP accounts/UI revisions. Select a unique visible
account marker and its exact text, not a book title or a generic navigation label.
This account guard is mandatory; the adapter also verifies the exact draft URL,
formal title, ISBN, ink/paper, trim, bleed, cover-upload mode, and finish. Unfamiliar
controls or non-English interfaces fail closed. This adapter is versioned
`kdp-paperback-en-v1`; it does not pretend KDP's DOM is a stable public API.

`mathpub kdp login kdp/book.toml` opens the configured persistent browser for manual
login/MFA. Close that window after signing in; do not run two processes on the
same browser profile. Session expiry is resumable, not something MathPub bypasses.
Nix supplies Playwright and its packaged browsers; an explicit compatible Chromium
executable can be configured where the platform package lacks Chromium. Outside
Nix install the `kdp` extra and compatible Playwright browser separately.

```console
mathpub kdp plan releases/autumn --book my-book --config kdp/book.toml --output kdp/plan.json --json
mathpub kdp upload kdp/plan.json --output kdp/attempt-one --json
```

Review the plan's destination, source revision, identities, settings and full
artifact hashes before invoking upload. Both files are rechecked against the
release. Native local-file transfer stages a browser `File`, computes its SHA-256
**before** dispatching the retailer input/change events, and avoids large base64
payloads or logging PDF bytes. Filenames contain the full artifact hash.

## Receipts and recovery

The attempt directory contains staged files, screenshots of the validated draft,
and an atomically updated private `receipt.json`. File states distinguish planned,
submitting, submitted, acknowledged, and draft-persisted. The final gate is both
exact filenames after a fresh page load, even if autosave disabled Save as Draft.
This is not a server-side checksum or completed print processing; receipts never
claim Previewer approval or publication.

`mathpub kdp upload kdp/plan.json --output kdp/attempt-one --resume --json` reinspects
the draft before continuing and skips files already verified and observed there.
If an earlier submission is ambiguous, inspect KDP first; only an additional
`--retry-uncertain` authorizes replacement uploads. No duplicate draft is created.
Browser failures become `needs-review`; receipts redact raw browser exceptions
that could contain session information. Keep the profile and screenshots private.

The workspace's **Publishing tools** dialog exposes paired edition review, manual
login, plan preparation/loading and confirmed upload/resume. GUI mutations require
same-origin requests on the loopback workspace and library-relative file paths.

## Validation boundary

Routine tests use synthetic releases, fake adapters and intercepted browser pages,
including a 16 MiB browser transfer. No live account or draft is touched by tests.
Before adopting a changed KDP DOM adapter, run a supervised smoke check against a
designated test draft. No live upload was performed for this implementation.
Draft creation, assigned-ISBN acquisition, listing export/reconciliation and
metadata updates remain the follow-on operations identified by the survey.
