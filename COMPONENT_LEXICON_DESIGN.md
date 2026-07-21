# mathpub component lexicon design

## 1. Purpose

mathpub publications should be assembled from reusable, independently inspectable components.
A textbook is not a large TeX document with a second publishing path: it is an ordered assembly of
the same generated, validated mathematical objects that can also appear in worksheets, tests,
slides, articles, and workbooks.

This document defines the proposed lexicon of those objects, their relationships, and the boundary
between authored source, generated instances, placement, and presentation.

The design extends the existing question-instance model. It does not replace deterministic
generation, projection isolation, or manifest provenance with a looser document abstraction.

## 2. Design axioms

### 2.1 One mathematical object, many uses

A definition, example, question, or theorem has one stable identity. Publications include it by
identifier. Reuse must not require copying its TeX or its answer.

### 2.2 Generate once, project many times

Every parameterized component produces one immutable instance. Student text, short answers,
worked solutions, validation material, slides, and parent notes consume that same instance.

### 2.3 Prose and computation have different responsibilities

TeX expresses reader-facing language and notation. SageMath selects parameters, derives values,
checks relationships, and formats declared display values. A calculated value must not be copied
independently into prose, an example, an answer, and a solution.

### 2.4 Concepts are semantic hubs

A concept records what a student should understand and remember. Definitions, notation, examples,
misconceptions, teaching tips, questions, and objectives relate to concepts. A section or chapter
summary gathers the summary facets of the concepts it contains; it does not maintain a second,
manually synchronized account of those ideas.

### 2.5 Collections contain placements, not copied content

A problem set contains ordered question placements. A lesson contains ordered component
placements. A chapter contains lessons and derived collections. The component remains reusable;
the placement supplies local role, instance policy, audience, and layout.

### 2.6 Evidence keeps its strength

Formal proof, exhaustive verification, symbolic checking, numerical checking, property testing,
and human review remain distinct. Every mathematical claim or generated instance reports the
evidence that actually supports it.

### 2.7 Reader-facing text contains no build commentary

Publication content addresses the student or an explicitly named adult reader. Generator details,
source identities, checks, and review boundaries belong in manifests and validation projections,
not in the student narrative.

## 3. Four layers of identity

The framework must not conflate these four objects.

### 3.1 Component definition

Reviewed source with a stable ID, kind, relationships, generator or proof references, and rendering
fragments. Examples:

- `algebra.order-operations.left-to-right`
- `algebra.distribution.negative-factor.example`
- `algebra.distribution.first-term-only-error`
- `algebra.distribution.practice.negative-binomial`

### 3.2 Component instance

An immutable accepted result of instantiating a component for a seed and variant. It contains
canonical parameters, derived values, display values, checks, evidence, and a content hash.

Static components also receive an instance record. Their record identifies reviewed source and
declares that no generator ran; “static” must not mean “absent from provenance.”

### 3.3 Placement

One occurrence of a component in an assembly. A placement has its own stable ID and may declare:

- role: motivation, definition, guided example, practice, review, assessment, or reference;
- instance policy: shared, fresh, original, or explicitly pinned;
- audience and projection policy;
- points, numbering, workspace, caption, and layout hints; and
- local cross-reference label.

The same component may be placed in a lesson, a slide deck, and a review worksheet without changing
its mathematical identity.

### 3.4 Rendered projection

The student, answer, solution, validation, parent, presenter, or other view of placed instances.
Rendering cannot rerun generators or change canonical mathematics.

## 4. Component taxonomy

The lexicon has semantic components, reader-visible atomic components, mathematical claims,
instructional components, and composite assemblies.

### 4.1 Semantic components

#### Concept

A concept is the central organizing object for an idea such as “like terms,” “slope,” or “the
zero-product property.” It is primarily semantic, although its summary facets can be rendered.

Required data:

- stable ID and student-facing title;
- plain-language meaning;
- notation and vocabulary IDs;
- prerequisite and successor concept IDs;
- observable learning objectives;
- a concise `summary` facet written to the student;
- cues for choosing or recognizing the concept;
- useful checks or interpretations; and
- links to definitions, examples, misconceptions, teaching tips, and question families.

