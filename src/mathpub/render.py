"""Projection-specific TeX rendering and PDF compilation."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from mathpub.catalog import Entry
from mathpub.errors import MathpubError, timeout_transcript

LOOKUP = re.compile(r"\\mp(value|parameter|derived)\{([a-z][a-z0-9_]*)\}")

FONT_CHOICES = ("concrete", "libertinus", "computer-modern")

NUMBER_SET_PREAMBLE = r"""\usepackage{dsfont}
\newcommand{\mpNaturals}{\mathds{N}}
\newcommand{\mpWholes}{\mathds{W}}
\newcommand{\mpIntegers}{\mathds{Z}}
\newcommand{\mpRationals}{\mathds{Q}}
\newcommand{\mpIrrationals}{\mathds{I}}
\newcommand{\mpReals}{\mathds{R}}"""

SOURCE_BEGIN = "% mathpub-source-begin "
SOURCE_END = "% mathpub-source-end"

MATH_ONLY_COMMAND = re.compile(
    r"\\(?:d?frac|tfrac|sqrt|cdot|times|div|pm|mp|leq?|geq?|neq|sum|prod|pi|theta|alpha|beta)\b"
)


def font_preamble(font_family: str) -> str:
    if font_family == "computer-modern":
        return ""
    if font_family == "concrete":
        return r"""\usepackage{fontspec,unicode-math}
\setmainfont{cmunorm.otf}[
  BoldFont=cmunobx.otf,
  ItalicFont=cmunoti.otf,
  BoldItalicFont=cmunobi.otf
]
\setmathfont{Euler-Math.otf}"""
    if font_family == "libertinus":
        return r"""\usepackage{fontspec,unicode-math}
