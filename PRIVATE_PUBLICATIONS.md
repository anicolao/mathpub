# Private publication repositories

## Boundary

The public `mathpub` repository contains the GPLv3 publishing engine, schemas, templates, tests,
and deliberately public examples. Publication manuscripts do not belong here. Each private body of
authored content should live in a new Git repository with no ancestry shared with a working branch
that ever contained that content.

Deleting manuscript files at the tip of a public branch is not sufficient: earlier commits remain
reachable. Start private publication repositories with `git init`, not by cloning or forking a
repository whose history contains other private manuscripts.

## Create a content repository

From a mathpub checkout, create a content-only project:

```console
nix run .#mathpub -- init ../private-math-book \
  --mathpub-url github:anicolao/mathpub
cd ../private-math-book
nix flake lock
nix flake check
```

`mathpub init` creates:

- `flake.nix`, which pins mathpub as a dependency;
- `mathpub.toml` and empty component/publication roots;
- content-repository instructions in `AGENTS.md`;
- a private-project README and generated-output exclusions; and
- no copy of mathpub's Python, TeX templates, schemas, tests, examples, or GPL licence.

When publications exist, list each one in the generated flake so `nix flake check` validates it:

```nix
publicationPaths = [
  "publications/student-book.toml"
  "publications/teacher-book.toml"
];
```

The content flake re-exports the pinned `mathpub` app, package, development shell, and formatter.
Normal work therefore stays inside that repository:

```console
nix develop
nix run .#mathpub -- list components --json
nix run .#mathpub -- check project --json
nix run .#mathpub -- build publications/student-book.toml \
  --seed 2026 --variant review --replace --json
```

## Create the private GitHub remote

Initialize a new history and inspect exactly what will be committed:

```console
git init -b main
git add AGENTS.md README.md .gitignore flake.nix flake.lock mathpub.toml \
  components publications profiles
git status --short
git commit -m "Initialize private mathpub publication"
nix develop -c gh repo create OWNER/private-math-book \
  --private --source=. --remote=origin --push
```

Confirm the repository reports `PRIVATE` before inviting collaborators:

```console
nix develop -c gh repo view OWNER/private-math-book --json nameWithOwner,visibility,url
```

GitHub visibility is only one boundary. The owner remains responsible for collaborator access,
branch protection, Actions logs and artifacts, backups, generated PDFs, and any content licence.
No licence file is generated for authored content.

## Public examples

Only content intentionally approved for unrestricted public distribution should be added beneath
the tooling repository's `questions/` or `publications/` trees. The physics practice publication is
the base example and regression fixture. Private repositories may copy its structure, but should
use their own IDs and never push proprietary source back to the public tooling remote.