A concept does not embed copies of all related components. It owns typed relationships to their
stable IDs. The catalog builds reverse indexes so either direction can be queried.

#### Term

A term introduces vocabulary, notation, pronunciation when useful, aliases, and a concise meaning.
A glossary is derived from terms reached by the selected concepts.

#### Learning objective

An objective states an observable student capability and links to the concepts it covers and the
questions that provide evidence. Objectives are components so section introductions,
self-assessments, coverage reports, and unit practices refer to the same statements.

### 4.2 Reader-visible narrative components

#### Motivation

A student-facing paragraph or short sequence that opens an idea through a relevant situation,
question, pattern, or surprise. It links to the concept it motivates. It contains no authorial
commentary.

Motivation is usually static, but it may reference a generated calculation or figure placement.

#### Exposition

Reader-facing explanation that connects definitions, representations, and procedures. Exposition
may include references to terms, claims, examples, and computed inline values, but it must not hide
independent calculations in TeX.

#### Transition

A short connection between adjacent concepts or representations. A transition records `from` and
`to` concept IDs so an assembly checker can reject transitions whose endpoints are absent.

#### Calculation

A small generated mathematical component intended for inline or displayed use inside exposition.
It owns canonical inputs, derived values, display values, and checks just like a question, but it
does not ask the reader for a response.

Examples include:

- evaluating a substituted expression;
- deriving a table row;
- calculating a slope from two points;
- producing exact and decimal forms; and
- computing diagram coordinates.

This is the component that prevents calculated values from being typed independently into
textbook prose.

#### Figure

A diagram, graph, table, or other mathematical visual. Parameterized geometry derives from the
same canonical values as the associated calculation, example, or question. A figure declares what
measurements and relationships its checks validate.

### 4.3 Mathematical claim components

#### Definition

A definition gives a term or concept an exact mathematical meaning. It may include prerequisites,
equivalent forms, scope, examples, and nonexamples. Definitions are normally static claims but can
reference generated illustrations.

#### Claim

The general object for a mathematical statement with assumptions, conclusion, evidence, and
optional proof. Its displayed style may be proposition, identity, rule, fact, conjecture, or
observation.

#### Lemma

A claim whose principal role is supporting another claim. Its `supports` relation must name at
least one claim or proof step.

#### Theorem

A claim intended as a significant reusable result. It records assumptions, dependencies, and an
evidence requirement. A theorem may be human-proved, formally proved, or explicitly unformalized;
the renderer must not blur those states.

#### Corollary

A claim whose evidence depends primarily on a named theorem and a short derivation.

#### Proof

A proof supports one or more claims. It may contain reviewed TeX, a formal-proof artifact, or both.
The manifest records the proof backend, assumptions, artifact hash, and checking status.

The display names lemma, theorem, and corollary are meaningful roles, not separate computation
engines. All share the claim-and-evidence contract.

### 4.4 Instructional components

#### Worked example

A worked example models mathematical thinking for the student. It contains or references:

- a task or situation;
- the concept cues a student should notice;
- canonical parameters and derived values when generated;
- a thought-process projection;
- sequential mathematical steps with reasons;
- a final result;
- a check or interpretation; and
- concepts illustrated.

Worked examples and questions may share a generator or a lower-level scenario component. They need
not duplicate mathematical logic.

#### Question

The existing mathpub question becomes a component kind rather than a separate privileged catalog.
It retains:

- prompt, short-answer, worked-solution, and validation projections;
- generator, parameters, derived values, constraints, and checks;
- difficulty, tags, workspace, and points; and
- concepts assessed and objective evidence.

A fixed question is still an individually identified component. A problem set must never replace
twenty question components with one TeX file containing twenty anonymous `\item` entries.

#### Hint

A hint is independently projectable and linked to a question or example. Ordered hint levels can
move from a cue to a partial setup without leaking the complete solution.

#### Misconception

A misconception records:

- concepts affected;
- a plausible incorrect belief or work sample;
- a diagnostic cue or question;
- why the reasoning fails;
- corrected mathematics; and
- related questions or examples.

