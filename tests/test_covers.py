import json

import pytest
from pypdf import PdfWriter

from mathpub.covers import check_cover, cover_geometry, prepare_cover
from mathpub.errors import MathpubError
from tests.test_print_export import edition


def spec_file(tmp_path):
    edition(tmp_path)
    path = tmp_path / "cover.toml"
    path.write_text("""schema=1
id="synthetic-stock-v1"
profile_date="2026-09-19"
interior_manifest="manifest.json"
projection="student"
trim_width_pt=432
trim_height_pt=648
spine_per_page_pt=0.16
bleed_pt=9
safe_pt=18
round_pages_to=2
barcode_box_pt=[30,30,100,70]
[printing]
format="paperback"
ink="BW"
paper="WHITE"
bleed=false
finish="MATTE"
""")
    return path


def test_cover_uses_actual_pages_and_rejects_proof_as_artwork(tmp_path):
    spec = spec_file(tmp_path)
    geometry = prepare_cover(spec, tmp_path / "prepared")
    assert geometry["interior"]["pages"] == 1
    assert geometry["production_pages"] == 2
    assert geometry["spine_pt"] == 0.32
    assert geometry["width_pt"] == 882.32
    with pytest.raises(MathpubError, match="not upload artwork"):
        check_cover(spec, tmp_path / "prepared/dimension-proof.pdf")
    writer = PdfWriter()
    writer.add_blank_page(geometry["width_pt"], geometry["height_pt"])
    artwork = tmp_path / "artwork.pdf"
    writer.write(artwork)
    assert check_cover(spec, artwork, tmp_path / "prepared/geometry.json")["passed"]
    prepared = tmp_path / "prepared/geometry.json"
    data = json.loads(prepared.read_text())
    data["interior"]["sha256"] = "stale"
    prepared.write_text(json.dumps(data))
    with pytest.raises(MathpubError, match="stale"):
        check_cover(spec, artwork, prepared)


def test_trim_and_barcode_policy_validation(tmp_path):
    spec = spec_file(tmp_path)
    spec.write_text(spec.read_text().replace("trim_width_pt=432", "trim_width_pt=400"))
    with pytest.raises(MathpubError, match="every interior"):
        cover_geometry(spec)
    spec.write_text(
        spec.read_text()
        .replace("trim_width_pt=400", "trim_width_pt=432")
        .replace("[30,30,100,70]", "[0,0,100,70]")
    )
    with pytest.raises(MathpubError, match="barcode"):
        cover_geometry(spec)
