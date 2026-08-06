"""Version-matched capability discovery for authoring agents."""

from __future__ import annotations

from typing import Any

from mathpub import display_version
from mathpub.config import Project, schema_enum
from mathpub.scaffold import FRAMEWORK_GUIDE, QUESTION_TEMPLATES
from mathpub.styles import StyleCatalog

COMMANDS = (
    ("capabilities", "Discover this pinned framework contract and the library's styles."),
    ("list", "List components, questions, publications, profiles, or styles."),
    ("show", "Inspect one catalog entry, including a built-in or library style."),
    ("new", "Scaffold a component, question, or library-defined style."),
    ("check", "Validate a project, component, question, or publication."),
    ("preview", "Build all requested projections for one question in isolation."),
    ("build", "Build a deterministic publication edition."),
    ("variants", "Build several named deterministic variants."),
    ("reproduce", "Rebuild an edition from its stored manifest and instances."),
    ("workspace", "Launch the browser form of the interactive authoring workspace."),
)


def capability_data(project: Project) -> dict[str, Any]:
    """Return structured capabilities from the running framework and active library."""
    styles = StyleCatalog(project)
    return {
        "mathpub_version": display_version(),
        "project": project.config["project"],
        "authoring_root": str(project.root),
        "refresh_command": "nix run .#mathpub -- capabilities",
        "commands": [{"name": name, "purpose": purpose} for name, purpose in COMMANDS],
        "publication_kinds": list(schema_enum("publication", "kind")),
        "component_kinds": list(schema_enum("component", "kind")),
        "question_templates": list(QUESTION_TEMPLATES),
        "projections": ["student", "answers", "solutions", "validation", "parent"],
        "font_families": ["concrete", "libertinus", "computer-modern"],
        "styles": [entry.summary(project) for entry in styles.entries()],
        "style_authoring": {
            "scaffold_command": (
                "nix run .#mathpub -- new style STYLE_ID --extends mathpub --json"
            ),
            "list_command": "nix run .#mathpub -- list styles --json",
            "inspect_command": "nix run .#mathpub -- show style STYLE_ID --json",
            "publication_setting": 'style = "STYLE_ID"',
            "metadata": "styles/STYLE_ID/style.toml",
            "tex_customization": "styles/STYLE_ID/style.tex",
            "supports": ["textbook"],
        },
        "environment": {
            "entry": "nix develop",
            "guaranteed_tools": ["mathpub", "nix", "git", "gh", "jq", "rg", "pdftotext"],
            "add_tools_in": "flake.nix extraPackages",
        },
    }


def framework_guide(project: Project) -> str:
    """Render the human- and agent-readable contract with live style discovery."""
    styles = StyleCatalog(project).entries()
    rows = "\n".join(
        f"- `{style.identifier}` ({style.source}, base `{style.base}`): {style.description}"
        for style in styles
    )
    style_section = f"""## Publication styles

Styles control the document-wide typography and TeX preamble for textbook publications. Discover
the styles supplied by this pinned framework and this library instead of guessing a style name:

```console
nix run .#mathpub -- list styles --json
nix run .#mathpub -- show style STYLE_ID --json
```

Styles currently available in this library:

{rows}

To define a new library style, scaffold it from the closest existing style:

```console
nix run .#mathpub -- new style my-series --extends anna --json
```

Edit `styles/my-series/style.tex`, then set `style = "my-series"` in a textbook publication. The
customization is inserted after the inherited framework definitions, so it may load packages,
change geometry and fonts, or redefine commands such as `\\annachapter`. It must not declare a
document class, create a document environment, or read and write arbitrary files. A custom style
may extend another custom style. Run `check publication` and build every required projection after
style changes; the GUI watcher includes style sources in incremental rebuilds.
"""
    return FRAMEWORK_GUIDE.replace("## Presentations", f"{style_section}\n\n## Presentations")
