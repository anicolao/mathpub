"""One workflow contract shared by startup prose and structured discovery."""

from importlib.resources import files
from pathlib import Path

from mathpub.errors import MathpubError

# topic, when, prerequisites/boundaries, CLI examples, version-matched manual
WORKFLOWS = (
    (
        "preflight",
        "Check an existing PDF before print handoff or after typography/layout changes.",
        "Use the library's explicit TOML policy; do not invent printer thresholds. "
        "Without a profile this is inspection, not acceptance. Checks are not PDF/X certification.",
        ("preflight BOOK.pdf --profile print-policy.toml --json",),
        "pdf-preflight.md",
    ),
    (
        "export-print",
        "Derive print delivery bytes while retaining the original review PDF and navigation.",
        "Requires a complete, clean, source-stable edition with matching embedded provenance. "
        "Select the projection explicitly; preserve the receipt. Legacy editions need rebuilding.",
        (
            "export-print build/book/A/manifest.json --projection student "
            "--policy remove-invisible-links-v1 --output print/interior --json",
        ),
        "print-export.md",
    ),
    (
        "release",
        "Prepare a book/catalog handoff or verify a previously assembled release.",
        "Declare required roles, manifest projections and optional export receipts "
        "in release TOML. "
        "Build every required projection with --require-clean; keep incremental caches. "
        "Historical verify uses retained evidence, not today's source tree. Stamps are unsigned.",
        (
            "release check release.toml --json",
            "release assemble release.toml --output releases/edition-one --json",
            "release verify releases/edition-one --json",
        ),
        "releases.md",
    ),
    (
        "cover",
        "Prepare a paperback cover or recheck it after the interior page count changes.",
        "Use an explicit dated printer profile and the exact clean interior manifest. "
        "The generated dimension proof is NOT upload artwork. Author artwork through a normal "
        "component-backed publication with cover_spec, then check it. "
        "Verify printer rules separately.",
        (
            "cover prepare cover.toml --output cover-preparation --json",
            "cover check cover.toml --artwork cover.pdf "
            "--prepared cover-preparation/geometry.json --json",
        ),
        "covers.md",
    ),
    (
        "review",
        "Review revisions against a saved PDF baseline across sessions or at edition handoff.",
        "Retain the baseline before changing it. Open the generated index.html and inspect "
        "changed, "
        "inserted and deleted pages; alignment is heuristic. Progress marks are not approval. "
        "Use explicit --page, --crop and --cache only when appropriate; "
        "excluded margins are recorded. Use review-set for multiple publications. "
        "Use --notes, --baseline-revision and --attach for author-supplied context/evidence; "
        "these are not verified PDF provenance. The viewer retains percentage zoom and offers "
        "direct page selection, filtered progress counts and links to frozen full PDFs.",
        (
            "review baseline.pdf revised.pdf --output reviews/revision-one --json",
            "review-set review.toml --output reviews/catalog --json",
        ),
        "edition-review.md",
    ),
    (
        "identity",
        "Share title/author/ISBN across interiors, covers and metadata, or diagnose wording drift.",
        "Reference a canonical identity TOML from publications using identity. Display overrides "
        "are separate from formal metadata. ISBN-13 is validated; "
        "drift inspection does not edit PDFs.",
        ("identity identity.toml --pdf interior.pdf --pdf cover.pdf --json",),
        "identity.md",
    ),
    (
        "navigation",
        "Add QR codes or validate rendered QR placements, PDF links and bookmarks.",
        "Place vector QR assets in normal authored components. Supply an occurrence inventory TOML "
        "to audit missing/unexpected/duplicate codes and destinations; "
        "omitted families are skipped. "
        "Rendered decoding does not guarantee phone-camera readability.",
        (
            "qr https://example.org/resources --output assets/resources.tex --size-pt 72 --json",
            "audit-navigation book.pdf --expectations navigation.toml --json",
        ),
        "navigation-audit.md",
    ),
    (
        "layout",
        "Check that layout edits preserve mathematics, or inspect actual-size component specimens.",
        "Compare retained manifests by placement, not answer multisets. Library-specific evidence "
        "must be bound to both manifests; domain rules remain in the library. Specimens use the "
        "production renderer and SyncTeX, not scaled screenshots. Preserve the explicit seed.",
        (
            "invariants before/manifest.json after/manifest.json --json",
            "specimen my-specimens --component COMPONENT_ID --output publications/specimens.toml "
            "--style mathpub --projection student --seed 2026 --json",
        ),
        "layout-tools.md",
    ),
    (
        "kdp",
        "The author explicitly requests uploading a verified pair "
        "to an existing KDP paperback draft.",
        "Requires verified interior/cover print receipts, matching canonical identity with ISBN, "
        "linked cover geometry and explicit print settings. Read the manual before configuring the "
        "mandatory exact account guard and draft URL. Login/MFA is manual. "
        "Review the plan and obtain "
        "explicit upload authorization before upload; ordinary builds/reviews never imply it. "
        "No title creation, metadata changes, Previewer approval, proof orders, "
        "pricing or publishing. Draft-persisted filenames do not mean "
        "completed retailer processing. "
        "On interruption inspect "
        "the receipt and draft before --resume; --retry-uncertain requires explicit authorization.",
        (
            "kdp plan releases/edition-one --book BOOK_ID "
            "--config kdp.toml --output plan.json --json",
            "kdp login kdp.toml",
            "kdp upload plan.json --output submissions/attempt-one --json",
            "kdp upload plan.json --output submissions/attempt-one --resume --json",
        ),
        "kdp.md",
    ),
)

