# mathpub

`mathpub` is a reproducible publishing system for trustworthy mathematical tests and worksheets.
Its MVP turns reviewed TeX fragments and deterministic SageMath generators into professional
student worksheets, compact answer keys, worked solutions, and validation/justification editions.

The project combines:

- TeX for precise mathematical writing and publication-quality typography;
- SageMath for symbolic computation, validation, and deterministic question generation;
- explicit computational evidence for mathematical checks, with a path toward formal proofs;
- Nix flakes for repeatable builds on macOS and Linux; and
- a structured content model that can render the same mathematics for different audiences and formats.

## Status

The worksheet/test MVP is implemented. It includes a Nix-packaged CLI, isolated deterministic
Sage generation, versioned schemas, projection-safe TeX rendering, provenance manifests,
reproduction from stored instances, and a representative three-question physics worksheet. See
[MVP_DESIGN.md](MVP_DESIGN.md) for the contract and [VISION.md](VISION.md) for the longer-term
publishing and formal-proof direction.

## Quick start

No host Python, SageMath, TeX installation, or font installation is used. With Nix flakes enabled:

```console
nix develop
nix flake check
```

Build every projection of the example worksheet with one command:

```console
nix run .#mathpub -- build publications/physics-practice.toml \
  --seed 2026 --variant A --replace --json
```

Outputs are written beneath `build/physics.practice/A/`. The manifest records the seed, variant,
question-instance hashes, mathematical checks, source identity, toolchain identity, and output
hashes. Generated output is disposable and must not be edited.

The example publication declares four PDFs: `student`, `answers`, `solutions`, and `validation`.
The validation edition contains every question, its worked solution, check classification,
assumptions, status, and plain-language justification notes. Diagram scales are validated in that
evidence without adding scale commentary to student-facing figures.

Useful authoring commands include:

```console
nix run .#mathpub -- list questions --json
nix run .#mathpub -- show question physics.energy.ramp-speed --json
nix run .#mathpub -- check question physics.energy.ramp-speed --seeds 20 --json
nix run .#mathpub -- check question physics.energy.ramp-speed --exhaustive --json
nix run .#mathpub -- preview physics.projectiles.snowball --seed 2026 --replace --json
nix run .#mathpub -- variants publications/physics-practice.toml --seed 2026 --count 3 --json
nix run .#mathpub -- reproduce build/physics.practice/A/manifest.json --replace --json
```

The repository’s [AGENTS.md](AGENTS.md) is the operational interface for Codex CLI and other LLM
harnesses. `mathpub init` generates equivalent instructions and complete question scaffolds for a
new authoring project.

## What we want to build

A mathpub document should be able to express prose, notation, theorems, proofs, examples, exercises, generators, and solutions without copying the same content between student and instructor editions.

A mathpub workflow looks like this:

```console
nix develop
nix run .#mathpub -- check project --json
nix run .#mathpub -- build publications/physics-practice.toml --seed 2026 --variant A
```

The same seed produces the same canonical questions and answers. A build fails—not merely warns—
when generation exhausts its constraints, a mathematical check fails, an instance hash disagrees,
or TeX cannot be rendered cleanly.

## Design principles

1. **Correctness is a feature.** Important claims should have explicit evidence: a formal proof, an independently checked symbolic identity, or a clearly identified human-review boundary.
2. **One source, several publications.** Student editions, answer keys, presentations, and long-form texts should be projections of shared content.
3. **Generated questions are constrained data.** Generators must declare valid domains, reject degenerate cases, produce solutions from the same parameters, and support reproducible seeds.
4. **Builds are hermetic.** Fonts, TeX packages, SageMath, proof tools, and project code are pinned by the flake.
5. **Outputs are inspectable.** Every artifact should record its source revision, toolchain, seed, and validation results.
6. **TeX remains first-class.** Authors should retain direct control over notation, macros, page design, and specialist packages.

## MVP toolchain

The pinned flake supplies:

- LuaLaTeX and a curated TeX Live environment;
- SageMath running generators out of process and returning canonical JSON instances;
- a Python command-line orchestrator packaged by Nix;
- declarative TOML metadata for questions and publications;
- LuaLaTeX, TeX Live packages, and Libertinus fonts from the Nix closure; and
- formatter, static-analysis, generator, failure-path, PDF, and end-to-end tests.

The exact proof assistant and expression interchange remain design decisions. SageMath checks are
recorded as symbolic, exact, sampled, exhaustive, or numerical evidence—not as formal proofs.

## Reproducibility target

The supported entry point is the Nix flake:

```console
nix develop
nix flake check
nix build
```

The flake declares nix-darwin and Linux systems. The verified MVP target is byte-identical canonical
instance JSON and equivalent PDF page content; PDF container bytes may differ between independent
compilations.

## Contributing

Contributions are welcome from mathematics educators, TeX practitioners, proof-assistant users,
accessibility experts, and reproducible-build engineers. All project commands and checks must run
through the flake; see [AGENTS.md](AGENTS.md) for the required validation loop.

By contributing, you agree that your contributions are licensed under the GNU General Public License version 3.

## License

mathpub is free software licensed under the [GNU General Public License, version 3](LICENSE).
