"""Projection-specific TeX rendering and PDF compilation."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

from mathpub.catalog import Entry
from mathpub.errors import MathpubError

LOOKUP = re.compile(r"\\mp(value|parameter|derived)\{([a-z][a-z0-9_]*)\}")


def _tex_escape(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    return "".join(replacements.get(character, character) for character in value)


def validation_tex(instance: dict[str, Any]) -> str:
    notes = instance.get("validation_notes", {})
    items = []
    for check in instance.get("checks", []):
        assumptions = ", ".join(check.get("assumptions", ())) or "none beyond the model"
        note = notes.get(check["id"], "No additional author note supplied.")
        items.append(
            "\n".join(
                [
                    rf"\item \textbf{{{_tex_escape(check['id'])}}} "
                    rf"[{_tex_escape(check['evidence'])}; {_tex_escape(check['backend'])}]",
                    _tex_escape(note),
                    rf"\emph{{Assumptions:}} {_tex_escape(assumptions)}. "
                    rf"\emph{{Status:}} {_tex_escape(check['status'])}.",
                ]
            )
        )
    if not items:
        items.append(
            r"\item No executable checks are declared; this fixed content requires review."
        )
    return "\n".join(
        [
            r"\medskip\textbf{Validation and justification}",
            r"\begin{itemize}",
            *items,
            r"\end{itemize}",
            r"\small This is computational evidence, not a kernel-checked formal proof.",
        ]
    )


def _serialized_tex(value: Any) -> str:
    if isinstance(value, (str, bool)):
        return str(value)
    kind = value.get("type")
    if kind == "integer":
        return str(value["value"])
    if kind == "rational":
        return rf"\frac{{{value['numerator']}}}{{{value['denominator']}}}"
    if kind == "real":
        return value["decimal"]
    if kind == "expression":
        return value["tex"]
    raise MathpubError("MP-TEX-001", f"cannot render mathematical value: {value}", exit_code=6)


def expand(fragment: str, instance: dict[str, Any], question_id: str) -> str:
    def replace(match: re.Match) -> str:
        namespace, name = match.groups()
        if namespace == "value":
            values = instance["display"]
            if name not in values:
                raise MathpubError(
                    "MP-TEX-002", f"missing display value {name} in {question_id}", exit_code=6
                )
            return values[name]["tex"]
        values = instance["parameters" if namespace == "parameter" else "derived"]
        if name not in values:
            raise MathpubError(
                "MP-TEX-003", f"missing {namespace} {name} in {question_id}", exit_code=6
            )
        return _serialized_tex(values[name])

    return LOOKUP.sub(replace, fragment)


def question_tex(
    entry: Entry, instance: dict[str, Any], projection: str, points: int | None = None
) -> str:
    metadata = entry.metadata
    prompt = expand((entry.path / metadata["prompt"]).read_text(), instance, metadata["id"])
    pieces = [rf"\question[{points if points is not None else metadata['points']}]", prompt]
    if projection == "student":
        workspace = metadata.get("workspace", {}).get("student", "25mm")
        pieces.append(rf"\vspace{{{workspace}}}")
    elif projection == "answers":
        if not metadata.get("answer"):
            raise MathpubError(
                "MP-TEX-004", f"question has no answer: {metadata['id']}", exit_code=3
            )
        answer = expand((entry.path / metadata["answer"]).read_text(), instance, metadata["id"])
        pieces.append(rf"\begin{{solution}}{answer}\end{{solution}}")
    elif projection in {"solutions", "validation"}:
        if not metadata.get("solution"):
            raise MathpubError(
                "MP-TEX-005", f"question has no solution: {metadata['id']}", exit_code=3
            )
        solution = expand((entry.path / metadata["solution"]).read_text(), instance, metadata["id"])
        pieces.append(rf"\begin{{solution}}{solution}\end{{solution}}")
        if projection == "validation":
            pieces.append(validation_tex(instance))
    else:
        raise MathpubError("MP-TEX-006", f"unknown projection: {projection}", exit_code=3)
    return "\n".join(pieces)


def document_tex(publication: dict[str, Any], projection: str, questions: list[str]) -> str:
    paper = "a4paper" if publication.get("paper") == "a4" else "letterpaper"
    answers = "\\printanswers" if projection != "student" else "\\noprintanswers"
    instructions = publication.get("instructions", {}).get("tex", "")
    course = publication.get("course", "")
    title = publication["title"]
    projection_label = {
        "student": "Student",
        "answers": "Short Answers",
        "solutions": "Worked Solutions",
        "validation": "Validation and Justification",
    }[projection]
    display_title = f"{title} — {projection_label}"
    author = publication.get("author", "")
    return rf"""\documentclass[12pt,addpoints,{paper}]{{exam}}
\usepackage[margin=0.8in]{{geometry}}
\usepackage{{amsmath,mathtools}}
\usepackage{{fontspec,unicode-math}}
\setmainfont{{LibertinusSerif}}[
  Extension=.otf,
  UprightFont=*-Regular,
  ItalicFont=*-Italic,
  BoldFont=*-Bold,
  BoldItalicFont=*-BoldItalic
]
\setsansfont{{LibertinusSans}}[
  Extension=.otf,
  UprightFont=*-Regular,
  ItalicFont=*-Italic,
  BoldFont=*-Bold,
  BoldItalicFont=*-Italic
]
\setmathfont{{LibertinusMath-Regular.otf}}
\usepackage[per-mode=symbol]{{siunitx}}
\usepackage{{tikz,microtype}}
\setlength\parindent{{0pt}}
{answers}
\framedsolutions
\pagestyle{{headandfoot}}
\firstpageheader{{{course}}}{{\textbf{{{display_title}}}}}{{{author}}}
\runningheader{{{course}}}{{{display_title}}}{{Page \thepage\ of \numpages}}
\begin{{document}}
\begin{{center}}
  {{\Large\bfseries {display_title}}}\\[3pt]
  {publication.get("subtitle", "")}
\end{{center}}
\noindent Name: \rule{{2.7in}}{{0.4pt}}\hfill Date: \rule{{1.5in}}{{0.4pt}}
\medskip
{instructions}
\begin{{questions}}
{chr(10).join(questions)}
\end{{questions}}
\end{{document}}
"""


def compile_pdf(tex_path: Path, output_dir: Path) -> tuple[Path, Path]:
    process = subprocess.run(
        [
            "latexmk",
            "-lualatex",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-file-line-error",
            f"-outdir={output_dir}",
            str(tex_path),
        ],
        cwd=tex_path.parent,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
        env={
            **os.environ,
            "HOME": str(output_dir),
            "SOURCE_DATE_EPOCH": "0",
            "XDG_CACHE_HOME": str(output_dir / ".cache"),
        },
    )
    log_path = output_dir / f"{tex_path.stem}.build.log"
    log_path.write_text(process.stdout + "\n" + process.stderr, encoding="utf-8")
    pdf_path = output_dir / f"{tex_path.stem}.pdf"
    if process.returncode or not pdf_path.is_file():
        raise MathpubError("MP-TEX-007", f"LuaLaTeX failed; see {log_path}", exit_code=6)
    return pdf_path, log_path
