# mathpub MVP design: tests and worksheets

## 1. Purpose

The mathpub minimum viable product will create reproducible mathematical tests, worksheets, and their answer keys from reusable TeX question modules backed by SageMath.

The MVP takes its central authoring idea from the earlier `mechanics` project:

- a publication selects reusable question files;
- each question owns its parameter generation, prompt, and solution;
- SageMath computes values used by both the prompt and solution; and
- student and teacher editions are rendered from the same generated instance.

The MVP makes that workflow deterministic, testable, portable, and auditable. It does not attempt to solve textbook, article, or slideshow publishing yet.

This document is a proposed implementation contract. Examples are normative unless explicitly marked as illustrative.

## 2. MVP outcomes

A successful MVP lets an author:

1. enter a Nix development shell on nix-darwin or Linux;
2. create reusable fixed or parameterized questions;
3. assemble those questions into a worksheet or test;
4. build a student PDF and matching answer-key PDF using one seed;
5. reproduce the same edition later from its manifest;
6. generate several named variants without answer drift;
7. reject mathematically or pedagogically invalid instances;
8. validate individual questions across many seeds;
9. inspect the exact parameters, derived values, and checks used in a build; and
10. receive errors referring to the question and build stage rather than only generated TeX.

The MVP is complete when it can faithfully migrate representative material from `mechanics`, including a numerical question, a symbolic question, and a parameterized TikZ diagram.

## 3. Scope

### 3.1 Included

- Tests and worksheets composed from an ordered question bank.
- Fixed questions and SageMath-parameterized questions.
- TeX prompts, final answers, worked solutions, and TikZ diagrams.
- Student and teacher PDFs.
- Optional short-answer keys containing final answers without worked solutions.
- Deterministic seeds and named variants.
- Exact SageMath computation with explicit display formatting.
- Generator constraints and independent validation checks.
- Point values, section headings, instructions, and workspace sizing.
- A default professional TeX profile based on the `exam` class.
- Custom project-local TeX profiles.
- Build manifests and immutable generated question instances.
- Question-level tests, corpus checks, and basic PDF regression testing.
- A Nix flake supporting Apple Silicon macOS, Intel macOS where practical, and common 64-bit Linux systems supported by SageMath in nixpkgs.

### 3.2 Explicitly deferred

- Textbooks, workbooks, articles, and slideshows.
- A general-purpose structured mathematical document model.
- Formal proof-assistant integration.
- Browser-based or graphical authoring.
- HTML, EPUB, MathML, and learning-management-system export.
- Automatic grading, answer-sheet scanning, and student data.
- Collaborative editing or a hosted service.
- Remote execution of untrusted question code.
- Arbitrary conversion of existing TeX documents.
- Global content registries, dependency servers, and package marketplaces.
- Guaranteed byte-for-byte reproducible PDFs across different operating systems.

The MVP will leave extension points for some deferred features, but it will not implement speculative abstractions solely for them.

## 4. Product vocabulary

- **Question definition:** authored source describing generation, validation, prompt, solution, and metadata.
- **Question instance:** an immutable accepted parameter set and all values derived from it.
- **Publication:** an ordered specification for a test or worksheet.
- **Edition:** one publication built with a particular variant and root seed.
- **Projection:** a rendering of an edition, such as `student`, `answers`, or `solutions`.
- **Profile:** shared TeX document structure and visual styling.
- **Generator:** SageMath code that proposes parameters and derives answers.
- **Constraint:** a predicate that determines whether a proposed instance is suitable.
- **Check:** a verification performed after generation. A check does not alter the instance.
- **Manifest:** the machine-readable provenance record for an edition.
- **Question ID:** a stable, project-wide identifier such as `mechanics.kinematics.ramp-speed`.

## 5. Design principles

### 5.1 Generate once, project many times

Student, short-answer, and worked-solution editions must consume the same serialized question instances. Rendering an answer key must never invoke a generator again.

### 5.2 TeX is presentation, not hidden build state

TeX may control notation and layout, but it will not choose random parameters, call SageMath, or determine which mathematical instance is being published.

### 5.3 SageMath is computation, not universal proof

SageMath will generate parameters, manipulate exact expressions, and perform declared checks. The manifest will describe those results as generated, symbolically checked, exhaustively checked, or sampled—not formally proved.

### 5.4 Exact values precede display values

Generators should retain integers, rationals, algebraic expressions, and symbolic constants until a declared formatting step. Rounded strings are presentation artifacts, not canonical answers.

### 5.5 Every accepted instance explains why it is acceptable

Constraints and checks have stable names. Their outcomes are recorded. Rejected proposals are counted and diagnosable.

