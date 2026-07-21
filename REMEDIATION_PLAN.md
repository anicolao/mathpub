# Mathpub Remediation Plan

## Purpose

This plan responds to the shortcomings observed while authoring Chapter 8 and turns them into a
testable implementation sequence. The immediate goal is to make component-based textbook
authoring reliable for both people and LLM harnesses without weakening mathpub's semantic model,
projection isolation, or reproducibility.

The principal conclusions are:

1. Component questions must become first-class preview targets. The current split between legacy
   questions and component questions is the most consequential workflow defect.
2. TeX failures must identify the useful error and its authored source, not merely preserve a large
   compiler log.
3. Examples need two legitimate representations: a cohesive authored body and a structured set of
   semantic fragments. Empty placeholder fragments must not be necessary.
4. Answer rendering needs explicit content types. Automatically guessing that arbitrary answer text
   is mathematics would be unsafe.
5. Plural collection directories and singular component kinds are not inherently inconsistent. The
   friction should be addressed through scaffolding, documentation, and helpful validation errors,
   not by introducing plural aliases into the component type system.

## Implementation Status (2026-07-20)

All phases in this plan are complete on `agent/implement-mvp`:

- `d7e63d3` routes isolated previews through the component publication pipeline.
- `d68f194` maps generated TeX failures back to authored components and persistent logs.
- `50af70c` makes cohesive and structured examples explicit, mutually exclusive forms.
- `7d861e7` adds `math`, `plain-text`, and `mixed-tex` fragment modes and preflight checks.
- `889c2b1` makes new projects and question scaffolds component-native, adds all five requested
  component templates, documents singular kinds versus plural collections, and suggests close
  canonical kinds for metadata typos.
- `0b1e407` converts Sage and TeX timeouts into structured mathpub failures instead of leaking
  Python tracebacks.
- `f17e55c` adds the Chapter 8 component review publication using one authoritative source for each
  cohesive example.

Existing legacy question directories remain readable so the reviewed physics and Algebra 2
publications still build, but new projects set `question_roots = []` and all scaffolding writes
`component.toml`. There is one implementation path for newly authored questions.

## Guiding Principles

- Prefer one authoritative component pipeline; migrate recent source when that produces a simpler
  system than maintaining parallel behavior.
- Prefer explicit semantic metadata over heuristics that guess an author's intent.
- Keep authored source separate from generated files beneath `build/`.
- Preserve deterministic seeds, placements, instance hashes, and validation evidence.
- Treat every question as a component internally, regardless of where its current metadata file
  lives.
- Make every reported failure actionable from the CLI, including in JSON mode for an LLM harness.
- Use only the toolchain supplied by `flake.nix` for implementation and verification.

## Phase 0: Capture Regressions Before Changing Behavior

Add focused fixtures that reproduce each substantive issue before implementing its remedy. Chapter
8 may inspire the fixtures, but tests should be small and independent of a full textbook build.

Required regression cases:

- An Anna-style example declared with only a `body` fragment.
- A structured example with no `steps` fragment and no empty placeholder file.
- A component of `kind = "question"` that can be checked and previewed by ID.
- Student, answer, solution, and validation previews of that component question.
- An answer containing a math-only TeX command outside math mode.
- A mixed prose-and-mathematics answer that must not be wrapped wholesale in math mode.
- A deliberately broken TeX fragment whose failure output includes a generated line, authored
  component, authored fragment, concise error excerpt, and valid persistent log path.
- A common plural-kind typo such as `kind = "misconceptions"` that produces a useful suggestion.

Acceptance criteria:

- Every test fails for the intended reason on the current implementation.
- Fixtures use explicit seeds and stable component placements.
- Tests assert structured error codes and fields rather than matching an entire human-readable log.

## Phase 1: Make Component Questions Previewable

### Design

Introduce a question-like resolution layer that can resolve either:

- A legacy `question.toml` entry from `question_roots`; or
- A `component.toml` entry from `component_roots` whose `kind` is `question`.

Duplicate IDs must remain invalid. Resolving an ID is only the first step: component questions must
use component instantiation and component rendering rather than being forced through the legacy
worksheet path.

For a component question, `preview` should create an internal minimal component publication with:

- A deterministic preview placement derived from the component ID;
- The requested seed and variant;
- A selectable publication style and font;
- The same projection boundaries used by a real component textbook; and
- A manifest containing the component ID, placement, seed, instance hash, checks, and output hashes.

Extend the command with repeatable projection selection. It should support `student`, `answers`,
`solutions`, and `validation`, plus a convenient way to request all four. All previews should use
the component publication path.

JSON output must state which source model was resolved so an agent can distinguish `question` from
`component-question` without parsing file paths.

### Acceptance Criteria