Its wrong and corrected work may be parameterized from the same instance. “Common Mistakes” is a
derived collection of misconception components linked to the concepts in an assembly.

#### Teaching tip

A teaching tip is written to a tutor, teacher, or homeschool parent. It links to concepts and
usually to a misconception. It specifies:

- an action, visual, object, or question to use;
- what the student should say, mark, build, or calculate;
- what response indicates understanding;
- what response reveals the linked misconception; and
- a concrete follow-up.

Teaching tips are selected from the concepts present in a lesson or chapter rather than copied into
each manuscript.

#### Self-assessment prompt

A self-assessment prompt links an objective or misconception to evidence in completed placements.
It can ask for a confidence rating, cited work, a correction, an explanation, or a next action.
Section and unit self-assessments are collections of these prompts resolved against actual
question placement IDs.

### 4.5 Composite components

#### Problem set

A problem set is an ordered collection specification, not a TeX question container. It may:

- include explicit question component IDs;
- select from question families under declared constraints;
- require counts by concept, objective, representation, and difficulty;
- reserve categories such as application or error analysis;
- declare workspace and numbering policy; and
- choose whether instances are original, shared, fresh, or pinned.

The resolved problem set records every selected question and instance in the manifest.

#### Summary

A summary is a derived component. By default it collects, in concept order:

- each concept's student-facing summary;
- its recognition cue;
- its essential notation or definition;
- its principal check; and
- optionally a linked summary example.

An author may add a transition or synthesis paragraph, but may not replace concept summaries with a
second unsynchronized list of facts.

#### Common-errors collection

This derived component gathers misconceptions linked to selected concepts. Assembly rules may
limit the number, prioritize severe or frequent errors, and avoid duplicates.

#### Teaching-tips collection

This derived component gathers teaching tips linked to selected concepts and misconceptions. It is
visible only in projections intended for the named adult audience.

#### Glossary

A glossary gathers term components reached by a publication, sorted according to the publication
profile. Definitions remain owned by the original term or definition components.

#### Lesson or section

A lesson is an ordered assembly of placements plus declared concepts and objectives. It typically
contains motivation, exposition, definitions, examples, derived common errors, a derived summary,
teaching tips, a problem set, and self-assessment.

The structure is explicit but not rigid: a proof-oriented article section and an Algebra 1
workbook section can use different profiles while including the same components.

#### Unit or chapter

A chapter groups lessons. Its concept set is the ordered union of concepts introduced or practiced
by those lessons. Chapter summaries, glossaries, teaching tips, coverage reports, and practices are
derived from that set.

#### Publication

A publication orders chapters, sections, or other assemblies and selects a profile, audience,
variant, projections, and root seed. It never contains mathematical source copied from components.

## 5. Relationship lexicon

Relationships are typed and schema-checked.

| Relation | Source | Target | Meaning |
|---|---|---|---|
| `defines` | definition | term or concept | supplies exact meaning |
| `uses` | any renderable component | concept, term, or calculation | depends on content |
| `prerequisite` | concept or objective | concept | should precede source |
| `motivates` | motivation | concept | introduces a reason to learn it |
| `explains` | exposition | concept or claim | develops reader understanding |
| `illustrates` | example or figure | concept or claim | shows a concrete instance |
| `assesses` | question | concept or objective | provides evidence of learning |
| `diagnoses` | misconception or question | concept | exposes a misunderstanding |
| `addresses` | teaching tip | misconception | gives an intervention |
| `supports` | lemma, proof, or evidence | claim | supplies justification |
| `derives-from` | claim, calculation, or example | component | identifies dependency |
| `hints-for` | hint | question or example | gives staged assistance |
| `summarizes` | summary facet | concept | supplies canonical review text |
| `revisits` | lesson or question | concept | provides spaced retrieval |

Content dependencies form a directed acyclic graph. Placement containment forms a separate ordered
tree. Keeping these structures distinct prevents a concept relationship from silently controlling
document order.

## 6. Proposed source layout

The catalog should discover all component kinds beneath component roots:

```text
components/
  algebra/
    distribution/
      concept.toml
      summary.tex
      definitions/
        distributive-property/
          component.toml
          body.tex
      examples/
        negative-factor/
          component.toml
          generate.sage
          prompt.tex
          thought-process.tex
          steps.tex
          result.tex
          check.tex
      misconceptions/
        first-term-only/
          component.toml
          wrong.tex
          diagnosis.tex
          correction.tex
      teaching-tips/
        draw-the-arrows/
          component.toml
          body.tex
      questions/
        negative-binomial/
          component.toml
          generate.sage
          prompt.tex
          answer.tex
          solution.tex
```

Directory nesting aids authors but does not define identity or relationships. Metadata does.

Existing question directories remain valid during migration and are exposed as components of kind
`question`.

## 7. Common metadata contract

Every component has:

```toml
schema = 2
id = "algebra.distribution.example.negative-factor"
kind = "example"
title = "Distributing a negative factor"
status = "reviewed"
tags = ["algebra-1", "distribution", "signed-numbers"]
concepts = ["algebra.distribution", "algebra.signed-multiplication"]
audiences = ["student"]

[source]
generator = "generate.sage"

[testing]
sample_seeds = 20
max_attempts = 100
```

Kind-specific schemas declare required fragments and relationships. `additionalProperties: false`
remains the default so misspelled relationships do not disappear silently.

## 8. Generation model

### 8.1 Generalized component context

The current question `Context` becomes a component-generation context without weakening its
contract:

- `parameter` stores canonical chosen values;
- `derived` stores canonical computed values;
- `display.*` stores presentation only;
- `require` rejects unsuitable instances;
- `check_*` records mathematical evidence; and
- `validation_note` explains important checks outside student projections.

Questions, examples, calculations, figures, misconceptions, and selected claims may all use this
context.

### 8.2 Shared mathematical scenarios

When several components need the same mathematical setup, they reference a scenario generator
rather than copy Sage code. A scenario is a non-rendered computational component that declares
parameters, derivations, constraints, and checks.

For example, one linear-equation scenario can support:

- a worked example;
- a direct practice question;
- an error-analysis question;
- a graph or balance-scale figure; and
- a teaching tip showing a diagnostic substitution.

Each placement chooses whether it shares one scenario instance or requests a fresh deterministic
instance.

### 8.3 Stable randomness

An instance seed derives from:

```text
root seed + variant + component ID + placement ID + attempt
```

Reordering unrelated placements must not change existing instances. Reusing a component twice in
one publication must not accidentally give both placements the same numbers unless `instance =
"shared"` is explicit.

### 8.4 Static mathematics

A static definition or theorem does not need a Sage generator merely to satisfy the framework.
It still declares assumptions, evidence status, dependencies, and source identity. Any embedded
computed example must be a calculation or example component, not an unchecked numeral hidden in
the prose.

## 9. Assembly model

An illustrative lesson assembly:

```toml
[[chapters]]
id = "foundations"
title = "Foundations of Algebra"

[[chapters.lessons]]
id = "distribution"
title = "The Distributive Property"
concepts = ["algebra.distribution"]
objectives = ["algebra.distribution.objective.expand"]

[[chapters.lessons.blocks]]
include = "algebra.distribution.motivation.sharing"

[[chapters.lessons.blocks]]
include = "algebra.distribution.definition"

[[chapters.lessons.blocks]]
include = "algebra.distribution.example.positive-factor"
role = "guided-example"
instance = "fresh"

[[chapters.lessons.blocks]]
include = "algebra.distribution.example.negative-factor"
role = "guided-example"
instance = "fresh"

[[chapters.lessons.blocks]]
derive = "common-errors"
from_concepts = "lesson"

[[chapters.lessons.blocks]]
derive = "concept-summary"
from_concepts = "lesson"

[[chapters.lessons.blocks]]
derive = "teaching-tips"
from_concepts = "lesson"
audience = "parent"

[[chapters.lessons.blocks]]
include = "algebra.distribution.problem-set"

[[chapters.lessons.blocks]]
derive = "self-assessment"
from_objectives = "lesson"
```

