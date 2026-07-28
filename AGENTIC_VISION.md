# Agentic Authoring Vision

## Purpose

MathPub's normal authoring experience should not require an author to learn its CLI, component
schema, publication TOML, TeX build process, or Nix workflow. Those interfaces remain important
because they make the system reproducible and inspectable, but an authoring agent should operate
them on the author's behalf.

The author directs the work, makes pedagogical and editorial decisions, and reviews the rendered
PDFs. The agent plans and edits the structured source, operates MathPub, interprets failures, and
keeps the project valid.

The intended first instructions are therefore:

1. **Run the MathPub application.**
2. **Create or open your private authoring repository, start the agent, and ask it to outline your
   first book.**

Everything after that should be a conversation grounded in a continuously updated PDF preview.

This document describes that intended state. [AUTHOR_WORKFLOW.md](AUTHOR_WORKFLOW.md) documents the
commands required to accomplish the same work today.

## The central product idea

The terminal in the MathPub GUI is not present primarily so that Anna can type MathPub commands.
It is an agent runtime.

Anna may occasionally use the shell directly, but the expected session is:

- MathPub opens a terminal in the private authoring repository.
- Anna starts a supported CLI agent, initially the Antigravity CLI.
- The agent receives MathPub-specific instructions and skills.
- Anna asks for an outline, section, problem set, revision, or publication.
- The agent discovers and reuses existing components before creating new ones.
- The agent edits source, validates it, and builds the appropriate PDF.
- Anna evaluates the actual student, answer, solution, parent, and validation editions.
- Anna hovers or clicks rendered material and sends precise feedback back to the agent.
- The agent revises the mapped source and MathPub incrementally refreshes the preview.

This division of labor preserves a transparent, versioned source model without turning the author
into a build engineer.

## One authoring repository, many publications

The private repository should represent a body of work, not necessarily one book. Anna might choose
one repository for:

- all algebra publications;
- all physics publications;
- a complete K–12 curriculum;
- everything published under one imprint; or
- all of her authored mathematical content.

The correct boundary depends on privacy, collaboration, ownership, and reuse—not on the number of
PDFs. A single repository can contain many publication assemblies over a shared component catalog:

```text
anna-math-library/
├── components/
│   ├── concepts/
│   ├── examples/
│   ├── misconceptions/
│   ├── objectives/
│   ├── questions/
│   └── teaching-tips/
├── publications/
│   ├── algebra/
│   │   ├── algebra-1.toml
│   │   ├── algebra-1-practice.toml
│   │   └── algebra-2-readiness.toml
│   └── physics/
│       ├── introductory-physics.toml
│       └── mechanics-review.toml
├── profiles/
├── flake.nix
├── flake.lock
└── mathpub.toml
```

One reviewed component can appear in a textbook, workbook, cumulative quiz, parent guide, and
targeted practice sheet without being copied. Publications select and place shared components,
while seeds, variants, and placement identifiers preserve deterministic instances.

The GUI should call this an **authoring library** or **content library**, not a “book project.” A
book is one publication assembled from that library.

## The intended first-run journey

### 1. Launch MathPub

MathPub should be launchable as a normal desktop application. It should not require the author to
open a terminal in an engine checkout.

The welcome screen offers:

- **Create a private authoring library**
- **Open an existing authoring library**
- **Clone an existing private authoring library**

Recent libraries appear below those actions. Opening a library restores its last publication,
projection, page, and agent session when possible.

### 2. Create the private repository

The creation flow asks only for information that changes the result:

- library name;
- local folder;
- intended scope, such as “all algebra publications” or “all my publications”;
- private Git host and owner, if a remote should be created now; and
- whether to start with Antigravity or another configured agent.

MathPub then performs the current bootstrap operations:

1. creates a content-only MathPub project;
2. pins MathPub and Nixpkgs in `flake.lock`;
3. initializes a new Git history with no public-engine ancestry;
4. creates a private remote when requested;
5. verifies that the remote actually reports private visibility;
6. creates and commits the initial project instructions; and
7. opens the new library in the workspace.