### 5.6 Stable identifiers isolate randomness

Changing one question, inserting a new question, or reordering a publication must not silently change the parameters of unrelated questions.

### 5.7 Generated files are inspectable and disposable

All intermediates live under the build directory. Authored source never depends on an untracked SageTeX cache or auxiliary file.

## 6. User workflow

### 6.1 Enter the environment

```console
nix develop
mathpub --version
```

No global TeX, SageMath, Python package, or font installation is required.

### 6.2 Create or migrate a question

```console
mathpub new question mechanics.kinematics.ramp-speed
mathpub check question mechanics.kinematics.ramp-speed
mathpub preview mechanics.kinematics.ramp-speed --seed 42
```

`preview` creates a small PDF showing the prompt followed by its worked solution and writes it beneath `build/previews/`.

### 6.3 Assemble a publication

```console
mathpub check publication publications/mechanics-practice.toml
mathpub build publications/mechanics-practice.toml --seed 2026 --variant A
```

The build produces:

```text
build/mechanics-practice/A/
├── manifest.json
├── instances/
│   ├── mechanics.kinematics.ramp-speed.json
│   └── mechanics.forces.car-curve.json
├── generated-tex/
├── logs/
├── mechanics-practice-A-student.pdf
├── mechanics-practice-A-answers.pdf
└── mechanics-practice-A-solutions.pdf
```

The publication decides which projections to create. The default is `student` plus `solutions`.

### 6.4 Rebuild an exact edition

```console
mathpub reproduce build/mechanics-practice/A/manifest.json
```

`reproduce` reads the stored instances and pinned source identities. It does not generate new parameters. It fails if required source or toolchain identities differ unless `--allow-different-toolchain` is supplied. That override is recorded in the new manifest.

## 7. Repository layout

The reference project layout is:

```text
mathpub-project/
├── flake.nix
├── flake.lock
├── mathpub.toml
├── questions/
│   └── mechanics/
│       └── kinematics/
│           └── ramp-speed/
│               ├── question.toml
│               ├── generate.sage
│               ├── prompt.tex
│               ├── answer.tex
│               ├── solution.tex
│               └── assets/
├── publications/
│   └── mechanics-practice.toml
├── profiles/
│   └── school-exam/
│       ├── profile.toml
│       ├── document.tex
│       └── profile.sty
├── tests/
│   ├── golden/
│   └── visual/
└── build/
```

Only `flake.nix`, `flake.lock`, project configuration, authored content, profiles, and intentionally accepted test fixtures belong in version control. `build/` is ignored.

## 8. Project configuration

The root `mathpub.toml` identifies source directories and defaults:

```toml
schema = 1
project = "mechanics"
question_roots = ["questions"]
profile_roots = ["profiles"]
build_dir = "build"
default_profile = "mathpub.exam"

[generation]
max_attempts = 100

[tex]
engine = "lualatex"
shell_escape = false
halt_on_warning = false
fatal_warnings = [
  "Undefined control sequence",
  "There were undefined references",
  "Citation .* undefined",
]
```

Paths are relative to the project root. The MVP supports one project configuration per invocation and does not search parent directories beyond the first `mathpub.toml` found.

## 9. Question definition

Each question is a directory. This avoids a large mixed TeX/Sage file while keeping all relevant material adjacent.

### 9.1 `question.toml`

```toml
schema = 1
id = "mechanics.kinematics.ramp-speed"
title = "Speed at the bottom of a ramp"
kind = "numeric"
points = 4
tags = ["mechanics", "energy", "kinematics"]
difficulty = 2
generator = "generate.sage"
prompt = "prompt.tex"
answer = "answer.tex"
solution = "solution.tex"

[workspace]
student = "55mm"
answers = "0mm"
solutions = "0mm"

[testing]
sample_seeds = 100
max_attempts = 50

[[testing.exhaustive_domains]]
name = "teaching-domain"
parameters = { angle_deg = "20..30", length_m = "25..45" }
```

Required fields are `schema`, `id`, `title`, `points`, and `prompt`. A question without a generator is fixed. `answer.tex` and `solution.tex` are optional independently, although a publication requesting a missing projection fails validation.

Question IDs must match `[a-z0-9]+([.-][a-z0-9]+)*` and must be unique across all question roots. Renaming a question ID is a reproducibility-breaking change and should be recorded explicitly in version control.

The MVP treats tags and difficulty as descriptive metadata. It will not automatically select questions by them.

### 9.2 Sage generator interface

`generate.sage` is executed by SageMath in an isolated working directory with the question directory available read-only by convention. It exports one function:

