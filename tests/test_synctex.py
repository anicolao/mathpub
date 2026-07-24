"""Tests for SyncTeX parsing and source-map resolution."""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from mathpub.gui.synctex import SyncTeXError, parse_records, resolve_boxes


def _sp(value: int) -> int:
    return round(value * 65781.76)


def test_parses_exact_source_records_and_resolves_component_boxes(tmp_path):
    project_root = tmp_path / "project"
    generated_source = project_root / "build/demo/A/generated-tex/demo-A-student.tex"
    generated_source.parent.mkdir(parents=True)
    generated_lines = [f"generated line {line}" for line in range(1, 25)]
    generated_lines[21] = r"\end{center}"
    generated_source.write_text("\n".join(generated_lines))
    synctex_path = project_root / "build/demo/A/demo-A-student.synctex.gz"
    synctex_path.parent.mkdir(parents=True, exist_ok=True)
    fixture = "\n".join(
        [
            "SyncTeX Version:1",
            "Input:1:/temporary/build/demo-A-student.tex",
            "Input:2:/texlive/article.cls",
            "Output:pdf",
            "Magnification:1000",
            "Unit:1",
            "X Offset:0",
            "Y Offset:0",
            "Content:",
            "{1",
            f"[1,10:{_sp(1)},{_sp(1)}:{_sp(600)},{_sp(900)},0",
            f"(1,10:{_sp(100)},{_sp(200)}:{_sp(50)},{_sp(10)},{_sp(2)}",
            f"(1,12:{_sp(80)},{_sp(240)}:{_sp(100)},{_sp(8)},{_sp(2)}",
            f"(1,20:{_sp(60)},{_sp(300)}:{_sp(90)},{_sp(9)},{_sp(3)}",
            f"(1,22:{_sp(60)},{_sp(20)}:{_sp(400)},{_sp(10)},0",
            f"(2,10:{_sp(1)},{_sp(1)}:{_sp(1)},{_sp(1)},0",
            "}",
            "{2",
            f"(1,10:{_sp(5)},{_sp(5)}:{_sp(5)},{_sp(5)},0",
            "}",
            "Postamble:",
        ]
    )
    with gzip.open(synctex_path, "wt", encoding="utf-8") as stream:
        stream.write(fixture)

    records = parse_records(synctex_path, generated_source, page=1)
    assert [(record.line, record.x, record.y) for record in records] == [
        (10, 100.0, 190.0),
        (12, 80.0, 232.0),
        (20, 60.0, 291.0),
        (22, 60.0, 10.0),
    ]

    boxes = resolve_boxes(
        records,
        [
            {
                "component_id": "demo.first",
                "fragment": "prompt",
                "authored_source": "components/questions/demo/first/prompt.tex",
                "generated_start_line": 10,
                "generated_end_line": 12,
            },
            {
                "component_id": "demo.second",
                "fragment": "prompt",
                "authored_source": "components/questions/demo/second/prompt.tex",
                "generated_start_line": 20,
                "generated_end_line": 24,
            },
        ],
        project_root=project_root,
        generated_source=generated_source,
        page=1,
    )
    assert boxes[0] == {
        "component_id": "demo.first",
        "fragment": "prompt",
        "authored_source": "components/questions/demo/first/prompt.tex",
        "authored_source_absolute": str(
            project_root / "components/questions/demo/first/prompt.tex"
        ),
        "generated_source": "build/demo/A/generated-tex/demo-A-student.tex",
        "generated_start_line": 10,
        "generated_end_line": 12,
        "page": 1,
        "x": 80.0,
        "y": 190.0,
        "w": 100.0,
        "h": 52.0,
    }
    assert boxes[1]["component_id"] == "demo.second"
    assert boxes[1]["h"] == 12.0


def test_rejects_missing_generated_source(tmp_path):
    synctex_path = tmp_path / "document.synctex.gz"
    with gzip.open(synctex_path, "wt", encoding="utf-8") as stream:
        stream.write(
            "SyncTeX Version:1\n"
            "Input:1:/tmp/other.tex\n"
            "Magnification:1000\n"
            "Unit:1\n"
            "X Offset:0\n"
            "Y Offset:0\n"
            "Content:\n"
        )

    with pytest.raises(SyncTeXError, match="generated source is absent"):
        parse_records(synctex_path, Path("expected.tex"), page=1)