\setmainfont{LibertinusSerif}[
  Extension=.otf,
  UprightFont=*-Regular,
  ItalicFont=*-Italic,
  BoldFont=*-Bold,
  BoldItalicFont=*-BoldItalic
]
\setsansfont{LibertinusSans}[
  Extension=.otf,
  UprightFont=*-Regular,
  ItalicFont=*-Italic,
  BoldFont=*-Bold,
  BoldItalicFont=*-Italic
]
\setmathfont{LibertinusMath-Regular.otf}"""
    raise MathpubError("MP-TEX-010", f"unknown font family: {font_family}", exit_code=3)


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


def validate_fragment_source(source: str, mode: str, source_path: Path) -> None:
    """Reject fragment content that contradicts its declared rendering mode."""
    if mode == "math":
        delimiter = re.search(r"(?<!\\)\$|\\[()\[\]]", source)
        if delimiter:
            raise MathpubError(
                "MP-TEX-012",
                f"math fragment supplies its own delimiter in {source_path}: {delimiter.group()}",
                details={"authored_source": str(source_path), "fragment_mode": mode},
            )
        return
    if mode == "plain-text":
        command = re.search(r"\\[A-Za-z]+|(?<!\\)\$", source)
        if command:
            raise MathpubError(
                "MP-TEX-012",
                f"plain-text fragment contains TeX in {source_path}: {command.group()}",
                details={"authored_source": str(source_path), "fragment_mode": mode},
            )
        return
    if mode != "mixed-tex":
        raise MathpubError("MP-TEX-012", f"unknown fragment mode {mode} in {source_path}")

    outside: list[str] = []
    cursor = 0
    math_closer: str | None = None
    token_pattern = re.compile(r"(?<!\\)\$|\\[()\[\]]")
    for token in token_pattern.finditer(source):
        if math_closer is None:
            outside.append(source[cursor : token.start()])
            math_closer = {"$": "$", r"\(": r"\)", r"\[": r"\]"}.get(token.group())
            if math_closer is None:
                raise MathpubError(
                    "MP-TEX-012",
                    f"unmatched math delimiter in {source_path}: {token.group()}",
                    details={"authored_source": str(source_path), "fragment_mode": mode},
                )
        elif token.group() == math_closer:
            math_closer = None
        cursor = token.end()
    if math_closer is not None:
        raise MathpubError(
            "MP-TEX-012",
            f"unclosed math delimiter in {source_path}: expected {math_closer}",
            details={"authored_source": str(source_path), "fragment_mode": mode},
        )
    if math_closer is None:
        outside.append(source[cursor:])
    if command := MATH_ONLY_COMMAND.search("".join(outside)):
        raise MathpubError(
            "MP-TEX-012",
            f"math-only TeX outside math mode in {source_path}: {command.group()}",
            details={"authored_source": str(source_path), "fragment_mode": mode},
        )


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
    prompt = component_fragment(entry, instance, "prompt")
    pieces = [rf"\question[{points if points is not None else metadata.get('points', 1)}]", prompt]
    fragment_name = "prompt"
    if projection == "student":
        workspace = metadata.get("workspace", {}).get("student", "25mm")
        pieces.append(rf"\vspace{{{workspace}}}")
    elif projection == "answers":
        fragment_name = "answer"
        answer = component_fragment(entry, instance, "answer")
        if not answer:
            raise MathpubError(
                "MP-TEX-004", f"question has no answer: {metadata['id']}", exit_code=3
            )
        pieces.append(rf"\begin{{solution}}{answer}\end{{solution}}")
    elif projection in {"solutions", "validation"}:
        fragment_name = "solution"
        solution = component_fragment(entry, instance, "solution")
        if not solution:
            raise MathpubError(
                "MP-TEX-005", f"question has no solution: {metadata['id']}", exit_code=3
            )
        pieces.append(rf"\begin{{solution}}{solution}\end{{solution}}")
        if projection == "validation":
            pieces.append(validation_tex(instance))
    else:
        raise MathpubError("MP-TEX-006", f"unknown projection: {projection}", exit_code=3)
    return _marked_source(entry, fragment_name, "\n".join(pieces))


def _component_metadata(entry: Entry) -> tuple[str, dict[str, str]]:
    if entry.kind == "question":
        metadata = entry.metadata
        return "question", {
            name: metadata[name] for name in ("prompt", "answer", "solution") if metadata.get(name)
        }
    return entry.metadata["kind"], entry.metadata.get("fragments", {})


def component_fragment(entry: Entry, instance: dict[str, Any], name: str) -> str:
    """Read and expand one declared component fragment."""
    _, fragments = _component_metadata(entry)
    source = fragments.get(name)
    if not source:
        return ""
    rendered = expand(
        (entry.path / source).read_text(encoding="utf-8"),
        instance,
        entry.metadata["id"],
    )
    mode = entry.metadata.get("fragment_modes", {}).get(name, "mixed-tex")
    source_path = entry.path / source
    validate_fragment_source(rendered, mode, source_path)
    if mode == "math":
        return rf"\({rendered.strip()}\)"
    if mode == "plain-text":
        return _tex_escape(rendered)
    return rendered


def _marked_source(entry: Entry, fragment: str, rendered: str) -> str:
    """Mark generated TeX with the authored fragment that produced it."""
    _, fragments = _component_metadata(entry)
    source = fragments.get(fragment)
    authored = entry.path / source if source else entry.path / "component.toml"
    marker = json.dumps(
        {
            "component_id": entry.metadata["id"],
            "fragment": fragment,
            "authored_source": str(authored),
        },
        ensure_ascii=True,
        sort_keys=True,
    )
    return "\n".join((f"{SOURCE_BEGIN}{marker}", rendered, SOURCE_END))


def component_tex(
    entry: Entry,
    instance: dict[str, Any],
    projection: str,
    *,
    phase: str = "body",
    workspace: str | None = None,
    style: str = "mathpub",
    response: str = "workspace",
    emphasize_answer: bool = False,
) -> str:
    """Render one component instance for its placement phase."""
    kind, _ = _component_metadata(entry)
    title = entry.metadata.get("title", "")
    if kind == "question":
        if phase == "prompt":
            prompt = component_fragment(entry, instance, "prompt")
            student_workspace = workspace or entry.metadata.get("workspace", {}).get(
                "student", "12mm"
            )
            if style == "anna" and response == "truth-blank":
                return _marked_source(
                    entry,
                    "prompt",
                    rf"\item \rule{{0.65in}}{{0.4pt}}\quad {prompt}"
                    rf"\par\vspace{{{student_workspace}}}",
                )
            if style == "anna" and response == "answer-line":
                return _marked_source(
                    entry,
                    "prompt",
                    rf"\item {prompt}\hfill\rule{{0.48\linewidth}}{{0.4pt}}"
                    rf"\par\vspace{{{student_workspace}}}",
                )
            return _marked_source(
                entry,
                "prompt",
                rf"\item {prompt}\par\vspace{{{student_workspace}}}",
            )
        fragment_name = "answer" if phase == "answer" else "solution"
        rendered = component_fragment(entry, instance, fragment_name)
        if style == "anna" and phase == "answer" and emphasize_answer:
            rendered = rf"\annaanswer{{{rendered}}}"
        elif style == "anna" and phase != "answer":
            solution = re.fullmatch(
                r"\s*(.*?)\.\s*\\textbf\{Explanation:\}\s*(.*)\s*",
                rendered,
                flags=re.DOTALL,
            )
            if solution:
                answer, explanation = solution.groups()
                short_answer = component_fragment(entry, instance, "answer").strip()
                if short_answer.endswith("."):
                    answer += "."
                answer = rf"\annaanswer{{{answer}}}" if emphasize_answer else answer
                rendered = rf"{answer}\\*\textit{{Explanation:}} {explanation}"
            elif emphasize_answer:
                short_answer = component_fragment(entry, instance, "answer").strip()
                leading_space = rendered[: len(rendered) - len(rendered.lstrip())]
                body = rendered[len(leading_space) :]
                if short_answer and body.startswith(short_answer):
                    emphasized = short_answer[:-1] if short_answer.endswith(".") else short_answer
                    rendered = (
                        rf"{leading_space}\annaanswer{{{emphasized}}}" + body[len(emphasized) :]
                    )
                else:
                    leading_answer = re.fullmatch(r"\s*(\S+)(\s+.*)?", rendered, flags=re.DOTALL)
                    if leading_answer:
                        answer, remainder = leading_answer.groups()
                        if answer.endswith(".") and answer.count(".") == 1:
                            answer = answer[:-1]
                        rendered = rf"\annaanswer{{{answer}}}{remainder or ''}"
                    else:
                        rendered = rf"\annaanswer{{{rendered}}}"
        if phase == "validation":
            rendered = "\n".join((rendered, validation_tex(instance)))
        return _marked_source(entry, fragment_name, rf"\item {rendered}")
    if kind == "example":
        if body := component_fragment(entry, instance, "body"):
            opening = (
                rf"\begin{{annaexample}}{{{title}}}"
                if style == "anna"
                else rf"\begin{{workedexample}}[{title}]"
            )
            closing = r"\end{annaexample}" if style == "anna" else r"\end{workedexample}"
            rendered = "\n".join(
                (
                    opening,
                    _marked_source(entry, "body", body),
                    closing,
                )
            )
            if projection == "validation":
                rendered = "\n".join((rendered, validation_tex(instance)))
            return rendered
        opening = (
            rf"\begin{{annaexample}}{{{title}}}"
            if style == "anna"
            else rf"\begin{{workedexample}}[{title}]"
        )
        closing = r"\end{annaexample}" if style == "anna" else r"\end{workedexample}"
        parts = [
            opening,
            r"\textbf{Problem.}",
            _marked_source(entry, "prompt", component_fragment(entry, instance, "prompt")),
        ]
        if thought_process := component_fragment(entry, instance, "thought_process"):
            parts.extend(
                (
                    r"\textbf{Thought Process.}",
                    _marked_source(entry, "thought_process", thought_process),
                )
            )
        if steps := component_fragment(entry, instance, "steps"):
            parts.append(_marked_source(entry, "steps", steps))
        parts.extend(
            (
                r"\textbf{Answer.}",
                _marked_source(entry, "result", component_fragment(entry, instance, "result")),
            )
        )
        if check := component_fragment(entry, instance, "check"):
            parts.extend((r"\textbf{Check.}", _marked_source(entry, "check", check)))
        if projection == "validation":
            parts.append(validation_tex(instance))
        parts.append(closing)
        return "\n".join(parts)
    if kind == "concept":
        return _marked_source(entry, phase, component_fragment(entry, instance, phase))
    if kind == "misconception":
        if body := component_fragment(entry, instance, "body"):
            if style == "anna":
                rendered = rf"\begin{{annamistakes}}{{{title}}}{body}\end{{annamistakes}}"
            else:
                rendered = rf"\subsection*{{{title}}}{body}"
            return _marked_source(entry, "body", rendered)
        body = " ".join(
            filter(
                None,
                (
                    component_fragment(entry, instance, "wrong"),
                    component_fragment(entry, instance, "diagnosis"),
                    component_fragment(entry, instance, "correction"),
                    component_fragment(entry, instance, "body"),
                ),
            )
        )
        return _marked_source(entry, "body", rf"\item \textbf{{{title}.}} {body}")
    if kind == "teaching-tip":
        body = component_fragment(entry, instance, "body")
        if style == "anna" and phase != "list-item":
            rendered = rf"\begin{{annatips}}{{{title}}}{body}\end{{annatips}}"
        else:
            rendered = rf"\item \textbf{{{title}.}} {body}" if phase == "list-item" else body
        return _marked_source(entry, "body", rendered)
    if kind == "objective":
        body = component_fragment(entry, instance, "body")
        if style == "anna" and phase != "list-item":
            rendered = rf"\begin{{learningbox}}[{title}]{body}\end{{learningbox}}"
        else:
            rendered = rf"\item {body}" if phase == "list-item" else body
        return _marked_source(entry, "body", rendered)
    if kind == "self-assessment" and style == "anna":
        body = component_fragment(entry, instance, "body")
        self_title = title if title.startswith("Unit ") else "Self-Assessment"
        return _marked_source(
            entry,
            "body",
            rf"\begin{{annaboxenv}}{{{self_title}}}{body}\end{{annaboxenv}}",
        )
    rendered = component_fragment(entry, instance, "body")
    if projection == "validation" and instance.get("checks"):
        rendered = "\n".join((rendered, validation_tex(instance)))
    return _marked_source(entry, "body", rendered)


def document_tex(
    publication: dict[str, Any], projection: str, questions: list[str], font_family: str
) -> str:
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
{NUMBER_SET_PREAMBLE}
{font_preamble(font_family)}
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


def textbook_tex(
    publication: dict[str, Any], projection: str, chapters: list[str], font_family: str
) -> str:
    """Render a hierarchical textbook while preserving answer projection boundaries."""
    if publication.get("style") == "anna":
        return anna_textbook_tex(publication, projection, chapters)
    paper = "a4paper" if publication.get("paper") == "a4" else "letterpaper"
    projection_label = {
        "student": "Student Text",
        "answers": "Text with Short Answers",
        "solutions": "Teacher Edition",
        "validation": "Validation Edition",
        "parent": "Tutor and Homeschool Parent Edition",
    }[projection]
    title = publication["title"]
    author = publication.get("author", "")
    anna_style = publication.get("style") == "anna"
    document_class = "article" if anna_style else "book"
    opening = (
        ""
        if anna_style
        else rf"""\frontmatter