```python
from mathpub import question

@question.generator
def generate(ctx):
    angle = ctx.random.integer(20, 30)
    length = ctx.random.integer(25, 45)

    g = QQ(98) / 10
    theta = angle * pi / 180
    speed = sqrt(2 * g * sin(theta) * length)

    ctx.parameter("angle_deg", angle)
    ctx.parameter("length_m", length)
    ctx.derived("theta", theta)
    ctx.derived("speed", speed)

    ctx.require("positive-speed", speed > 0)
    ctx.require("reasonable-speed", speed < 40)

    ctx.check_equal(
        "energy-conservation",
        lhs=(QQ(1) / 2 * speed^2).simplify_full(),
        rhs=g * length * sin(theta),
    )

    ctx.display.integer("angle", angle)
    ctx.display.quantity("length", length, unit=r"\meter")
    ctx.display.decimal("speed", speed, places=1, unit=r"\meter\per\second")
    ctx.display.math("speed_exact", speed)
```

The generator returns through `ctx`; arbitrary standard output is captured in the question log and never parsed as data.

The public MVP generator API is deliberately small:

- `ctx.random.integer(low, high)`, inclusive;
- `ctx.random.choice(sequence)`;
- `ctx.random.rational(numerators, denominators)`;
- `ctx.parameter(name, value)`;
- `ctx.derived(name, value)`;
- `ctx.require(name, condition, detail=None)`;
- `ctx.check_equal(name, lhs, rhs)`;
- `ctx.check_close(name, lhs, rhs, atol, rtol=0)`;
- `ctx.check_true(name, condition, detail=None)`;
- `ctx.display.text(name, value)`;
- `ctx.display.integer(name, value)`;
- `ctx.display.decimal(name, value, places, trailing_zeros=True, unit=None)`;
- `ctx.display.significant(name, value, digits, unit=None)`;
- `ctx.display.math(name, value)` using Sage's LaTeX formatter;
- `ctx.display.quantity(name, value, unit)`; and
- `ctx.display.tex(name, trusted_tex)` for an explicitly trusted TeX fragment.

Names must be unique within their namespace and match `[a-z][a-z0-9_]*`. The implementation rejects non-finite decimal results, undeclared display values, duplicate declarations, and values it cannot serialize.

Direct use of global Sage/Python random functions is forbidden by policy and detected by a lint check for common calls. It cannot be made impossible for trusted local code in the MVP, so determinism is also tested by running a generator twice and comparing canonical instances.

### 9.3 Value serialization

Question instances use canonical JSON with tagged mathematical values. The MVP supports:

- integers;
- rational numbers as signed numerator and positive denominator;
- finite real approximations as decimal strings plus declared precision;
- Sage symbolic expressions as Sage source text plus rendered TeX;
- booleans and strings;
- homogeneous lists of supported values; and
- records with sorted string keys.

Example:

```json
{
  "type": "rational",
  "numerator": 49,
  "denominator": 5
}
```

Canonical instances sort object keys, use UTF-8, normalize line endings to LF, and end with one newline. Their SHA-256 hashes are recorded in the edition manifest.

Symbolic expressions are serialized for inspection and rendering, not evaluated when an edition is reproduced. Reproduction consumes the stored display values and generated TeX. A future version may define a stronger symbolic interchange format.

### 9.4 Constraints and rejection

`ctx.require` is for suitability constraints. When a constraint fails, the entire proposal is discarded and generation resumes with the next deterministic attempt stream.

For question ID `Q`, root seed `S`, variant `V`, and attempt `N`, the random seed is:

```text
SHA-256("mathpub-mvp\0" || S || "\0" || V || "\0" || Q || "\0" || N)
```

Fields are UTF-8 strings, and `N` is an unsigned base-10 integer. The 256-bit digest is interpreted as an unsigned big-endian integer and passed to NumPy's seed sequence to initialize mathpub's documented pseudorandom generator. The MVP must choose and version a concrete generator rather than relying on Python's or Sage's default global generator. The proposed choice is NumPy `PCG64`, with its package version pinned by Nix and `rng_algorithm = "pcg64-v1"` recorded in manifests.

Question values therefore do not depend on publication order. Duplicate question IDs in one publication are rejected in the MVP; authors should create distinct wrapper question IDs when intentional repeats need independent values.

If no proposal is accepted within `max_attempts`, generation fails with the question ID, attempted seeds, rejection count by constraint, and the final rejection details. It never silently relaxes a constraint.

### 9.5 Checks versus constraints

A constraint can reject a proposed pedagogical instance, such as an undesirable repeated root. A check asserts that the accepted computation is internally consistent, such as substitution of an answer into the original equation.

