# mathpub

`mathpub` is an emerging, reproducible publishing system for trustworthy mathematics. Its goal is to turn one TeX-based source into professional worksheets, workbooks, slide decks, textbooks, articles, and matching answer keys.

The project combines:

- TeX for precise mathematical writing and publication-quality typography;
- SageMath for symbolic computation, validation, and deterministic question generation;
- machine-checkable proofs for the mathematical claims that matter;
- Nix flakes for repeatable builds on macOS and Linux; and
- a structured content model that can render the same mathematics for different audiences and formats.

## Status

`mathpub` is at the design stage. This repository currently defines the project and its engineering principles; it does not yet contain a working publisher. See [VISION.md](VISION.md) for the intended architecture, trust model, and roadmap.

## What we want to build

A mathpub document should be able to express prose, notation, theorems, proofs, examples, exercises, generators, and solutions without copying the same content between student and instructor editions.

A future workflow might look like this:

```console
nix develop
mathpub check algebra-1
mathpub build algebra-1 --format worksheet --seed 2026
mathpub build algebra-1 --format answers   --seed 2026
mathpub build algebra-1 --format slides
```

The same seed would always produce the same questions and answers. A build would fail—not merely warn—when a generated instance violates its constraints, a symbolic check disagrees with an expected result, a required proof artifact is stale, or TeX cannot be rendered cleanly.

## Design principles

1. **Correctness is a feature.** Important claims should have explicit evidence: a formal proof, an independently checked symbolic identity, or a clearly identified human-review boundary.
2. **One source, several publications.** Student editions, answer keys, presentations, and long-form texts should be projections of shared content.
3. **Generated questions are constrained data.** Generators must declare valid domains, reject degenerate cases, produce solutions from the same parameters, and support reproducible seeds.
4. **Builds are hermetic.** Fonts, TeX packages, SageMath, proof tools, and project code are pinned by the flake.
5. **Outputs are inspectable.** Every artifact should record its source revision, toolchain, seed, and validation results.
6. **TeX remains first-class.** Authors should retain direct control over notation, macros, page design, and specialist packages.

## Intended toolchain

The initial implementation will explore:

- LuaLaTeX and a curated TeX Live environment;
- SageMath, initially through generated data files or SageTeX where appropriate;
- a small command-line build orchestrator;
- declarative metadata for variants, audiences, dependencies, and validation;
- golden-file, property-based, and PDF regression tests; and
- integration with a proof assistant for selected definitions and theorems.

The exact proof assistant and interchange format remain design decisions. SageMath is excellent computational evidence, but computation alone is not a universal proof system; mathpub will keep those assurance levels distinct.

## Reproducibility target

The supported entry point will be a Nix flake:

```console
nix develop
nix flake check
nix build
```

The project begins on nix-darwin, but the flake and continuous integration should support common Linux systems as well. Binary reproducibility of PDFs can be complicated by timestamps and engine behavior, so the first target is reproducible content and toolchains, followed by byte-for-byte output where practical.

## Contributing

The project is not yet ready for general contributions. Early design discussion is welcome, especially from mathematics educators, TeX practitioners, proof-assistant users, accessibility experts, and reproducible-build engineers.

By contributing, you agree that your contributions are licensed under the GNU General Public License version 3.

## License

mathpub is free software licensed under the [GNU General Public License, version 3](LICENSE).