\begin{{titlepage}}\centering\vspace*{{1.2in}}
{{\Huge\bfseries {title}\par}}\vspace{{0.25in}}
{{\Large {publication.get("subtitle", "")}\par}}\vspace{{0.4in}}
{{\large {projection_label}\par}}\vfill
{{\large {author}\par}}\end{{titlepage}}
\tableofcontents
\mainmatter"""
    )
    return rf"""\documentclass[11pt,{paper}]{{{document_class}}}
\usepackage[margin=0.85in]{{geometry}}
\usepackage{{amsmath,amssymb,mathtools}}
{NUMBER_SET_PREAMBLE}
{font_preamble(font_family)}
\usepackage[per-mode=symbol]{{siunitx}}
\usepackage{{tikz,microtype,xcolor,enumitem,fancyhdr}}
\definecolor{{lessonblue}}{{HTML}}{{244A73}}
\definecolor{{exampleblue}}{{HTML}}{{EAF2F8}}
\definecolor{{exercisegray}}{{HTML}}{{F2F3F4}}
\setlength\parindent{{0pt}}
\setlength\parskip{{5pt}}
\setlist[enumerate]{{itemsep=6pt}}
\newenvironment{{workedexample}}[1][Worked Example]{{\par\medskip\noindent
  \begin{{minipage}}{{\linewidth}}\setlength{{\parindent}}{{0pt}}
  \vrule width 1.2pt\hspace{{0.7em}}\begin{{minipage}}{{0.94\linewidth}}
  \textbf{{#1}}\par\smallskip}}{{\end{{minipage}}\end{{minipage}}\par\medskip}}
\newenvironment{{exercises}}{{\section*{{Exercises}}\begin{{enumerate}}[leftmargin=*,label=\arabic*.]}}{{\end{{enumerate}}}}
\newenvironment{{lessonanswers}}[1]{{\section*{{#1}}\begin{{enumerate}}[leftmargin=*,label=\arabic*.]}}{{\end{{enumerate}}}}
\newcommand{{\keyidea}}[1]{{\par\smallskip\noindent
  \fcolorbox{{lessonblue}}{{exampleblue}}{{\parbox{{0.94\linewidth}}{{\textbf{{Key idea.}} #1}}}}
  \par\smallskip}}
\newcommand{{\answerkeytitle}}[1]{{\subsection*{{Answer Key: #1}}}}
\newcommand{{\problempart}}[1]{{\subsection*{{#1}}}}
\newcommand{{\annachapter}}[2]{{\clearpage\begin{{center}}
  {{\LARGE\bfseries Chapter #1}}\\[6pt]\rule{{\linewidth}}{{1.1pt}}\\[7pt]
  {{\Large\itshape #2}}\\[7pt]\rule{{\linewidth}}{{1.1pt}}
\end{{center}}}}
\newcommand{{\annapractice}}[2]{{\clearpage\begin{{center}}
  {{\LARGE\bfseries #1}}\\[6pt]{{\Large\bfseries #2}}
\end{{center}}}}
\newenvironment{{learningbox}}{{\par\medskip\noindent
  \begin{{minipage}}{{\linewidth}}\hrule\smallskip\textbf{{What You Will Learn}}\par}}
  {{\smallskip\hrule\end{{minipage}}\par\medskip}}
\pagestyle{{fancy}}
\fancyhf{{}}
\fancyhead[LE,RO]{{\thepage}}
\fancyhead[LO]{{\nouppercase{{\rightmark}}}}
\fancyhead[RE]{{\nouppercase{{\leftmark}}}}
\begin{{document}}
{opening}
{chr(10).join(chapters)}
\end{{document}}
"""


def anna_textbook_tex(publication: dict[str, Any], projection: str, chapters: list[str]) -> str:
    """Render Anna's compact Computer Modern workbook design."""
    paper = "a4paper" if publication.get("paper") == "a4" else "letterpaper"
    return rf"""\documentclass[12pt,{paper}]{{article}}
\usepackage[margin=1in,headheight=0pt,headsep=0pt]{{geometry}}
\usepackage{{amsmath,amssymb,mathtools}}
{NUMBER_SET_PREAMBLE}
\usepackage{{tikz,xcolor,enumitem,microtype}}
\definecolor{{annagray}}{{gray}}{{0.94}}
\definecolor{{annadark}}{{gray}}{{0.20}}
\setlength{{\parindent}}{{1.5em}}
\setlength{{\parskip}}{{0pt}}
\setlist[itemize]{{label=\textbullet,itemsep=7pt,topsep=6pt}}
\setlist[enumerate]{{itemsep=8pt,topsep=6pt}}
\pagestyle{{plain}}
\raggedbottom
\newsavebox{{\annabox}}
\newenvironment{{annaboxenv}}[1]{{%
  \def\annaboxtitle{{#1}}%
  \begin{{lrbox}}{{\annabox}}\begin{{minipage}}{{0.935\linewidth}}\vspace{{8pt}}
  \setlength{{\parindent}}{{0pt}}}}
  {{\vspace{{1pt}}\end{{minipage}}\end{{lrbox}}%
  \par\medskip\noindent\begin{{tikzpicture}}
  \node[draw=annadark,rounded corners=10pt,fill=annagray,inner xsep=15pt,inner ysep=6pt] (b)
    {{\usebox{{\annabox}}}};
  \node[anchor=west,fill=annadark,rounded corners=4pt,text=white,
    font=\sffamily\bfseries\large,inner xsep=10pt,inner ysep=3pt]
    at ([xshift=12pt]b.north west) {{\annaboxtitle}};
  \end{{tikzpicture}}\par\medskip}}
\newenvironment{{learningbox}}[1][What You Will Learn]{{\begin{{annaboxenv}}{{#1}}}}
  {{\end{{annaboxenv}}}}
\newenvironment{{annadirections}}{{\begin{{annaboxenv}}{{Directions}}}}
  {{\end{{annaboxenv}}}}
\newenvironment{{annasummary}}[1]{{\begin{{annaboxenv}}{{#1}}}}
  {{\end{{annaboxenv}}}}
\newsavebox{{\annawarningbox}}
\newenvironment{{annamistakes}}[1]{{%
  \def\annawarningtitle{{#1}}%
  \begin{{lrbox}}{{\annawarningbox}}\begin{{minipage}}{{0.935\linewidth}}
  \vspace{{19pt}}\setlength{{\parindent}}{{0pt}}}}
  {{\end{{minipage}}\end{{lrbox}}%
  \par\medskip\noindent\begin{{tikzpicture}}
  \node[draw=black,line width=1.1pt,rounded corners=1.5pt,fill=white,
    inner xsep=15pt,inner ysep=8pt] (b) {{\usebox{{\annawarningbox}}}};
  \fill[black,rounded corners=1.5pt]
    (b.north west) rectangle ([yshift=-18pt]b.north east);
  \node[anchor=west,text=white,font=\sffamily\bfseries\normalsize]
    at ([xshift=15pt,yshift=-9pt]b.north west)
    {{\(\blacktriangle\) \annawarningtitle!}};
  \draw[black!25,line width=2pt]
    ([xshift=2pt,yshift=-3pt]b.south west) -- ([xshift=2pt,yshift=-3pt]b.south east);
  \end{{tikzpicture}}\par\medskip}}
\newsavebox{{\annatipsbox}}
\newenvironment{{annatips}}[1]{{%
  \def\annatipstitle{{#1}}%
  \begin{{lrbox}}{{\annatipsbox}}\begin{{minipage}}{{0.935\linewidth}}
  \vspace{{4pt}}\setlength{{\parindent}}{{0pt}}}}
  {{\vspace{{1pt}}\end{{minipage}}\end{{lrbox}}%
  \par\medskip\noindent\begin{{tikzpicture}}
  \node[draw=black,dash pattern=on 3pt off 3pt,line width=0.8pt,
    rounded corners=3pt,fill=white,inner xsep=15pt,inner ysep=8pt] (b)
    {{\usebox{{\annatipsbox}}}};
  \node[anchor=center,draw=black,rounded corners=2pt,fill=annagray,
    font=\sffamily\bfseries\large,inner xsep=9pt,inner ysep=2pt]
    at (b.north) {{\(\checkmark\)\annatipstitle}};
  \end{{tikzpicture}}\par\medskip}}
\newenvironment{{annaexample}}[1]{{\par\medskip\noindent
  \begin{{minipage}}{{\linewidth}}\setlength{{\parindent}}{{0pt}}
  \vrule width 1.2pt\hspace{{0.8em}}\begin{{minipage}}{{0.94\linewidth}}
  {{\sffamily\bfseries #1}}\par\smallskip}}
  {{\end{{minipage}}\end{{minipage}}\par\medskip}}
\newcommand{{\annachapter}}[2]{{\clearpage\thispagestyle{{plain}}\vspace*{{0.39in}}
  \begin{{center}}{{\Huge\sffamily\bfseries Chapter #1}}\par\vspace{{7pt}}
  \hrule height 1.1pt\vspace{{9pt}}
  {{\LARGE\sffamily\itshape #2}}\par\vspace{{9pt}}\hrule height 1.1pt
  \end{{center}}\vspace{{-2pt}}}}
\newcommand{{\annapractice}}[2]{{\clearpage\thispagestyle{{plain}}\vspace*{{0.32in}}
  \begin{{center}}{{\Huge\sffamily\bfseries #1}}\par\vspace{{12pt}}
  \hrule height 1.1pt\vspace{{9pt}}
  {{\LARGE\sffamily\itshape #2}}\par\vspace{{9pt}}\hrule height 1.1pt
  \end{{center}}\vspace{{27pt}}}}
\newcommand{{\annaproblemset}}[2]{{\clearpage\thispagestyle{{plain}}\vspace*{{0.32in}}
  \begin{{center}}{{\Huge\sffamily\bfseries Problem Set #1}}\par\vspace{{12pt}}
  \hrule height 1.1pt\vspace{{9pt}}
  {{\LARGE\sffamily\itshape #2}}\par\vspace{{9pt}}\hrule height 1.1pt
  \end{{center}}\vspace{{42pt}}}}
\newcommand{{\answerkeytitle}}[1]{{\begin{{center}}
  {{\LARGE\sffamily\bfseries Answer Key: #1}}\end{{center}}\vspace{{4pt}}
  \hrule height 1.1pt\vspace{{20pt}}}}
\newcommand{{\problempart}}[1]{{\par\medskip\noindent{{\bfseries #1}}\par\smallskip}}
\newcommand{{\annaanswer}}[1]{{{{\bfseries\boldmath #1}}}}
\newenvironment{{workedexample}}[1][Worked Example]{{\begin{{annaexample}}{{#1}}}}
  {{\end{{annaexample}}}}
\newenvironment{{exercises}}{{\section*{{Exercises}}\begin{{enumerate}}}}
  {{\end{{enumerate}}}}
\newenvironment{{lessonanswers}}[1]{{\section*{{#1}}\begin{{enumerate}}}}
  {{\end{{enumerate}}}}
\newcommand{{\keyidea}}[1]{{\textbf{{Key idea.}} #1}}
\begin{{document}}
{chr(10).join(chapters)}
\end{{document}}
"""


def compile_pdf(
    tex_path: Path,
    output_dir: Path,
    font_family: str,
    tex_engine: str = "lualatex",
    *,
    projection: str | None = None,
    source_map: list[dict[str, Any]] | None = None,
    generated_source: str | None = None,
    source_map_file: str | None = None,
) -> tuple[Path, Path]:
    engine = f"-{tex_engine}"
    log_path = output_dir / f"{tex_path.stem}.build.log"
    command = [
        "latexmk",
        engine,
        "-synctex=1",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-file-line-error",
        f"-outdir={output_dir}",
        str(tex_path),
    ]
    try:
        process = subprocess.run(
            command,
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
    except subprocess.TimeoutExpired as error:
        transcript = timeout_transcript(error)
        log_path.write_text(transcript, encoding="utf-8")
        details: dict[str, Any] = {
            "engine": tex_engine,
            "projection": projection,
            "generated_source": generated_source or str(tex_path),
            "generated_line": None,
            "diagnostic": "TeX compilation timed out after 180 seconds",
            "timeout_seconds": 180,
            "log": str(log_path),
        }
        if source_map_file:
            details["source_map"] = source_map_file
        raise MathpubError(
            "MP-TEX-007",
            f"TeX compilation timed out after 180 seconds in "
            f"{projection or 'unknown projection'}; see {log_path}",
            exit_code=6,
            details=details,
        ) from error
    log_path.write_text(process.stdout + "\n" + process.stderr, encoding="utf-8")
    pdf_path = output_dir / f"{tex_path.stem}.pdf"
    if process.returncode or not pdf_path.is_file():
        transcript = process.stdout + "\n" + process.stderr
        file_error = re.search(r"(?m)^.*?\.tex:(\d+):\s*(.+)$", transcript)
        bang_error = re.search(r"(?m)^!\s*(.+)$", transcript)
        line_hint = re.search(r"(?m)^l\.(\d+)\s", transcript)
        generated_line = int(file_error.group(1)) if file_error else None
        if generated_line is None and line_hint:
            generated_line = int(line_hint.group(1))
        diagnostic = (
            file_error.group(2).strip()
            if file_error
            else bang_error.group(1).strip()
            if bang_error
            else "TeX engine exited without producing a PDF"
        )
        details: dict[str, Any] = {
            "engine": tex_engine,
            "projection": projection,
            "generated_source": generated_source or str(tex_path),
            "generated_line": generated_line,
            "diagnostic": diagnostic,
            "log": str(log_path),
        }
        if source_map_file:
            details["source_map"] = source_map_file
        if generated_line is not None:
            lines = tex_path.read_text(encoding="utf-8").splitlines()
            start = max(0, generated_line - 3)
            end = min(len(lines), generated_line + 2)
            details["excerpt"] = [
                {"line": index + 1, "text": lines[index]} for index in range(start, end)
            ]
            matching = next(
                (
                    item
                    for item in source_map or []
                    if item["generated_start_line"] <= generated_line <= item["generated_end_line"]
                ),
                None,
            )
            if matching:
                details.update(
                    {
                        "component_id": matching["component_id"],
                        "fragment": matching["fragment"],
                        "authored_source": matching["authored_source"],
                    }
                )
        location = details.get("authored_source", details["generated_source"])
        line_label = f" (generated line {generated_line})" if generated_line else ""
        raise MathpubError(
            "MP-TEX-007",
            f"TeX compilation failed in {projection or 'unknown projection'} at "
            f"{location}{line_label}: {diagnostic}; see {log_path}",
            exit_code=6,
            details=details,
        )
    normal_text_fallbacks = ("using `T1/cmr/m/n' instead", "using `OT1/cmr/m/n' instead")
    if any(warning in process.stdout for warning in normal_text_fallbacks):
        raise MathpubError("MP-TEX-009", f"font substitution detected; see {log_path}", exit_code=6)
    return pdf_path, log_path
