# Release sets and provenance

Every build now embeds a `/MathpubProvenance` JSON record directly through TeX's
PDF metadata primitive. It identifies the publication, projection, lesson scope,
Git revision, dirty/unknown state, and tracked/unignored source tree fingerprint.
The same source record is in the manifest. `build --require-clean` checks both
ends of the build and refuses a source change; ordinary builds record whether
their source stayed stable. Unknown Git state is null, never falsely clean.

Print export now requires a matching embedded stamp and a source-stable manifest.
Rebuild older editions before exporting. Incrementally preserved projections keep
their original stamp: a release rejects them if they no longer match the manifest.
Rebuild every required projection (without discarding caches) for a release.

Declare a release in TOML, with paths relative to that file:

```toml
schema = 1
id = "autumn-release"
[[books]]
id = "my-book"
required_roles = ["interior", "cover"]
[[books.artifacts]]
role = "interior"
manifest = "build/interior/A/manifest.json"
projection = "student"
receipt = "print/interior/receipt.json" # optional: select verified export bytes
[[books.artifacts]]
role = "cover"
manifest = "build/cover/A/manifest.json"
projection = "student"
receipt = "print/cover/receipt.json"
```

`mathpub release check release.toml --json` checks completeness, hashes, page
counts, stamps, and same-source cover/interior pairs. Roles are `interior`, `cover`,
`proof`, and `supplement`. Required roles are explicit, as are each projection and
optional print receipt. Proofs are never implicitly upload artifacts.

`mathpub release assemble release.toml --output releases/autumn --json` stages and
verifies a new, portable bundle. Existing bundles are never replaced. Partial
catalog updates select new artifacts for changed books and prior artifacts for
unchanged books; revisions are per book, not a fabricated catalog-wide commit.
`mathpub release verify releases/autumn --json` checks a historical bundle using
only its index and embedded artifact evidence, independent of today's source tree.
Interrupted bundles with missing/mismatched files are invalid. Hashes and stamps
are unsigned consistency evidence, not authentication or printer acceptance.