POLICY = (
    "Discover these workflows at startup, then use them when the task calls for them; do not run "
    "builds, audits or retailer sessions merely to orient yourself. "
    "Prefer these supported commands over ad-hoc PDF scripts. "
    "Existing output directories are not overwritten. Use authored library "
    "configuration, not invented printer/account policy. "
    "Paths and uppercase identifiers in examples "
    "are placeholders. Run through the library's pinned Nix environment. Read the matching topic "
    "manual for TOML examples and detailed limitations before first use. The GUI Publishing tools "
    "dialog also exposes edition review and confirmed KDP submission. "
    "Keep sessions and receipts private."
)


def publishing_data() -> dict:
    return {
        "policy": POLICY,
        "workflows": [
            {
                "topic": topic,
                "when": when,
                "requirements_and_boundaries": requirements,
                "examples": [f"nix run .#mathpub -- {command}" for command in commands],
                "manual_command": f"nix run .#mathpub -- capabilities --topic {topic}",
            }
            for topic, when, requirements, commands, _ in WORKFLOWS
        ],
    }


def publishing_guide() -> str:
    sections = ["## Publishing and delivery tools", POLICY]
    for workflow in publishing_data()["workflows"]:
        sections.extend(
            [
                f"### {workflow['topic']}",
                f"Use when: {workflow['when']}\n\n{workflow['requirements_and_boundaries']}",
                "```console\n" + "\n".join(workflow["examples"]) + "\n```",
                f"Full manual: `{workflow['manual_command']}`.",
            ]
        )
    return "\n\n".join(sections)


def publishing_manual(topic: str) -> str:
    names = {row[0]: row[4] for row in WORKFLOWS}
    if topic not in names:
        raise MathpubError("MP-CLI-003", "unknown publishing capability topic")
    resource = files("mathpub").joinpath("publishing_docs", names[topic])
    if resource.is_file():
        return resource.read_text(encoding="utf-8")
    # Source-checkout development; installed distributions carry the same docs as resources.
    source = Path(__file__).resolve().parents[2] / "docs" / names[topic]
    if source.is_file():
        return source.read_text(encoding="utf-8")
    raise MathpubError("MP-CLI-003", "publishing manual missing from this MathPub installation")