The source identifies components and derivation rules. The resolved assembly written to the build
directory lists exact placements and instances.

## 10. Projection rules

Each component kind declares allowable projections.

- **Student:** motivation, exposition, definitions, claims, selected proofs, examples, question
  prompts, hints chosen by profile, summaries, and self-assessments.
- **Answers:** student material plus concise answers at the configured location.
- **Solutions:** student material plus thought processes and full solutions.
- **Validation:** solution material plus checks, assumptions, evidence types, generator provenance,
  and human-review boundaries.
- **Parent or tutor:** student material plus teaching tips and optional diagnostic guidance.
- **Slides or presenter:** selected component views and speaker notes without changing instances.

Projection isolation is enforced at fragment and schema boundaries. A student projection cannot
read an answer or proof fragment merely because TeX conditionals would hide it.

## 11. Derived sections

### 11.1 Section summary

Collect the summary facet of each concept introduced by the lesson, preserve concept order, remove
duplicate prerequisites, and optionally add an authored synthesis component.

### 11.2 Chapter summary

Take the ordered union of concepts introduced across the chapter. Include each concept once,
followed by its recognition cue and principal check. A chapter-level synthesis may describe
connections among the concepts.

### 11.3 Common mistakes

Select misconception components linked to lesson concepts. Prefer misconceptions exercised by a
question or example in the same lesson. Do not emit a generic warning when no reviewed
misconception exists.

### 11.4 Teaching tips

Select tips linked to lesson concepts and misconceptions. Tips appear only in the configured adult
projection or in an explicitly requested student-and-parent edition.

### 11.5 Problem sets and unit practices

Resolve collection constraints to concrete question placements before generation. The resolver
must report coverage by concept and objective and fail when it cannot meet the declared mix.
Selections and instances are stored in the manifest so a later build never silently chooses a
different set.

## 12. Validation

### 12.1 Component validation

`check component ID` verifies:

- schema and required fragments;
- referenced component IDs and relation types;
- deterministic generation;
- constraints and declared seed samples;
- mathematical checks;
- projection isolation; and
- source-specific requirements, such as a proof for a formally proved claim.

### 12.2 Graph validation

`check project` verifies:

- no dependency cycles;
- prerequisite ordering;
- every referenced concept, objective, and component exists;
- definitions precede uses within an assembly unless explicitly marked review;
- every misconception and teaching tip reaches a concept;
- every question assesses at least one concept or objective; and
- no stable ID is duplicated.

### 12.3 Assembly validation

`check publication` resolves all derived collections and verifies:

- all placements are legal for their roles and audiences;
- every generated placement has an accepted immutable instance;
- problem-set and practice coverage constraints are satisfied;
- summaries match the selected concept graph;
- solutions exist for assessed questions;
- no answer material reaches the student projection; and
- the requested profile can render every component kind.

### 12.4 Mathematical validation

Sage checks instances, not prose. Claims state their evidence separately. The validation edition
must identify:

- what was checked;
- under which assumptions;
- by which backend;
- at what evidence strength;
- for which instance or general claim; and
- what still requires human review.

## 13. Manifest requirements

A component-based publication manifest records:

- source revision, dirty state, flake lock, profile, and fonts;
- resolved assembly and placement order;
- every component source hash;
- every relationship used to derive a collection;
- every selected concept and objective;
- every generated or static component instance;
- root and derived seeds;
- parameters, derived values, display values, constraints, and checks;
- proof and evidence artifacts;
- projection decisions;
- problem-set coverage results; and
- output identities.

A textbook manifest with mathematical examples or questions must never contain an empty component
or instance list.

## 14. Agent-facing CLI

The component model must be discoverable without reading arbitrary source files:

```console
mathpub list components --kind concept --json
mathpub show component algebra.distribution --json
mathpub graph concept algebra.distribution --json
mathpub check component algebra.distribution.example.negative-factor --seeds 20 --json
mathpub preview component algebra.distribution.example.negative-factor --seed 2026 --json
mathpub resolve publication publications/algebra1.toml --seed 2026 --json
mathpub check publication publications/algebra1.toml --json
```