- `mathpub preview COMPONENT_QUESTION_ID --seed 2026 --replace --json` succeeds.
- Previewing a component question does not require compiling its containing textbook.
- All four projections can be generated and inspected independently.
- Prompt source never leaks answer or solution content into the student projection.
- The same seed and placement reproduce the same component instance hash.
- Questions currently stored in `question_roots` and questions stored in `component_roots` resolve
  through the same preview implementation.
- The repository's generated `AGENTS.md` instructions describe the correct check and preview commands
  for both question source models.

## Phase 2: Surface Actionable TeX Diagnostics

### Design

Keep the complete `latexmk` log, but parse its output before raising `MP-TEX-007`. At minimum, the
error should include:

- TeX engine and projection;
- The first meaningful file-and-line error;
- The primary TeX diagnostic;
- A short excerpt around the generated line;
- The affected authored component and fragment when known; and
- The final, persistent log path beneath the renamed `failed-*` build directory.

Generated TeX needs a source map. While assembling a publication, record generated line ranges for
each authored fragment in a machine-readable file such as `generated-tex/source-map.json`. TeX
comments may also mark boundaries for human inspection, but comments alone are not an adequate API.

Move or finalize the failure directory before constructing the user-facing error so the reported log
path continues to exist after the exception is handled.

JSON errors should expose structured fields such as:

```json
{
  "code": "MP-TEX-007",
  "projection": "answers",
  "generated_source": "generated-tex/example-answers.tex",
  "generated_line": 412,
  "component_id": "algebra1.example-question",
  "fragment": "answer",
  "authored_source": "components/example-question/answer.tex",
  "diagnostic": "Missing $ inserted",
  "log": "build/example/failed-.../logs/example-answers.build.log"
}
```

Human-readable output should present the same information concisely rather than dumping the entire
compiler transcript.

### Acceptance Criteria

- The log path printed after a failed build exists.
- A deliberately invalid component answer identifies `answer.tex` and the component ID.
- The CLI prints the relevant TeX diagnostic and a bounded excerpt.
- `--json` produces stable structured fields suitable for an agent to act on.
- Successful builds retain their existing deterministic output behavior.

## Phase 3: Support Cohesive and Structured Examples

### Schema

Replace the unconditional four-fragment requirement for examples with two mutually exclusive forms:

1. Cohesive form: `body` is required.
2. Structured form: `prompt` and `result` are required; `thought_process`, `steps`, and `check` are
   optional.

An example must use one form, not a mixture of both. This should be expressed in the JSON Schema so
invalid combinations fail during `check component` with a clear explanation.

### Rendering

Both forms must render under every supported publication style. The style controls presentation, not
which semantic representation is legal.

For structured examples, omit absent optional sections cleanly. Do not emit empty labels, blank
paragraphs, or require empty files. Validation evidence remains appended only to the validation
projection.

Parameterized cohesive examples remain valid: `body.tex` may use the same mathpub substitutions as
other component fragments, and their generators must follow the same deterministic validation rules.

### Acceptance Criteria

- Existing reviewed structured examples continue to validate and render.
- A body-only example validates and renders in both Anna and standard styles.
- A structured example without thought-process or steps files validates and contains no empty
  headings.
- Declaring both `body` and structured fragments fails with an actionable schema error.
- Parameter expansion and validation notes work in either representation.

## Phase 4: Add Explicit Answer Content Types

### Design

Do not automatically wrap arbitrary answer fragments in math mode. Instead, add authoritative
fragment-mode metadata. A possible form is:

```toml
[fragment_modes]
answer = "math"
solution = "mixed-tex"
```

Supported modes should be narrowly defined:

- `math`: the fragment is a mathematical expression. Mathpub supplies inline math delimiters, and
  authored delimiters in the fragment are rejected to prevent double wrapping.
- `plain-text`: the fragment is escaped as text and cannot contain raw TeX commands.
- `mixed-tex`: the fragment is trusted authored TeX with explicit math delimiters. This is the
  compatibility default for existing components.

The mode describes content before visual wrappers such as `\annaanswer` are applied. Presentation
macros must not be responsible for deciding whether content is mathematics.

Add preflight checks for common, reliably detectable mistakes in `mixed-tex`, including unbalanced
math delimiters and unambiguous math-only commands in text mode. The linter should not pretend to be
a complete TeX parser; uncertain cases should be left to compilation and its improved diagnostics.

Generated Sage display values should retain enough type information for templates or future typed
fragments to render them without guessing.

### Acceptance Criteria

- A `math` answer containing `-x^2` renders correctly without authored delimiters.
- A prose property name remains text and is not placed in math mode.
- Mixed prose and mathematics remain supported through `mixed-tex`.
- Double-delimited `math` content fails before TeX compilation with an authored-source error.
- Existing components without mode metadata retain current behavior.
- Answer emphasis, punctuation, and projection isolation remain unchanged.

## Phase 5: Improve Naming Guidance and Scaffolding

### Decision

Keep canonical component kinds singular. Plural directories name collections and do not need to
match the singular type of each contained object.

