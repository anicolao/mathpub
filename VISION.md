# Vision for mathpub

## The problem

Mathematical publishing is too often split across disconnected tools and duplicated documents. An author writes a worksheet, copies it to make an answer key, pastes examples into slides, runs calculations in a separate notebook, and manually checks that every variant still makes sense. The typography may be excellent while the computation is irreproducible; the algebra may be checked while the surrounding theorem is misstated; the source may build only on one laptop.

For generated exercises, the risk compounds. A random choice can introduce division by zero, an unintended repeated root, an ugly coefficient, multiple valid answers, or a diagram that no longer matches the text. A correct solution template is not enough: every admitted parameter combination must respect the mathematical and pedagogical constraints.

mathpub aims to make correctness, variation, reuse, and professional presentation parts of one publishing workflow.

## The north star

An author writes a mathematical idea once, states what must be true, and chooses how it should appear. mathpub produces the requested publications and an auditable account of why their mathematical content is trusted.

The ideal build has five properties:

- **Beautiful:** it meets the typographic standard expected of serious mathematical publishing.
- **Correct:** claims and calculations carry explicit, appropriately strong evidence.
- **Generative:** exercises can vary without separating questions from their solutions.
- **Reproducible:** a revision, configuration, and seed identify the content exactly.
- **Adaptable:** shared material can become a worksheet, workbook, slide deck, textbook, article, or accessible derivative.

## A layered authoring model

TeX will be the author-facing language for mathematical prose and layout, but TeX should not have to serve simultaneously as database, random-number generator, theorem prover, and build system. mathpub will separate concerns while keeping ordinary TeX comfortable to write.

### 1. Mathematical content

Content includes definitions, claims, proofs, examples, exercises, hints, solutions, learning objectives, prerequisites, and references. Stable identifiers connect these objects so that a theorem can be reused in an article and a textbook chapter without copying it.

### 2. Parameters and computation

SageMath generators produce typed parameter records from explicit domains. Each generator also defines validity predicates, derived values, canonical answers, alternative acceptable forms, and explanations. Seeds belong to the build manifest rather than hidden global state.

Generation should resemble constrained search:

1. derive a deterministic random stream from the document, item, variant, and seed;
2. propose parameters;
3. evaluate mathematical and pedagogical predicates;
4. reject unsuitable cases with a recorded reason; and
5. emit a complete, immutable instance consumed by both question and solution renderers.

This design prevents the question and answer key from drifting apart.

### 3. Evidence and verification

mathpub will describe what kind of evidence supports each check instead of presenting all green checkmarks as equivalent.

- **Formal proof:** a proof assistant kernel checks a theorem derived from shared definitions.
- **Exhaustive verification:** all values in a declared finite domain are checked.
- **Symbolic verification:** SageMath establishes an identity or condition under recorded assumptions.
- **Property testing:** many deterministic samples exercise a stated invariant.
- **Example checking:** a particular generated instance is independently recomputed.
- **Human review:** prose, pedagogy, diagrams, and claims outside the formal boundary are explicitly marked for review.

Formalization will be incremental. Requiring every sentence in an introductory workbook to be formalized would make the system impractical; calling a symbolic simplification a proof would make it untrustworthy. The useful middle is a visible assurance case with no hidden category errors.

### 4. Presentation

Publication profiles select content and layout without changing its mathematical identity. Profiles can control paper size, typography, color, solution visibility, pacing, slide overlays, space for student work, and accessibility metadata.

TeX classes and packages remain available for expert control. mathpub will provide strong defaults, not a lowest-common-denominator renderer.

### 5. Build and provenance

Nix pins the executable toolchain. A build manifest records at least:

- the source revision and dirty-tree state;
- the flake lock and mathpub version;
- the publication profile and audience;
- generator seeds and accepted parameter records;
- proof and computation artifact hashes;
- fonts and relevant rendering configuration; and
- validation outcomes.

Artifacts should be rebuildable from this information and traceable back to their sources.

## Trust boundaries

Professional appearance must never be mistaken for mathematical assurance. The system will make its trusted components and limitations legible.