Remote creation is optional so that authors can work locally or use a Git provider MathPub does not
yet integrate with. “Private” must be the safe default, and MathPub must never infer that manuscript
content is suitable for a public repository.

### 3. Start the agent

The terminal pane should have a prominent action such as:

> **Start Antigravity**

Pressing it launches the configured CLI in the repository root with:

- the repository's Nix environment available;
- the repository's `AGENTS.md` instructions;
- the MathPub version-matched skill bundle;
- the current publication, projection, page, seed, and variant as session context; and
- a concise startup prompt explaining that the author works primarily by reviewing PDFs.

The agent program must remain replaceable. Antigravity is the first polished integration, not a
hard-coded protocol. The launcher should eventually support other CLI agents through named,
user-configurable commands and small provider adapters.

If the CLI is missing or unauthenticated, the GUI explains the exact problem and offers a supported
installation or sign-in path. It must not leave Anna at an unexplained shell prompt.

### 4. Give the first authorial instruction

The empty-library screen should offer a useful example:

> Outline an Algebra 1 book for students learning independently with help from a tutor or
> homeschool parent. Show me the proposed units, dependencies, and publication plan before writing
> the first section.

The agent should ask only the questions that materially affect the book: audience, assumed
prerequisites, scope, sequence, tone, assessment expectations, and desired editions. It then
proposes a curriculum and waits for the author's direction before producing a large body of
content.

The author should not need to say “create a concept component,” “edit `publicationPaths`,” or “run
the 20-seed component check.” Those are agent responsibilities.

### 5. Produce the first reviewable slice

After the outline is accepted, the agent creates a thin vertical slice:

- the publication assembly;
- the first concept and lesson;
- objectives and exposition;
- a guided example;
- a useful initial problem set;
- short answers and explained solutions;
- parent or tutor guidance where requested; and
- validation notes and deterministic checks.

The agent validates the slice, builds it, and tells the GUI which PDF to select. As soon as the PDF
exists, the right pane changes from onboarding to the rendered preview. A new author should never
have to know that an initial build is currently required before the preview has something to show.

### 6. Review the PDF, not an implementation

Anna reads the output as a student or teacher would. When she hovers over mapped content, MathPub
shows the relevant region. When she clicks it, she can write feedback such as:

> This explanation introduces negative coefficients too early. Keep the example positive and add
> a sentence connecting the balance model to the inverse operation.

MathPub sends the agent a structured payload containing:

- Anna's comment;
- publication, projection, page, seed, and variant;
- component identifier and kind;
- fragment name;
- authored source path;
- placement and lesson context; and
- the mapped generated-source range.

The agent confirms its interpretation when necessary, edits the authored component rather than
generated TeX, runs the relevant checks, and triggers an incremental rebuild. The preview remains
on the same page and reports when the revision is ready.

### 7. Grow a reusable library

For every new request, the agent searches the catalog before creating content:

> Make a readiness quiz for the Algebra 2 book using the skills students should remember from
> Algebra 1.

The agent should identify reviewed Algebra 1 components that can be reused directly, components
that need publication-specific placement overrides, and genuine gaps that need new source. It
should present meaningful reuse decisions to Anna without forcing her to inspect component paths.

Over time, the repository becomes more valuable because later publications draw on an expanding
reviewed library instead of starting from blank pages.

## Division of responsibility

### The author

The author owns:

- audience, scope, sequence, and pedagogical intent;
- the standard of explanation and practice;
- acceptance or rejection of an outline;
- editorial and visual review of every intended edition;
- decisions about reuse when context changes meaning;
- approval to commit, push, share, or release content; and
- the final claim that a publication is ready.

### The agent

The agent owns:

- translating authorial intent into MathPub source;
- inspecting the catalog and proposing reuse;
- planning stable identifiers, placements, and publication structure;
- maintaining projection isolation;
- writing and revising components and generators;
- operating the CLI and Nix-provided tools;
- running proportionate deterministic, mathematical, publication, and build checks;
- interpreting errors in author-facing language;
- keeping generated files out of source control; and
- reporting exactly which PDF, seed, variant, and checks are ready for review.