A failed check fails the build immediately. It is not treated as random bad luck and does not cause another proposal to be chosen. This prevents a faulty model from being hidden by retrying until a check happens to pass.

### 9.6 TeX fragments

`prompt.tex`, `answer.tex`, and `solution.tex` are ordinary TeX fragments with mathpub lookup commands:

```tex
A block slides from rest down a frictionless ramp inclined at
\mpvalue{angle}\unit{\degree}. The ramp is
\mpvalue{length}. Find its speed at the bottom.
```

```tex
\mpvalue{speed}
```

```tex
Conservation of energy gives
\[
  mgh = \frac12 mv^2,
  \qquad h = \mpparameter{length_m}\sin(\mpvalue{angle}\unit{\degree}).
\]
Therefore
\[
  v = \sqrt{2gL\sin\theta}
    = \mpvalue{speed}.
\]
```

Supported commands are:

- `\mpvalue{name}`: a declared, already formatted display value;
- `\mpparameter{name}`: canonical TeX rendering of a parameter;
- `\mpderived{name}`: canonical TeX rendering of a derived value; and
- `\mpasset{path}`: an asset beneath the question's `assets/` directory.

There is no generic expression evaluator inside TeX.

Missing names fail before LuaLaTeX runs. Plain text display values are TeX-escaped. Math and trusted-TeX display values are inserted verbatim and are visibly marked as trusted in the instance JSON.

TeX fragments may use profile-provided packages and commands but may not contain `\documentclass`, `\begin{document}`, `\end{document}`, `\include`, or direct file access outside `\mpasset`. The MVP enforces common cases with linting and compiles in an isolated build directory with shell escape disabled. Since TeX is not a secure sandbox, projects must treat question and profile source as trusted code.

### 9.7 Diagrams

TikZ is the required parameterized-diagram mechanism for the MVP. A prompt or solution may contain TikZ directly and use declared values. Complex repeated diagrams can live in `assets/*.tex` and be included only through `\mpasset`.

Generated raster or vector graphics from Sage are deferred unless needed by the migration corpus. If implemented, the only supported API will write declared assets into the question instance directory with recorded hashes; templates will never reference unpredictable SageTeX filenames.

## 10. Publication definition

Tests and worksheets share one schema. Their difference is semantic metadata and default styling, not a separate build pipeline.

```toml
schema = 1
id = "mechanics-practice-dec-08"
kind = "worksheet"
title = "Mechanics Practice Questions"
subtitle = "Energy, circular motion, and forces"
course = "Mechanics"
author = "Ethan Nicolaou"
profile = "mathpub.exam"
paper = "letter"
projections = ["student", "answers", "solutions"]

[student_fields]
name = true
date = true
class_period = false

[instructions]
tex = "Show your work and include units with every numerical answer."

[[sections]]
title = "Practice questions"

[[sections.questions]]
id = "mechanics.kinematics.ramp-speed"
points = 4
page_break_after = false

[[sections.questions]]
id = "mechanics.forces.car-curve"
points = 6
page_break_after = true
```

Required fields are `schema`, `id`, `kind`, `title`, `profile`, and at least one question. `kind` is `test` or `worksheet`. Publication IDs follow the same syntax as question IDs.

A publication may override points and workspace but cannot override generator parameters in the MVP. Parameter overrides complicate the identity and test domain of a question and are deferred.

The publication order controls rendering only. It does not affect generation.

### 10.1 Projections

- **student:** prompt and configured workspace; no answer or solution content is loaded into generated student TeX.
- **answers:** prompt followed by the final answer, using a compact profile layout by default.
- **solutions:** prompt followed by the worked solution; if `answer.tex` exists, the profile may show it as a summary.

This is stronger than conditionally hiding solutions in one TeX document: the generated student source does not contain them. A static leak check fails if known answer or solution fragment hashes appear in student generated source. This check reduces accidental leakage but is not a semantic proof that prose does not reveal an answer.

### 10.2 Tests versus worksheets

The default profile varies presentation by `kind`:

| Behavior | Worksheet | Test |
| --- | --- | --- |
| Running total of points | Optional | Enabled |
| Student name/date fields | Enabled | Enabled |
| Workspace | Question default | Publication/profile default may enlarge it |
| Solutions in student PDF | Never | Never |
| Page header | Title | Course, title, page count |
| Answer-key point rubric | Optional | Enabled where provided |

No security claims are made for test secrecy. Generated PDFs and manifests are ordinary local files.

## 11. Rendering architecture

The pipeline has explicit stages:

```text
discover → validate source → instantiate → validate instances
         → generate TeX → compile → inspect PDF → write manifest
```

### 11.1 Discovery

