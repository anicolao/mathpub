import hashlib
import json
import os
import sys

import pytest
from pypdf import PdfWriter

from mathpub.covers import cover_geometry
from mathpub.errors import MathpubError
from mathpub.kdp import KDPBrowser, content_url, create_plan
from mathpub.print_export import POLICY, export_print
from mathpub.releases import assemble_release
from mathpub.submissions import execute_submission, plan_hash
from tests.test_covers import spec_file
from tests.test_submissions import submission_plan


@pytest.mark.parametrize(
    "url",
    [
        "http://kdp.amazon.com/en_US/title-setup/paperback/ABC/content",
        "https://evil.invalid/paperback/ABC/content",
        "https://kdp.amazon.com/en_US/title-setup/ebook/ABC/content",
        "https://kdp.amazon.com/en_US/title-setup/paperback/ABC/content?x=1",
    ],
)
def test_target_guard_rejects_wrong_site_format_and_ambiguous_urls(url):
    with pytest.raises(MathpubError):
        content_url(url)


def test_plan_requires_verified_pair_identity_and_manufacturing_profile(tmp_path):
    spec = spec_file(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    identity = {
        "schema": 1,
        "id": "synthetic.book",
        "title": "Synthetic Book",
        "author": "Test Author",
        "isbn": "9780306406157",
    }
    metadata = {
        "/MathpubIdentity": json.dumps(identity),
        "/Title": identity["title"],
        "/Author": identity["author"],
    }
    writer = PdfWriter(clone_from=tmp_path / "sample.pdf")
    writer.add_metadata(metadata)
    writer.write(tmp_path / "sample.pdf")
    manifest["identity"] = identity
    manifest["outputs"][1]["sha256"] = hashlib.sha256(
        (tmp_path / "sample.pdf").read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    geometry = cover_geometry(spec)
    writer = PdfWriter()
    writer.add_blank_page(geometry["width_pt"], geometry["height_pt"])
    stamp = {
        "schema": 1,
        "publication_id": "synthetic.cover",
        "projection": "student",
        "lesson_ids": [],
        "source": manifest["source"],
    }
    writer.add_metadata({**metadata, "/MathpubProvenance": json.dumps(stamp)})
    writer.write(tmp_path / "cover.pdf")
    cover_manifest = {
        **manifest,
        "publication_id": "synthetic.cover",
        "cover": geometry,
        "outputs": [
            {
                "projection": "student",
                "path": "cover.pdf",
                "pages": 1,
                "sha256": hashlib.sha256((tmp_path / "cover.pdf").read_bytes()).hexdigest(),
            }
        ],
    }
    (tmp_path / "cover-manifest.json").write_text(json.dumps(cover_manifest))
    export_print(manifest_path, "student", tmp_path / "print-interior", policy=POLICY)
    export_print(
        tmp_path / "cover-manifest.json", "student", tmp_path / "print-cover", policy=POLICY
    )
    config = tmp_path / "release.toml"
    config.write_text("""schema=1
id="test"
[[books]]
id="synthetic.book"
required_roles=["interior", "cover"]
[[books.artifacts]]
role="interior"
manifest="manifest.json"
projection="student"
receipt="print-interior/receipt.json"
[[books.artifacts]]
role="cover"
manifest="cover-manifest.json"
projection="student"
receipt="print-cover/receipt.json"
""")
    assemble_release(config, tmp_path / "release")
    kdp = tmp_path / "kdp.toml"
    kdp.write_text("""schema=1
locale="en-US"
url="https://kdp.amazon.com/en_US/title-setup/paperback/TEST/content"
profile_dir="browser-profile"
account_selector="#account"
account_text="Test Account"
""")
    plan = create_plan(tmp_path / "release", "synthetic.book", kdp, tmp_path / "plan.json")
    assert plan["target"]["trim_in"] == [6, 9]
    assert plan["target"]["ink"] == "BW_WHITE"
    assert [item["role"] for item in plan["files"]] == ["interior", "cover"]


def test_browser_transfer_verifies_large_file_before_retailer_change_event(tmp_path):
    if (
        not os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
        or os.environ.get("HOME") == "/homeless-shelter"
    ):
        pytest.skip("requires Nix-packaged browsers")
    from playwright.sync_api import sync_playwright

    url = "https://kdp.amazon.com/en_US/title-setup/paperback/TEST/content"
    fixture = """<input id="retailer" type="file"><script>
      window.submissions=0;document.querySelector('input').onchange=()=>window.submissions++;
      </script>"""
    with sync_playwright() as runtime:
        browser_type = runtime.webkit if sys.platform == "darwin" else runtime.chromium
        browser = browser_type.launch(headless=True)
        page = browser.new_page()
        page.route(
            "**/*", lambda route: route.fulfill(status=200, content_type="text/html", body=fixture)
        )
        page.goto(url)
        adapter = KDPBrowser()
        adapter.page = page
        adapter.plan = {"target": {"url": url}}
        payload = b"x" * (16 * 1024 * 1024)
        path = tmp_path / "large.pdf"
        path.write_bytes(payload)
        result = adapter.stage({"role": "interior"}, path)
        assert result == {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
        assert page.evaluate("window.submissions") == 0
        page.locator("#retailer").evaluate(
            "e=>{e.parentElement.dataset.testid='manuscript-upload'}"
        )
        adapter.submit({"role": "interior"})
        assert page.evaluate("window.submissions") == 1
        browser.close()


def test_versioned_browser_contract_and_autosave_persistence(tmp_path):
    if (
        not os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
        or os.environ.get("HOME") == "/homeless-shelter"
    ):
        pytest.skip("requires Nix-packaged browsers")
    from playwright.sync_api import sync_playwright

    url = "https://kdp.amazon.com/en_US/title-setup/paperback/TEST/content"
    markup = """<h1>Synthetic Book</h1><div id="account">Test Account</div>
    <input name="isbn-type" type="radio" value="OWN" checked>
    <input aria-label="ISBN" value="9780306406157">
    <select aria-label="Trim Size"><option>8 x 10 in</option>
    <option selected>6 x 9 in</option></select>
    <input id="ink-paper-bw" type="radio" value="BW_WHITE" checked>
    <input id="bleed-yes" name="bleed" type="radio">
    <input id="bleed-no" name="bleed" type="radio" checked>
    <input name="cover-choice" type="radio" value="UPLOAD" checked>
    <input name="cover-finish" type="radio" value="MATTE" checked>
    <button disabled>Save as Draft</button>
    <div data-testid="manuscript-upload"><input type="file">
    <p data-testid="success-alert"></p></div>
    <div data-testid="cover-upload"><input type="file">
    <p data-testid="hardcover-success-alert"></p></div>
    <script>document.querySelectorAll('[data-testid] input').forEach(input=>{
      const panel=input.parentElement,key=panel.dataset.testid;
      const show=()=>panel.querySelector('p').textContent=
        (localStorage.getItem(key)||'')+' uploaded successfully!';
      show();input.onchange=()=>{localStorage.setItem(key,input.files[0].name);show()};
    });</script>"""
    plan = submission_plan(tmp_path)
    plan["target"] = {
        "url": url,
        "title": "Synthetic Book",
        "account": "Test Account",
        "isbn": "9780306406157",
        "ink": "BW_WHITE",
        "bleed": False,
        "finish": "MATTE",
        "cover_mode": "UPLOAD",
        "trim_in": [6, 9],
    }
    plan["browser"] = {"account_selector": "#account", "timeout_seconds": 2}
    plan["sha256"] = plan_hash(plan)
    with sync_playwright() as runtime:
        browser_type = runtime.webkit if sys.platform == "darwin" else runtime.chromium
        browser = browser_type.launch(headless=True)
        page = browser.new_page()
        page.route(
            "**/*", lambda route: route.fulfill(status=200, content_type="text/html", body=markup)
        )
        page.goto(url)

        class FixtureBrowser(KDPBrowser):
            def open(self, plan):
                self.plan, self.page = plan, page

        receipt = execute_submission(plan, tmp_path / "attempt", FixtureBrowser())
        assert receipt["status"] == "draft-persisted"
        assert receipt["save_clicked"] is False
        page.goto("https://kdp.amazon.com/signin")
        adapter = FixtureBrowser()
        adapter.open(plan)
        with pytest.raises(MathpubError, match="login expired"):
            adapter.observe()
        browser.close()