The agent may propose commits or releases, but it should not silently publish manuscript content.

### MathPub

MathPub owns:

- deterministic generation and projection-safe rendering;
- schema validation and source-to-PDF traceability;
- reproducible environments and manifests;
- fast, reliable incremental previews;
- routing visual feedback to the correct authored source;
- safe repository and agent bootstrapping;
- clear status for builds, agents, Git, and remotes; and
- making failures actionable to the agent and legible to the author.

The GUI should automate mechanics, not hide provenance or weaken validation.

## The agent contract

Every supported agent session needs a versioned operating contract.

### Repository instructions

`mathpub init` already generates `AGENTS.md`, but the agentic workflow requires it to explain more
than command syntax. It should tell the agent:

- this repository is a reusable authoring library containing many publications;
- the PDF is the primary human review surface;
- catalog discovery precedes component creation;
- generated output is disposable;
- private source must not be copied into the public engine repository;
- author approval is required for consequential Git and publication actions; and
- feedback arriving from the GUI includes trusted source-map context.

### Versioned skills

Private content repositories do not currently receive the authoring skills that exist in the
MathPub engine checkout. The launched agent needs a MathPub-version-matched bundle covering:

- authoring-library bootstrap and maintenance;
- curriculum planning and dependency audits;
- section authoring;
- problem-set authoring;
- self-assessment and unit-practice authoring;
- publication assembly and component reuse;
- generators, diagrams, and mathematical validation;
- PDF review and source-mapped revision;
- multi-publication consistency checks; and
- release and reproduction workflows.

The current curriculum, section, problem-set, self-assessment, and unit-practice skills are a
foundation. They need a supported distribution mechanism for private repositories and adapters for
each agent CLI. The skills must remain versioned with the MathPub schema and command set so that an
agent never follows instructions from a different engine revision.

### A predictable operating loop

Unless Anna requests otherwise, an agent should:

1. inspect the current project, catalog, publication, and working tree;
2. clarify the authorial goal and propose a bounded change;
3. search for reviewed components that already satisfy the need;
4. create or edit authored source, never generated files;
5. run focused checks with explicit seeds;
6. build the smallest useful review projection;
7. direct the GUI to the resulting PDF and relevant page;
8. summarize what changed and what still requires human review; and
9. run the complete publication loop before proposing a commit or release.

This loop should be encoded in instructions and skills rather than relying on every provider model
to infer it.

## GUI capabilities implied by this vision

The agentic experience requires more than the existing split pane:

### Library and repository controls

- Create, open, clone, and switch authoring libraries.
- Initialize local Git and optionally create a verified private remote.
- Show repository scope, current branch, dirty state, remote visibility, and synchronization state.
- List many publications and projections in one library.
- Add publications to flake checks without hand-editing `flake.nix`.

### Agent controls

- Start, stop, restart, and resume Antigravity from a clear GUI action.
- Configure alternative CLI agents without rebuilding MathPub.
- Detect installation, authentication, and startup failures.
- Show whether feedback will be inserted into a shell or a recognized live agent.
- Preserve ordinary terminal access for expert use.
- Display the active agent, working directory, and granted permissions.

### Author-facing controls

- Offer starter prompts appropriate to an empty library or selected publication.
- Automatically select the first successful preview.
- Navigate publication, variant, projection, lesson, and page without filesystem knowledge.
- Route PDF feedback with structured source context.
- Show concise validation and rebuild status.
- Make full-review and release readiness visible without requiring log inspection.

### Agent-facing interfaces

The agent can continue using the CLI, but machine-readable commands should eventually cover:

- creating publications, concepts, chapters, and lessons;
- searching and comparing reusable components;
- registering publications with project checks;
- selecting the active GUI preview;
- reporting validation summaries and human-review boundaries;
- requesting incremental versus full builds; and
- preparing a review or release candidate.