The CLI loads `mathpub.toml`, indexes question metadata, indexes profiles, and resolves the publication. Duplicate IDs, path escapes, unknown schema versions, and missing files fail here.

### 11.2 Source validation

TOML schemas, identifiers, TeX fragment restrictions, generator interface, projection availability, and asset paths are checked without generating an edition.

### 11.3 Instantiation

Each question generator runs in a separate Sage process. Per-question processes provide failure isolation and eliminate cross-question global state. The orchestrator supplies a JSON request containing the seed material and receives canonical JSON on a dedicated file descriptor or output file, never mixed with diagnostic output.

Parallel generation is permitted because seeds are question-local. The initial implementation may run serially for simpler diagnostics.

### 11.4 Instance validation

The orchestrator validates the returned schema, canonicalizes values, confirms all requested display names exist, verifies checks succeeded, and writes one immutable JSON file per question.

### 11.5 TeX generation

For each projection, mathpub:

1. renders profile metadata;
2. defines display values as safely named TeX commands scoped to one question;
3. copies or links declared assets into a projection-specific staging tree;
4. appends the appropriate prompt, answer, or solution fragments; and
5. emits a complete `document.tex` plus a source map from generated lines to authored files.

The source map is used to augment TeX failures with the question ID and fragment path.

### 11.6 Compilation

The MVP uses LuaLaTeX through `latexmk` with:

- nonstop interaction for complete logs;
- halt on errors;
- file-line errors;
- shell escape disabled;
- an explicit output directory;
- a bounded number of passes; and
- `SOURCE_DATE_EPOCH` derived from the Git commit time when available, otherwise zero.

The default profile uses the `exam`, `fontspec`, `amsmath`, `mathtools`, `siunitx`, `tikz`, `microtype`, and `geometry` packages. The precise TeX Live closure is pinned in `flake.lock`.

### 11.7 PDF inspection

After compilation, the MVP verifies:

- the PDF exists and is non-empty;
- its page count is nonzero;
- expected title text is extractable;
- no page is completely blank unless an explicit blank page was requested;
- the TeX log contains no configured fatal warning; and
- all projections refer to the same instance hashes.

Visual excellence still requires human review. Automated checks catch regressions, not every layout defect.

## 12. Build manifest

`manifest.json` is written only after every requested projection succeeds. It contains:

```json
{
  "schema": 1,
  "mathpub_version": "0.1.0",
  "project": "mechanics",
  "publication_id": "mechanics-practice-dec-08",
  "publication_kind": "worksheet",
  "variant": "A",
  "root_seed": "2026",
  "rng_algorithm": "pcg64-v1",
  "source": {
    "git_commit": "abc123...",
    "dirty": false,
    "flake_lock_sha256": "...",
    "publication_sha256": "...",
    "profile_sha256": "...",
    "question_sources_sha256": "..."
  },
  "toolchain": {
    "system": "aarch64-darwin",
    "nix_derivation": "/nix/store/...",
    "sage": "...",
    "lualatex": "...",
    "mathpub": "..."
  },
  "questions": [
    {
      "id": "mechanics.kinematics.ramp-speed",
      "attempt": 0,
      "instance": "instances/mechanics.kinematics.ramp-speed.json",
      "sha256": "...",
      "checks": ["energy-conservation"]
    }
  ],
  "outputs": [
    {
      "projection": "student",
      "path": "mechanics-practice-A-student.pdf",
      "sha256": "...",
      "pages": 3
    }
  ]
}
```

Absolute source paths, usernames, temporary paths, and timestamps are omitted because they harm portability and reproducibility. Wall-clock build time may appear in a separate diagnostic report but not in the canonical manifest.

A dirty tree is allowed for local development and clearly recorded. Release builds may use `--require-clean`.

## 13. Command-line interface

The executable is `mathpub`. Commands return zero on success and nonzero on failure. Human-readable diagnostics go to standard error; machine-readable results requested with `--json` go to standard output.

### 13.1 Commands

```text
mathpub init [DIRECTORY]
mathpub new question QUESTION_ID
mathpub check project [--all-seeds N]
mathpub check question QUESTION_ID [--seeds N] [--exhaustive]
mathpub check publication PATH
mathpub preview QUESTION_ID [--seed SEED]
mathpub build PUBLICATION [--seed SEED] [--variant NAME]
                  [--projection NAME]... [--require-clean]
mathpub variants PUBLICATION --seed SEED --count N
mathpub reproduce MANIFEST [--allow-different-toolchain]
mathpub clean [--edition PUBLICATION/VARIANT]
mathpub --version
```

### 13.2 Seed behavior

