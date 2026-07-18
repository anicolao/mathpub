# Working with mathpub

This repository is both the mathpub implementation and a mathpub authoring project. Use only
programs supplied by `flake.nix`. Enter the environment with `nix develop`, or run the packaged
CLI as `nix run .#mathpub -- COMMAND`. Never invoke a host Python, Sage, TeX, formatter, or test
runner, and never edit generated files beneath `build/`.

Before creating a question, inspect the catalog:

```console
nix run .#mathpub -- list questions --json
nix run .#mathpub -- show question QUESTION_ID --json
```

A question is a directory containing reviewed TOML metadata, a Sage generator, and separate TeX
fragments for its prompt, short answer, and worked solution. Copy the closest reviewed example
when possible. Keep exact mathematical values in `ctx.parameter` and `ctx.derived`; use
`ctx.display.*` only to define presentation. Use `ctx.require` for pedagogical suitability and
`ctx.check_*` for mathematical evidence. A computational check is not a formal proof.
Attach a plain-language explanation to every important check with
`ctx.validation_note(CHECK_ID, NOTE)`; it appears only in the validation projection.

Parameterized diagram coordinates must be derived from the same canonical parameters used by the
mathematics. Use one common coordinate scale for measurable axes and validate lengths, angles, and
endpoints with `ctx.check_*`. Do not label student diagrams with implementation-scale commentary.

Required validation loop after authoring or changing a question:

```console
nix run .#mathpub -- check question QUESTION_ID --seeds 20 --json
nix run .#mathpub -- preview QUESTION_ID --seed 2026 --replace --json
nix run .#mathpub -- check publication publications/physics-practice.toml --json
nix run .#mathpub -- build publications/physics-practice.toml --seed 2026 --variant A --replace --json
nix flake check
```

Preserve explicit seeds in reports and commits. Do not put answer or solution content in
`prompt.tex`; projection isolation depends on those source boundaries.
