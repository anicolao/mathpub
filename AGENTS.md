# Working with mathpub

## Branching Policy

**Always work on a feature branch.** NEVER commit directly to `main`. Create or check out a dedicated feature branch (e.g. `feature/gui-workspace`, `tooling/algebra-ready`) before making any code, test, or documentation edits. Keep `main` clean and synchronized with `origin/main`.

## Authoring and Toolchain Guidelines

This repository is both the mathpub implementation and a mathpub authoring project. Use only
programs supplied by `flake.nix`. Enter the environment with `nix develop`, or run the packaged
CLI as `nix run .#mathpub -- COMMAND`. Never invoke a host Python, Sage, TeX, formatter, or test
runner, and never edit generated files beneath `build/`.

Before creating content, inspect the component catalog and the closest reviewed source:

```console
nix run .#mathpub -- list components --json
nix run .#mathpub -- show component COMPONENT_ID --json
```

Persisted component kinds are singular (`objective`, `misconception`, `teaching-tip`, `example`,
and `question`); plural directory names identify collections. New questions must use the component
schema and can be scaffolded with `nix run .#mathpub -- new question ID --concept CONCEPT_ID
--template TEMPLATE`. A question component contains reviewed TOML metadata, an optional Sage
generator, and separate TeX fragments for its prompt, short answer, and worked solution. Copy the
closest reviewed example when possible. Keep exact mathematical values in `ctx.parameter` and `ctx.derived`; use
`ctx.display.*` only to define presentation. Use `ctx.require` for pedagogical suitability and
`ctx.check_*` for mathematical evidence. A computational check is not a formal proof.
Attach a plain-language explanation to every important check with
`ctx.validation_note(CHECK_ID, NOTE)`; it appears only in the validation projection.
When preserving a source fixture alongside generated comparisons, use `ctx.variant == "original"`
for the reviewed values and constrained generation for other variant names. Test both paths.

Parameterized diagram coordinates must be derived from the same canonical parameters used by the
mathematics. Use one common coordinate scale for measurable axes and validate lengths, angles, and
endpoints with `ctx.check_*`. Do not label student diagrams with implementation-scale commentary.

Required validation loop after authoring or changing a question component:

```console
nix run .#mathpub -- check component QUESTION_ID --seeds 20 --json
nix run .#mathpub -- preview QUESTION_ID --seed 2026 --replace --json
nix run .#mathpub -- check publication publications/physics-practice.toml --json
nix run .#mathpub -- build publications/physics-practice.toml --seed 2026 --variant A --replace --json
nix flake check
```

Preserve explicit seeds in reports and commits. Do not put answer or solution content in
`prompt.tex`; projection isolation depends on those source boundaries.
