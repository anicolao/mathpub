# Starting a Book with MathPub

This guide describes the current, working command-line path for an author such as Anna to start a
private authoring library, write its first book lesson, review the result in MathPub, and produce
student and instructor PDFs. The same repository may eventually contain many related publications
that reuse its component catalog. This guide also identifies places where the engine still exposes
implementation details that should become author-facing product features.

MathPub currently assumes that the author is comfortable working with files and running commands,
or is working alongside someone or an authoring agent that can do so. It is not yet a
click-through book editor.

The intended product experience is agent-first: the GUI creates or opens the private repository,
launches an authoring agent in its terminal, and lets the author work mainly by directing that
agent and reviewing source-mapped PDF previews. See [AGENTIC_VISION.md](AGENTIC_VISION.md).

## The working model

A MathPub book has three layers:

1. **Components** are reusable pieces of reviewed source: concepts, objectives, examples,
   questions, misconceptions, teaching tips, and other lesson material.
2. **A publication file** arranges those components into chapters, lessons, and problem sets, and
   chooses which editions to produce.
3. **Generated editions** contain the PDFs, deterministic question instances, SyncTeX maps, build
   logs, and a reproduction manifest. Everything under `build/` is disposable output and should
   never be edited.

Student prompts, short answers, and worked solutions remain in separate source files. MathPub uses
those boundaries to prevent answers from leaking into student editions.

## 1. Install the prerequisites

The author needs:

- Nix with flakes enabled;
- Git; and
- access to the private Git host where the manuscript will live.

Python, SageMath, TeX, fonts, and MathPub itself come from the pinned Nix flake. Do not install or
run separate host versions of those tools.

> **Gap:** MathPub does not yet provide a normal desktop installer or a first-run check for Nix and
> Git. Installing Nix and configuring its binary cache are currently onboarding steps outside the
> application.

## 2. Create a private authoring library

Manuscripts should not be developed on a branch of the public MathPub engine repository. Create a
content-only project with its own Git history. The example begins with one Algebra 1 book, but its
component catalog can support additional algebra, physics, or other publications later:

```console
nix run github:anicolao/mathpub#mathpub -- init anna-algebra-1 \
  --mathpub-url github:anicolao/mathpub \
  --publication publications/book.toml
cd anna-algebra-1
nix flake lock
nix develop
```

The first command creates `mathpub.toml`, `flake.nix`, `AGENTS.md`, `.gitignore`, and empty
`components/`, `publications/`, and `profiles/` directories. `flake.lock` then pins the exact
MathPub and Nixpkgs revisions used by the book.

The `--publication` option registers the future book with `nix flake check`. Do not run that check
until `publications/book.toml` exists. Additional publication files must be added to
`publicationPaths` in `flake.nix`.

Initialize a private history after inspecting the generated files:

```console
git init -b main
git add AGENTS.md README.md .gitignore flake.nix flake.lock mathpub.toml \
  components publications profiles
git status --short
git commit -m "Initialize MathPub book"
```

See [PRIVATE_PUBLICATIONS.md](PRIVATE_PUBLICATIONS.md) for creating a private GitHub repository and
checking its visibility before inviting collaborators.

> **Gap:** `mathpub init` creates an empty project, not a usable first book. There is no **New
> Book** action in the desktop application, and no `mathpub new publication` command. Passing
> `--publication` registers a path but does not create that file.

## 3. Plan stable identifiers

Choose identifiers that describe the mathematics rather than a page number or current chapter
position. For example:

- concept: `algebra.variables`
- objective: `algebra.variables.objective`
- example: `algebra.variables.example`
- question: `algebra.variables.identify`
- lesson: `variables`

Components can then move between lessons or books without being renamed. A component's
`placement` identifies one use inside a publication; it must be unique even when the same question
appears more than once.

> **Gap:** There is no guided curriculum, chapter, or identifier planner. Authors currently design
> this structure in TOML, with schema errors as the main feedback.

## 4. Create the first concept

A component-based textbook lesson must name at least one concept. Create these two files in
`components/concepts/algebra/variables/`.

`component.toml`:

```toml
schema = 1
id = "algebra.variables"
kind = "concept"
title = "Variables"
status = "draft"

[fragments]
summary = "summary.tex"

[fragment_modes]
summary = "mixed-tex"
```

`summary.tex`:

```tex
A variable is a symbol that represents a number. Its value may be unknown or may change.
```

Then confirm that MathPub can discover it:

```console
nix run .#mathpub -- show component algebra.variables --json
```

> **Gap:** The schema supports concepts, exposition, definitions, transitions, figures, and other
> textbook material, but the scaffolding command currently supports only objectives,
> misconceptions, teaching tips, examples, and questions. Even the required concept above must be
> created manually.