Scaffolding should create complete examples for each supported component kind. Repository
instructions should tell an agent to inspect concepts and related components before authoring new
material.

## 15. Migration from the current implementation

### Phase 1: Generalize the catalog

- Introduce `component` as the catalog base type.
- Treat every existing question as a component of kind `question`.
- Preserve current question commands as aliases.
- Generalize instance and rendering APIs without changing question behavior.

### Phase 2: Concepts and atomic components

- Add schemas and scaffolds for concepts, terms, motivation, exposition, definitions, claims,
  calculations, examples, misconceptions, teaching tips, and objectives.
- Add typed relationships and graph validation.
- Demonstrate shared generation between a calculation, example, and question.

### Phase 3: Assembly and derived collections

- Replace the raw textbook `content/exercises/answers/solutions` schema with ordered placements.
- Add problem-set resolution, concept-derived summaries, common errors, teaching tips, and
  self-assessments.
- Store resolved assemblies and instances in manifests.

### Phase 4: Migrate one chapter

- Decompose Algebra 1 Chapter 1 into reviewed components.
- Ensure every worked computation and question is generated or explicitly static.
- Produce student, answers, solutions, validation, and parent projections.
- Require nonempty instance and evidence records.
- Compare the result editorially and visually with Anna's reference chapter.

Only after this vertical slice passes should Chapters 2–10 be migrated.

### Phase 5: Claims and proof backends

- Add claim, lemma, theorem, corollary, and proof artifacts.
- Integrate a selected proof assistant behind the same evidence interface.
- Keep Sage symbolic checks distinct from formal proof.

## 16. Compatibility and deprecation

Tests and worksheets using existing question publications remain supported throughout migration.
The current bulk textbook lesson schema may remain readable temporarily, but it is designated
legacy and receives a visible validation warning. It must not be used for new textbook content.

Legacy lesson files can be imported only by decomposing them into components. Wrapping a large
`exercises.tex` file in a component would preserve the architectural defect and is not a valid
migration.

## 17. Acceptance criteria for the component model

The design is implemented successfully when:

1. one component catalog serves worksheets, tests, textbooks, slides, and articles;
2. a question used in a lesson can be listed, previewed, checked, varied, and reused independently;
3. worked examples and inline calculations use canonical generated values;
4. student, answer, solution, and validation views consume the same immutable instances;
5. concept summaries, common mistakes, teaching tips, glossaries, and self-assessments derive from
   typed relationships;
6. problem sets contain resolved question placements rather than anonymous TeX items;
7. manifests enumerate every mathematical component, instance, check, and evidence boundary;
8. changing a generator cannot leave an answer, example, diagram, or summary calculation stale;
9. an agent can discover and safely author each component kind through documented schemas and CLI
   commands; and
10. the Algebra 1 Chapter 1 vertical slice satisfies both the computational architecture and
    Anna's reader-facing quality standard.

## 18. Decisions this design makes

- `component` is the common abstraction; `question` remains a first-class component kind.
- `concept` is a semantic hub with canonical summary data and typed links.
- summaries, common-error sections, teaching-tip sections, glossaries, and practices are derived
  assemblies.
- generated instances and document placements are separate identities.
- Sage generation is available to every math-bearing component, not only questions.
- scenario components may share canonical mathematics across examples, questions, figures, and
  calculations.
- large mixed TeX files are not valid substitutes for component collections.
- the current question model is the compatibility foundation, not a discarded prototype.

## 19. Open design questions

The following should be resolved with small vertical prototypes:

1. Whether concept summary facets live directly in `concept.toml`, in named TeX fragments, or as
   linked summary components.
2. Whether scenario generators use composition, imports, or a declarative dependency interface.
3. How much automatic problem-set selection is desirable before explicit reviewed selections are
   preferable.
4. Whether parent material is a separate projection or an overlay on student and solution
   projections.
5. Which claim kinds require proofs and which evidence policies belong to a publication profile.
6. How cross-component TeX references and counters remain stable across different publication
   families.
7. How to represent accessible alternatives for figures, tables, and symbolic notation.