### Work

- Document the distinction explicitly in authoring guidance and generated `AGENTS.md` files.
- Ensure scaffolding creates canonical directory and kind combinations.
- Add close-match suggestions for invalid kind values.
- Provide complete templates for objective, misconception, teaching-tip, example, and component
  question metadata.
- Ensure LLM-facing instructions show exact canonical values rather than asking the agent to infer
  them from directory names.

### Acceptance Criteria

- `kind = "misconceptions"` suggests `misconception`.
- Newly scaffolded components validate without manual metadata repair.
- Documentation consistently distinguishes collection paths from entity kinds.
- No plural aliases are added to the persisted component schema.

## Delivery Sequence

Implement the work as small, reviewable commits:

1. Add failing regression fixtures and structured error-test helpers.
2. Add question-like resolution and component-question preview.
3. Add TeX source mapping and improved failure diagnostics.
4. Relax and reconcile the example schema and renderer.
5. Add answer content modes and preflight validation.
6. Improve kind suggestions, scaffolding, and authoring documentation.
7. Rebuild the Chapter 1 and Chapter 8 review publications and record explicit seeds and hashes.

Each behavior-changing commit should include its tests. Schema changes and migrations should not be
combined with unrelated visual-template changes.

## Verification

At the end of each relevant phase, run the narrow tests first and then the repository checks through
the flake environment. Final acceptance includes:

```console
nix run .#mathpub -- check project --json
nix run .#mathpub -- check component COMPONENT_QUESTION_ID --seeds 20 --json
nix run .#mathpub -- preview COMPONENT_QUESTION_ID --seed 2026 --replace --json
nix run .#mathpub -- check publication publications/algebra1-chapter1-components.toml --json
nix run .#mathpub -- check publication publications/algebra1-chapter8-components.toml --json
nix flake check
```

Publication builds used for visual review must record the seed, variant, projection list, page counts,
and output hashes. Failure-path tests must also verify that diagnostics remain valid after temporary
build directories are renamed.

### Verification record: seed `2026`, variant `remediation`

`nix flake check` passed on `aarch64-darwin`. `check project`, both publication checks, a 20-seed
component-question check, the four-projection isolated preview, and both five-projection chapter
builds also passed.

| Publication | Projection | Pages | SHA-256 |
| --- | --- | ---: | --- |
| Chapter 1 | student | 32 | `97f6f88ceb4860e5d1c50e43819f9271c072f9a3a927cf8b329fe1eb01a6b9c1` |
| Chapter 1 | answers | 43 | `66aabf936be725abd7ad626d5ff67a7f79992c53cf509243c69ec5af27dc5dbd` |
| Chapter 1 | solutions | 43 | `58ba64acae0429d56925383dcd9f97a7b9f651b92c718ac5a99386d1fe30b756` |
| Chapter 1 | validation | 60 | `1341cababb96533d6d56f312e255dfc904acae87dd119fed99b2ef3859de41be` |
| Chapter 1 | parent | 43 | `c58c5567b9c9d7e79848d740d0d7f22088b84d53af67c6b10a836749eb12371d` |
| Chapter 8 | student | 14 | `24a82cf73839e6c3621335015c36714e7a02dd7f71544053ebee8d854b14006a` |
| Chapter 8 | answers | 17 | `0ae38958c32037be7aca042eed7af7b6ee23ec34048d53777edaa7a3340fbf04` |
| Chapter 8 | solutions | 17 | `78c0b7dbb5608348f8ecec6514ced18dca1fd4592ae54cb128ecdc0bd141d631` |
| Chapter 8 | validation | 21 | `9edde464f12bd175862f1d01f307405ca928475049eb3f346a3c99e89ddb5ad2` |
| Chapter 8 | parent | 17 | `cd16e8dfba2f4a40e5216af50c1be374ac0bb19a0c6fad11c6a3c141bca85cb1` |

The isolated preview target was `algebra1.factoring.question-01`. Its static instance hash was
`9e373e601033b5d05bef6d8053d929bd8a5e0a42b65f89b4e6fc4488b903b671` for all 20 sampled seeds,
as expected for reviewed static mathematics. Preview PDFs are recorded in
`build/preview.algebra1.factoring.question-01/preview/manifest.json`; chapter manifests are under
their respective `build/algebra1.chapter*-components/remediation/` editions.

## Explicit Non-Goals

This remediation does not:

- Introduce plural component kinds;
- Infer math mode from arbitrary prose using heuristics;
- Automatically rewrite authored TeX;
- Collapse all legacy and component metadata into one on-disk schema in a single migration;
- Change the visual design of existing textbook templates; or
- Claim that successful TeX compilation or Sage checks constitute a formal mathematical proof.

The longer-term unification of the two question source formats and integration with a formal proof
system remain architectural goals. This plan removes the immediate authoring and validation barriers
without conflating those larger projects with the Chapter 8 remediation.
