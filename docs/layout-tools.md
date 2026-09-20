# Layout invariants and actual-size specimens

`mathpub invariants before/manifest.json after/manifest.json --json` verifies
stored instance hashes and compares canonical parameters/derived values **by
placement**, not as a multiset. Swapping two questions' answers therefore fails.
Display values may change during layout work. Legacy worksheet placements use
their question index plus ID, so ordering changes are not silently accepted.

Libraries can add domain evidence using `--evidence report.json` (repeatable):

```json
{
  "schema": 1,
  "before_manifest_sha256": "<full hash>",
  "after_manifest_sha256": "<full hash>",
  "checks": [{"id": "diagram-size", "placement": "lesson.question-one",
              "passed": true, "note": "The measured diagram meets the library minimum.",
              "measured": 72, "expected": 60, "source": "components/question-one"}]
}
```

Evidence must match both manifests and known placements. This is a report
interface, not arbitrary plug-in execution; Sudoku legality, equivalence, size
policies and solver evidence remain in libraries. Checks are not formal proofs.

`mathpub specimen my-specimens --component COMPONENT_ID --output publications/specimens.toml --style anna --projection student --seed 2026 --json`
creates a normal, component-backed publication descriptor and builds it through
the production renderer. Repeat `--component` for a specimen collection. The
result includes source-mapped physical page/region inventory from SyncTeX, source
references and the explicit seed. It does not detect domain-specific diagram
grids or scale screenshots. Print at actual size, not fit-to-page. Existing
descriptors or specimen editions are not overwritten.