Structured JSON should be the stable agent interface. The GUI and agent should not coordinate by
scraping prose from terminal output.

## Privacy, agency, and trust

A private Git remote does not by itself make an agent session private. The selected CLI may send
prompts, source fragments, PDFs, or other context to its model provider. Before first launch,
MathPub must clearly identify the selected agent, link to its data-handling controls, and explain
what project material may leave the machine.

Additional safeguards should include:

- private remote creation by default;
- explicit confirmation before public visibility, push, release, or destructive Git operations;
- no automatic upload of generated PDFs or build logs;
- credentials owned by the selected CLI or Git provider, not stored in manuscript source;
- visible agent permissions and working directory;
- source-mapped feedback treated as context, not permission for unrelated changes;
- reviewable diffs for agent edits;
- reproducible manifests for every candidate edition; and
- a clear distinction between computational evidence and human editorial approval.

The goal is not unattended autonomous publishing. It is high-leverage collaboration with an author
who remains accountable and in control.

## What success looks like

The intended experience is achieved when Anna can:

1. launch MathPub without opening a separate terminal;
2. create and verify a private authoring library from the welcome screen;
3. press **Start Antigravity** and receive a ready agent in that library;
4. say “outline my first book” in ordinary authorial language;
5. approve the outline and receive a correctly separated, reviewable first PDF without issuing a
   MathPub command;
6. click a paragraph or problem in the PDF, describe the desired revision, and see the correct
   source updated and rebuilt;
7. request a second publication and have the agent reuse appropriate reviewed components from the
   first;
8. understand which checks passed and which judgments still require her review; and
9. approve commits, pushes, and releases without managing generated files or build machinery.

An expert should still be able to inspect every TOML file, TeX fragment, generator, command, check,
and manifest. The beginner should not need to manipulate them to make progress.

## Current foundation and missing pieces

Several foundations already exist:

- a native GUI with an embedded PTY terminal;
- project-independent startup and local private authoring-library creation;
- validated existing-library opening, a persistent recent-library list, and automatic restoration
  of the most recently used valid library;
- a configurable one-click agent launcher with executable detection;
- agent launch through the library's locked Nix environment, including core repository tools and
  a documented extension point;
- a first-book starter prompt and generated agent operating instructions;
- deterministic PDF builds and multiple projections;
- first-class mapped Beamer/Metropolis presentations alongside tests, worksheets, and textbooks;
- autonomous default Antigravity startup with an explicit instruction to load the repository's
  MathPub operating contract;
- SyncTeX hover regions and source-map resolution;
- feedback injection into the terminal without automatic execution;
- active-preview watching and incremental rebuilds;
- content-only repository initialization and pinned flakes;
- component discovery, scaffolding, checking, and publication builds; and
- initial MathPub curriculum and authoring skills.

The major missing pieces are:

1. clone and richer authoring-library chooser flows;
2. private-remote creation and visibility verification after local library creation;
3. Antigravity authentication guidance, provider adapters, and resumable session state;
4. versioned delivery of MathPub instructions and skills into private repositories;
5. agent-oriented commands for publications, concepts, lessons, reuse, and GUI preview selection;
6. automatic first-build and empty-library onboarding;
7. multi-publication catalog and reuse workflows;
8. author-facing review, approval, and release status; and
9. explicit privacy and permission UX for model providers and Git remotes.

These are not peripheral conveniences. Together they turn the existing publishing engine and
agent-capable workspace into the authoring product MathPub is intended to be.

## Non-goals

This vision does not require MathPub to:

- replace structured source with an opaque chat transcript;
- hard-code one model provider forever;
- become a general-purpose IDE;
- make the agent the final authority on pedagogy or correctness;
- put every book in a separate repository;
- publish or push content without author approval; or
- hide the commands, source, evidence, and provenance from expert users.

The durable source and reproducible build remain the product's foundation. The agent makes that
foundation accessible; it does not replace it.