`build` requires an explicit seed unless the publication declares one. The CLI never invents an unreported seed. A convenience `--random-seed` may be added later if it prints and records a cryptographically generated seed before doing work.

`variants --count 3` produces variants `A`, `B`, and `C`. Variant naming after `Z` uses `AA`, `AB`, and so on. Each variant shares the supplied root seed but receives an isolated variant component in question seed derivation.

### 13.3 Exit codes

- `0`: success;
- `2`: CLI usage error;
- `3`: source or schema validation failure;
- `4`: generation exhausted its attempts;
- `5`: mathematical check failure;
- `6`: TeX compilation failure;
- `7`: PDF inspection or regression failure;
- `8`: reproducibility/toolchain mismatch; and
- `1`: unexpected internal failure.

## 14. Testing strategy

Testing is part of the product, not only its implementation.

### 14.1 Generator unit tests

For a fixed seed, tests assert exact canonical parameters, derived values, display values, constraint outcomes, and checks. These fixtures catch unintended generator changes.

### 14.2 Determinism tests

Every generator is run twice in fresh Sage processes for the same seed. Canonical instance bytes must match. A publication is also built with questions reordered; each question's instance hash must remain unchanged.

### 14.3 Constraint-domain tests

For declared finite domains, `--exhaustive` enumerates every parameter combination without randomness and applies constraints and checks. It reports:

- total combinations;
- accepted and rejected counts;
- rejection count per constraint;
- check failures;
- minimum and maximum numeric outputs where available; and
- duplicate rendered prompts or answers.

For large or non-finite domains, deterministic sample testing runs the configured number of seeds. Reports must call this sampled verification, not exhaustive verification.

### 14.4 Independent mathematical checks

Migrated questions require at least one check that is not simply formatting the computed answer. Examples include substituting a solution back into an equation, comparing conserved quantities, differentiating an antiderivative, or confirming a numeric residual.

The MVP does not require two independently implemented solvers, but its documentation should encourage them for high-value questions.

### 14.5 Schema and lint tests

Tests cover duplicate IDs, missing fragments, invalid paths, forbidden global randomness, missing display values, unsupported serialized values, non-finite decimals, answer projection leaks, and unsupported schema versions.

### 14.6 TeX tests

Each example question must compile in preview mode. Each example publication must compile every declared projection. Logs are checked for errors, undefined references, missing glyphs, and overfull boxes above a configurable threshold.

Overfull boxes are warnings by default during authoring and fatal in checked golden publications.

### 14.7 PDF structural tests

Tests inspect page count, paper size, expected text, metadata normalization, and absence of unintended blank pages. Student output is checked not to contain configured answer-key headings or solution fragment content.

### 14.8 Visual regression tests

A small representative corpus is rasterized at a pinned resolution and compared against reviewed images. The comparison permits a small configured pixel tolerance for renderer variation. Updating golden images requires an explicit command and human review.

Visual regression is required for the default profile and three migration examples, not for every generated seed.

### 14.9 CLI and integration tests

End-to-end tests cover:

- clean project initialization;
- successful paired builds;
- multiple variants;
- exact reproduction from a manifest;
- a constraint that exhausts its attempts;
- a failed mathematical check;
- a TeX error attributed to its question;
- a missing answer projection;
- a dirty source tree recorded in provenance; and
- a toolchain mismatch on reproduction.

### 14.10 Nix checks

`nix flake check` runs formatting, static analysis, unit tests, generator tests, and a small end-to-end TeX build. Expensive exhaustive and visual suites may be separate flake checks but must run in continuous integration.

## 15. Default profile

The built-in `mathpub.exam` profile provides a professional but restrained baseline:

- LuaLaTeX with OpenType text and math fonts available in the Nix closure;
- `exam` class question numbering and point accounting;
- configurable US Letter and A4 paper;
- consistent heading hierarchy, margins, line spacing, and page furniture;
- `siunitx` units;
- framed or clearly separated worked solutions;
- compact final-answer projection;
- stable whitespace for student work;
- widow/orphan and obvious overfull-box mitigation;
- embedded fonts; and
- conservative grayscale-safe styling.

The initial fonts should be open licensed and selected only after visual review. A likely baseline is Libertinus Serif with Libertinus Math, but this is a review decision rather than a fixed MVP requirement.

Profiles are trusted TeX code. A custom profile has:

```toml
schema = 1
id = "school.exam"
document = "document.tex"
style = "profile.sty"
supports = ["student", "answers", "solutions"]
```

The profile receives a generated content file and publication metadata commands. It does not receive direct access to SageMath or generator source.

## 16. Implementation architecture

### 16.1 Language and runtime