## 5. Scaffold and write lesson components

Create a small vertical slice before writing an entire unit:

```console
nix run .#mathpub -- new component algebra.variables.objective \
  --kind objective --concept algebra.variables \
  --title "What You Will Learn"
nix run .#mathpub -- new component algebra.variables.example \
  --kind example --concept algebra.variables --form cohesive \
  --title "Naming an Unknown"
nix run .#mathpub -- new question algebra.variables.identify \
  --concept algebra.variables --template fixed \
  --title "Identify the Variable"
```

Each command creates a directory beneath `components/` with metadata and editable TeX fragments.
Replace the scaffold text with the real lesson material. For a fixed question, edit:

- `prompt.tex` for exactly what the student sees;
- `answer.tex` for the short answer; and
- `solution.tex` for a complete explanation.

Use `--template numeric`, `symbolic`, or `tikz` when a question should generate deterministic
variants. Those templates also create `generate.sage`. Keep exact values in `ctx.parameter` and
`ctx.derived`, presentation in `ctx.display.*`, suitability constraints in `ctx.require`, and
mathematical evidence in `ctx.check_*`. Give every important check a plain-language
`ctx.validation_note`.

Inspect nearby work instead of guessing at the component structure:

```console
nix run .#mathpub -- list components --json
nix run .#mathpub -- show component algebra.variables.example --json
```

The generated metadata starts with `status = "draft"`. Change it to `reviewed` only after the
mathematics, pedagogy, wording, answer, and solution have actually been reviewed.

> **Gap:** Scaffolds contain placeholder prose, but the GUI does not yet launch a MathPub-skilled
> authoring agent to replace it on the author's behalf. There is also no review checklist or
> workflow enforcing the transition from `draft` to `reviewed`. A direct source editor may remain
> useful for experts, but it is not required for the intended PDF-centered agent workflow.

## 6. Assemble the first lesson

Create `publications/book.toml`:

```toml
schema = 1
id = "anna.algebra-1"
kind = "textbook"
title = "Algebra 1"
subtitle = "A Clear and Practical Course"
author = "Anna"
profile = "mathpub.exam"
paper = "letter"
style = "anna"
projections = ["student", "answers", "solutions", "validation", "parent"]

[[component_chapters]]
id = "foundations"
title = "Foundations"

[[component_chapters.lessons]]
id = "variables"
number = "1"
title = "Variables"
concepts = ["algebra.variables"]

[[component_chapters.lessons.blocks]]
derive = "concept-summary"
title = "Lesson Summary"

[[component_chapters.lessons.blocks]]
include = "algebra.variables.objective"
placement = "foundations.variables.objective"

[[component_chapters.lessons.blocks]]
heading = "Guided Example"

[[component_chapters.lessons.blocks]]
include = "algebra.variables.example"
placement = "foundations.variables.example"

[[component_chapters.lessons.blocks]]
[component_chapters.lessons.blocks.problem_set]
id = "variables-practice"
title = "Practice"
directions = "Answer each question and explain how you know."

[[component_chapters.lessons.blocks.problem_set.questions]]
id = "algebra.variables.identify"
placement = "foundations.variables.question-1"
```

This asks MathPub to produce:

- a student book without answers;
- a compact answer edition;
- a worked-solutions edition;
- a validation edition containing mathematical evidence; and
- a parent edition that can include tutor or homeschool-parent guidance.

Validate the assembly before rendering it:

```console
nix run .#mathpub -- check publication publications/book.toml --json
```

> **Gap:** Authors must currently hand-author a deeply nested publication TOML file and unique
> placement strings. There is no book-outline editor, publication scaffold, automatic placement
> generation, schema-aware completion, or checked-in starter textbook on current `main`.

## 7. Validate and preview one question

Use a fixed review seed so that everyone sees the same material:

```console
nix run .#mathpub -- check component algebra.variables.identify --seeds 20 --json
nix run .#mathpub -- preview algebra.variables.identify \
  --seed 2026 --replace --json
```

The check confirms deterministic generation and evaluates recorded checks across the requested
seeds. The preview renders the question in student, answer, solution, and validation projections
beneath `build/preview.algebra.variables.identify/preview/`.

Use `--exhaustive` instead of `--seeds 20` only when a generator declares a finite exhaustive
domain.

> **Gap:** Preview operates on one question, not a general component or an entire lesson. There is
> no single command that reviews every generated question in a book across a chosen seed policy.

## 8. Build the book

Build every requested edition:

```console
nix run .#mathpub -- build publications/book.toml \
  --seed 2026 --variant review --replace --json
```

The PDFs and manifest will be under:

```text
build/anna.algebra-1/review/
```

Open every PDF, not only the student edition. In particular:

- confirm that answers and solutions do not appear in the student book;
- check page breaks, diagrams, workspace, and instructions;
- read the parent edition as its intended audience;
- inspect validation notes and failed or weak checks; and
- retain the explicit seed and variant in review reports.

The manifest records source identities, question instances, checks, toolchain versions, output
hashes, and the information needed to reproduce the edition.

> **Gap:** A successful build proves that the source validates and TeX renders; it does not replace
> editorial, accessibility, curriculum, or print review. MathPub does not yet provide a release
> checklist, approval record, print-preflight report, or a supported way to promote a reviewed PDF
> from disposable `build/` output into a release.

## 9. Work in the MathPub application

The application needs an existing built PDF to display, so perform the first build before
launching it from the book repository:

```console
nix run .#mathpub-gui
```

The workspace combines a terminal with a PDF preview. Select the built projection to watch it.
When a component changes, MathPub incrementally rebuilds the active projection and keeps the
visible page selected. Hovering mapped PDF content shows its source region; clicking it can send
focused feedback into the terminal.

Use **Open library** to switch to an existing MathPub repository by its absolute folder path.
Successfully created or opened libraries appear in the recent-library list, and MathPub restores
the most recently used valid library when the application is restarted outside another project.

Use **Import reference** to select source material such as notes, outlines, datasets, or PDFs.
MathPub copies and commits the file as `reference/<filename>` in the active library. You can then
refer to it naturally in an agent prompt—for example, “Use `reference/course-outline.pdf` to plan
the units for this book.” The agent's environment includes `pdftotext` for reading imported PDFs.

For a faster explicit one-lesson build:

```console
nix run .#mathpub -- dump-format \
  --style anna --font computer-modern --paper letter --json
nix run .#mathpub -- build publications/book.toml \
  --seed 2026 --variant review --projection student \
  --lesson variables --incremental --replace --json
```

The browser-hosted fallback is:

```console
nix run .#mathpub-workspace
```

> **Gap:** The terminal is still a general shell: MathPub does not yet provide a one-click agent
> launcher, agent authentication guidance, or version-matched authoring skills. The author must
> already know which agent command to run. A new empty project also has no welcome screen explaining
> that a first build is required before a PDF can be selected.

## 10. Run the complete review loop

After changing a generated question:

```console
nix run .#mathpub -- check component QUESTION_ID --seeds 20 --json
nix run .#mathpub -- preview QUESTION_ID --seed 2026 --replace --json
nix run .#mathpub -- check publication publications/book.toml --json
nix run .#mathpub -- build publications/book.toml \
  --seed 2026 --variant review --replace --json
nix flake check
```

For fixed questions and other components, run the applicable component check and then the
publication check and build. `nix flake check` validates the content repository and every
publication registered in `publicationPaths`; the explicit build remains necessary to compile and
review all PDFs.

Commit reviewed source and the lock file, but not generated output:

```console
git status --short
git add components publications flake.nix flake.lock mathpub.toml
git commit -m "Add the variables lesson"
git push
```

To confirm that an edition can be reconstructed from its stored instances:

```console
nix run .#mathpub -- reproduce \
  build/anna.algebra-1/review/manifest.json --replace --json
```

## 11. Create variants and update deliberately

Build several deterministic forms of the same generated material:

```console
nix run .#mathpub -- variants publications/book.toml \
  --seed 2026 --count 3 --replace --json
```

The seed, variant, placement, and generator source together determine the generated instance.
Record them when reporting a problem.

The book remains on the MathPub revision in `flake.lock` until the author deliberately updates it:

```console
nix flake update mathpub
nix flake check
nix run .#mathpub -- build publications/book.toml \
  --seed 2026 --variant review --replace --json
```

Review output changes before committing the updated lock file.

## Highest-priority author usability gaps

The current workflow is technically complete, but not yet self-service for a typical author. The
highest-leverage improvements are:

1. Extend the local create/open/recent-library flow with clone support and optional private-remote
   creation and visibility verification.
2. Extend the new one-click **Start Antigravity** launcher with authentication guidance, resumable
   sessions, provider adapters, and version-matched MathPub skills.
3. Add agent-facing `new publication`, `new concept`, and `new lesson` commands, with complete
   component-based templates and generated placement IDs.
4. Extend the initial empty-library onboarding and starter prompt with a multi-publication browser
   and an automatic first preview.
5. Add book-level review tooling: seed policies, draft/reviewed enforcement, accessibility checks,
   print preflight, approvals, and release artifacts.
6. Provide a supported desktop installation and cache health check so authors do not have to
   understand Nix installation or diagnose source builds.

Until those gaps are filled, MathPub is best described as a reproducible publishing engine with a
powerful interactive preview, operated through files and commands—not yet a complete author-facing
book application.