A likely early trust base includes the Nix-resolved toolchain, TeX engine, SageMath runtime, mathpub orchestration code, and—where formal proofs are used—the proof assistant's kernel and translation layer. Generated TeX is an output to inspect, not an independent verifier. PDF regression tests can detect visual changes, but cannot establish that a theorem is true.

When mathematics crosses representations—for example, from a Sage polynomial to a proof-assistant expression and then to TeX—the conversion must be tested, versioned, and visible in provenance. Prefer small, reviewable interchange formats over evaluating generated source code.

## Publication families

The first useful system should support a coherent family rather than six unrelated exporters.

- **Worksheets:** selected exercises, stable variants, work space, compact teacher keys.
- **Workbooks:** sequenced units, recurring structures, cumulative review, full solutions.
- **Slideshows:** progressive disclosure, presenter notes, examples shared with handouts.
- **Textbooks:** chapters, theorem-like environments, cross-references, indexes, bibliographies.
- **Articles:** conventional TeX workflows, journal profiles, reproducible computational appendices.

Each format may require specialized layout, but shared content identifiers, generated instances, computations, and evidence should remain the same.

## Quality bar

A release-quality publication should pass four gates:

1. **Content validation:** references resolve, required fields exist, variants are deterministic, and audience rules do not leak solutions.
2. **Mathematical validation:** declared checks and proof obligations succeed with assumptions recorded.
3. **Rendering validation:** TeX reports no unexpected errors or serious warnings; pages pass structural and visual regression checks.
4. **Editorial validation:** a human reviews pedagogy, language, accessibility, and final visual output.

Failures should point to the content object and originating source, not merely to a line in generated TeX.

## Roadmap

### Phase 0: reproducible foundation

- Create the flake and pinned development shell for nix-darwin and Linux.
- Select the minimal TeX Live, SageMath, font, and test dependencies.
- Establish licensing, contribution conventions, fixtures, and continuous integration.
- Define a deterministic build manifest and a small example corpus.

### Phase 1: trustworthy worksheets

- Build a CLI that validates, instantiates, and renders a document.
- Support TeX content with structured exercises, hints, and solutions.
- Generate paired student and teacher PDFs from one immutable parameter record.
- Add deterministic seeds, constraint checking, SageMath validation, and provenance.
- Test representative PDFs structurally and visually.

### Phase 2: reusable books and slides

- Add stable content identifiers, collections, prerequisites, and cross-references.
- Introduce workbook, textbook, article, and slideshow profiles.
- Support shared examples across slides, notes, handouts, and long-form text.
- Add bibliography, index, glossary, and accessibility workflows.

### Phase 3: proof-backed content

- Choose a proof assistant based on library coverage, kernel trust, Nix support, and author experience.
- Define a narrow, typed interchange boundary for selected mathematical objects.
- Link proof artifacts to source claims and make their status visible in manifests.
- Demonstrate end-to-end formally checked units without requiring universal formalization.

### Phase 4: publishing ecosystem

- Offer documented extension points for publication profiles, generators, validators, and proof backends.
- Build reusable, reviewed libraries of templates and mathematical content.
- Support institutional style packs and large multi-author projects.
- Explore accessible HTML or other derivatives while preserving TeX as a first-class source.

## Non-goals

At least initially, mathpub will not:

- replace TeX with a proprietary visual editor;
- claim that SageMath output is automatically a formal proof;
- hide randomness or silently repair invalid generated questions;
- guarantee correctness of unformalized prose;
- make arbitrary TeX fully convertible to every output medium; or
- trade reproducibility for a globally mutable package environment.

## Measures of success

The project is succeeding when:

- an author changes a generator once and cannot accidentally leave its answer key stale;
- another machine can reproduce a named edition from its revision and seed;
- readers can distinguish formally proved, symbolically checked, tested, and human-reviewed material;
- a shared example renders naturally in a worksheet, slides, and a chapter;
- build failures explain the mathematical object and violated invariant;
- generated variants are demonstrably valid across their promised domains; and
- the final PDFs look intentionally designed rather than mechanically exported.

## Guiding idea

mathpub is not only a document generator. It is an executable, auditable publishing practice for mathematics: source, computation, proof, presentation, and provenance working together.