The orchestrator will be Python running from the pinned SageMath Python environment. This minimizes impedance with Sage objects while keeping process orchestration, TOML parsing, JSON, hashing, and CLI logic conventional.

Question generators still run out of process. The orchestrator must not import arbitrary generator modules into its long-lived process.

### 16.2 Internal components

```text
mathpub.cli          command parsing and exit codes
mathpub.config       TOML loading and schema validation
mathpub.catalog      question/profile discovery and ID resolution
mathpub.seed         versioned seed derivation and random context
mathpub.runner       isolated Sage generator execution
mathpub.values       canonical mathematical value serialization
mathpub.instance     constraints, checks, and instance schema
mathpub.tex          TeX expansion, staging, and source maps
mathpub.compile      latexmk invocation and log diagnostics
mathpub.pdf          structural and visual inspection
mathpub.manifest     provenance and reproduction
```

The first implementation may combine modules, but their responsibilities and data boundaries should remain recognizable.

### 16.3 Schemas

TOML and JSON schemas are versioned independently with an integer `schema` field. Unknown versions fail; they are never interpreted as the newest known version. JSON Schema files should be shipped for editor integration and instance validation.

### 16.4 Atomic builds

An edition is first built under `build/.tmp-<random>/`. Once every projection and the manifest succeed, it is atomically renamed to its final directory. A failed build retains logs in a clearly named failure directory unless `--discard-failures` is requested.

If the final edition directory already exists:

- identical manifest inputs may reuse or verify it;
- different inputs cause an error; and
- replacement requires `--replace`, which first moves the existing edition to a timestamp-free backup name based on its manifest hash.

The MVP must not silently overwrite an edition.

### 16.5 Caching

Question instances may be cached by the hash of:

- question source and assets;
- generator API version;
- root seed, variant, and question ID;
- RNG algorithm version; and
- SageMath/mathpub toolchain identity.

Cache reuse is an optimization only. Turning the cache off must yield identical canonical instances.

## 17. Nix flake

The flake exposes:

- `packages.<system>.mathpub`: CLI and runtime;
- `packages.<system>.default`: the same package;
- `apps.<system>.mathpub`: runnable CLI;
- `devShells.<system>.default`: author/developer environment;
- `checks.<system>.unit`: fast code tests;
- `checks.<system>.integration`: representative document builds; and
- `formatter.<system>`: project formatter.

The runtime closure includes only the selected TeX packages, SageMath runtime, fonts, `latexmk`, and PDF inspection tools. The dev shell additionally includes linters, formatters, and visual-diff utilities.

The flake pins nixpkgs in `flake.lock`. Support is defined by passing flake checks, not merely by evaluating a package. CI should cover at least `aarch64-darwin` and `x86_64-linux`; other systems are best effort until continuously tested.

## 18. Diagnostics

Errors use a consistent structure:

```text
error[MP-GEN-004]: question mechanics.kinematics.ramp-speed
  generation failed after 50 attempts

  rejected by reasonable-speed: 50
  final attempt: 49
  final detail: computed speed 43.7 m/s exceeds 40 m/s

  source: questions/mechanics/kinematics/ramp-speed/generate.sage:15
```

Diagnostics include:

- stable error code;
- publication and question ID where applicable;
- pipeline stage;
- authored source path and line when known;
- concise cause;
- relevant values without dumping an entire Sage namespace; and
- path to detailed logs.

TeX errors are augmented through the generated source map. Raw logs remain available.

## 19. Safety and trust model

Question generators are executable Sage/Python code, profiles are executable TeX in practical terms, and both are trusted local project inputs. The MVP does not claim to sandbox hostile content.

It nevertheless reduces accidental damage by:

- running generators in temporary working directories;
- passing explicit inputs rather than ambient mutable state;
- disabling TeX shell escape;
- validating asset paths against their question directory;
- avoiding evaluation of generated Sage source during reproduction;
- excluding environment variables from manifests and diagnostic dumps;
- bounding generation attempts and TeX passes; and
- supporting process timeouts with clear failures.

Network access is not required for a build once the Nix inputs are available locally. The CLI itself will not make network requests.

## 20. Migration from `mechanics`

The old `.q` files should be treated as source material and acceptance fixtures, not copied unchanged into the runtime architecture.

### 20.1 Migration mapping

| Earlier mechanics concept | MVP equivalent |
| --- | --- |
| `.q` file | question directory |
| `sagesilent` variables | `generate.sage` parameters and derived values |
| direct `randint` | `ctx.random` |
| `\sage{...}` | declared `\mpvalue`, `\mpparameter`, or `\mpderived` |
| `solution` environment | `solution.tex` selected by the profile |
| document `\input` list | publication TOML question list |
| job-name answer switch | separate projection-specific generated TeX |
| copied SageTeX output | one canonical instance JSON shared by projections |
| Makefile dependency scan | catalog and explicit schema dependencies |
| hard-coded Sage application | Nix-provided SageMath |
| adjacent auxiliary files | isolated edition build directory |

### 20.2 Required migration examples

1. **Ramp speed:** random numeric parameters, exact computation, decimal formatting, conservation-of-energy check.
2. **Car on a curve:** symbolic equations, substitutions, solved result, and an independent residual check.
3. **Projectile or snowball:** values shared by prose, solution, and a TikZ diagram.
4. **Fixed formula sheet question:** proves fixed questions do not require a generator.

For each example, the reviewed numerical answer and visual layout should match the intent of the earlier publication. Any discovered mathematical or unit correction must be documented rather than hidden as a migration difference.

## 21. Delivery plan

### Milestone 1: reproducible shell and fixed question

- Flake, CLI skeleton, project discovery, schemas.
- Default profile and one fixed question.
- Student and solution PDFs in an isolated build directory.
- Basic manifest and CI build.

### Milestone 2: deterministic Sage instances

- Generator runner, seed derivation, canonical values, display API.
- Constraints, checks, retry behavior, and instance JSON.
- Migrated ramp-speed question.
- Determinism and seed tests.

### Milestone 3: publications and projections

- Publication schema, sections, points, workspace, metadata.
- Student, answers, and solutions projections from shared instances.
- Multiple variants and manifest reproduction.
- Migrated car-curve question.

### Milestone 4: diagrams and quality gates

- Parameterized TikZ support and migrated diagram question.
- PDF structural checks, visual regression, enhanced diagnostics.
- Exhaustive/sample generator checking and corpus command.
- Documentation and reviewed example publication.

## 22. MVP acceptance criteria

The MVP is ready for use when all of the following are demonstrated in CI and on nix-darwin:

1. `nix develop` provides every required tool without global dependencies.
2. `nix flake check` builds and validates the representative corpus.
3. One command produces a professional student worksheet and matching worked-solution PDF.
4. An optional compact answer key is produced from the same instances.
5. Repeating a build with the same source, seed, variant, and toolchain yields identical instance JSON and equivalent PDF content.
6. Reordering questions does not change their instance hashes.
7. Building variants A and B gives independently derived, recorded instances.
8. A failed constraint is retried deterministically and reported if attempts are exhausted.
9. A failed mathematical check stops the build without retrying another random instance.
10. Student generated TeX contains no answer or solution fragments.
11. A manifest can reproduce an edition without executing question generators.
12. TeX failures identify the responsible question and authored fragment.
13. The corpus includes fixed, numeric, symbolic, and parameterized-diagram questions.
14. At least one finite generator domain is exhaustively checked.
15. Visual regression protects the default profile and migration examples.
16. Build intermediates do not pollute authored source directories.
17. No build step contains a machine-specific SageMath or TeX path.

## 23. Decisions requested in review

The following choices should be approved or changed before implementation:

1. **Source decomposition:** one directory with separate Sage, prompt, answer, and solution files rather than a single mixed `.q` file.
2. **Metadata format:** TOML for project, question, profile, and publication definitions.
3. **Computation boundary:** Sage runs before TeX and emits immutable canonical instances; the MVP does not use SageTeX.
4. **Rendering API:** small TeX lookup commands over preformatted declared values, with no expression evaluation in TeX.
5. **RNG:** versioned PCG64 with question-ID-based seed derivation.
6. **Retries:** constraints retry; failed checks stop immediately.
7. **Projection isolation:** separate generated documents rather than TeX conditionals that merely hide solutions.
8. **Default renderer:** LuaLaTeX, `latexmk`, and an `exam`-based profile.
9. **Runtime:** Python from the SageMath environment with each generator in a separate process.
10. **Reproduction:** stored instances are authoritative and generators are not rerun.
11. **Trust:** local generators and profiles are trusted code; hostile-code sandboxing is outside the MVP.
12. **Migration target:** representative compatibility with the mechanics corpus, not source compatibility with old `.q` files.

## 24. Summary

The MVP preserves what worked in the earlier mechanics project: modular questions, TeX-quality presentation, SageMath-powered variation, worked solutions beside their questions, and paired student and teacher publications.

Its key architectural change is to place an immutable, validated question instance between SageMath and TeX. That boundary gives mathpub deterministic editions, matching answer keys, independent tests, explicit constraints, meaningful provenance, cleaner builds, and a foundation that can grow without asking TeX or SageTeX to act as the entire publishing system.
