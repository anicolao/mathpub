"""Optional English-paperback KDP adapter; existing drafts only, never publication."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from pypdf import PdfReader

from mathpub.config import load_toml
from mathpub.errors import MathpubError
from mathpub.releases import inside, sha256, verify_release
from mathpub.submissions import execute_submission, plan_hash

ADAPTER_VERSION = "kdp-paperback-en-v1"
SECTIONS = {"interior": "manuscript-upload", "cover": "cover-upload"}
ALERTS = {"interior": "success-alert", "cover": "hardcover-success-alert"}


def content_url(value: str) -> str:
    url = urlparse(value)
    if (
        url.scheme != "https"
        or url.netloc != "kdp.amazon.com"
        or url.query
        or url.fragment
        or not re.fullmatch(r"/[^?#]*/paperback/[A-Za-z0-9_-]+/content/?", url.path)
    ):
        raise MathpubError("MP-KDP-001", "expected an exact HTTPS KDP paperback content URL")
    return value


def create_plan(release: Path, book_id: str, config_path: Path, output: Path) -> dict:
    config = load_toml(config_path, "kdp")
    content_url(config["url"])
    report = verify_release(release)
    try:
        books = [book for book in report["books"] if book["id"] == book_id]
        if len(books) != 1 or not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", book_id):
            raise ValueError("book must resolve uniquely in the verified release")
        artifacts = {item["role"]: item for item in books[0]["artifacts"]}
        selected = [artifacts[role] for role in ("interior", "cover")]
        if not all(item.get("receipt_sha256") for item in selected):
            raise ValueError("both upload artifacts must have verified print-export receipts")
        geometry = artifacts["cover"].get("cover")
        if (
            not geometry
            or geometry["interior"]["sha256"] != artifacts["interior"]["source_artifact_sha256"]
        ):
            raise ValueError("cover is not linked to this exact interior")
        printing = geometry["profile"]["printing"]
        if printing["format"] != "paperback":
            raise ValueError("only existing paperback drafts are supported")
        identities, files = [], []
        for item in selected:
            path = inside(release, item["path"])
            reader = PdfReader(path)
            metadata = reader.metadata or {}
            if metadata.get("/MathpubArtifactRole") == "proof":
                raise ValueError("proof artifacts cannot be uploaded")
            identity = json.loads(metadata["/MathpubIdentity"])
            if identity["id"] != book_id or not identity.get("isbn"):
                raise ValueError("canonical identity and an explicit ISBN are required")
            if (
                metadata.get("/Title") != identity["title"]
                or metadata.get("/Author") != identity["author"]
            ):
                raise ValueError("formal PDF metadata drifts from canonical identity")
            identities.append(identity)
            files.append(
                {
                    "role": item["role"],
                    "path": str(path),
                    "sha256": item["sha256"],
                    "bytes": item["bytes"],
                    "filename": f"{book_id}-{item['role']}-{item['sha256']}.pdf",
                }
            )
        if identities[0] != identities[1]:
            raise ValueError("cover and interior identity differ")
        profile_dir = (config_path.parent / config["profile_dir"]).resolve()
        plan = {
            "schema": 1,
            "adapter": ADAPTER_VERSION,
            "book": book_id,
            "release": str(release.resolve()),
            "release_sha256": sha256((release / "release.json").read_bytes()),
            "source": artifacts["interior"]["stamp"]["source"],
            "identity": identities[0],
            "target": {
                "url": config["url"],
                "title": identities[0]["title"],
                "isbn": identities[0]["isbn"],
                "account": config["account_text"],
                "ink": f"{printing['ink']}_{printing['paper']}",
                "bleed": printing["bleed"],
                "finish": printing["finish"],
                "cover_mode": "UPLOAD",
                "trim_in": [
                    geometry["profile"]["trim_width_pt"] / 72,
                    geometry["profile"]["trim_height_pt"] / 72,
                ],
            },
            "browser": {**config, "profile_dir": str(profile_dir)},
            "files": files,
            "outcome": "Persist existing draft filenames; do not approve, order, price or publish.",
        }
        plan["sha256"] = plan_hash(plan)
        with output.open("x") as file:
            json.dump(plan, file, indent=2, sort_keys=True)
            file.write("\n")
        return plan
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise MathpubError("MP-KDP-001", f"cannot prepare submission plan: {error}") from error


class KDPBrowser:
    """Versioned DOM boundary. Unfamiliar controls, accounts and locales fail closed."""

    def __init__(self):
        self.runtime = self.context = self.page = None

    def open(self, plan):
        from playwright.sync_api import sync_playwright

        self.plan = plan
        config = plan["browser"]
        self.runtime = sync_playwright().start()
        self.context = self.runtime.chromium.launch_persistent_context(
            config["profile_dir"],
            headless=False,
            locale="en-US",
            executable_path=config.get("browser_executable"),
        )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.set_default_timeout(30000)
        self.page.goto(content_url(plan["target"]["url"]), wait_until="domcontentloaded")

    def observe(self):
        page, target = self.page, self.plan["target"]
        if page.url != target["url"]:
            raise MathpubError(
                "MP-KDP-002", "login expired or browser is on the wrong draft; sign in and resume"
            )
        title = page.locator("h1").inner_text().strip()
        account = page.locator(self.plan["browser"]["account_selector"]).inner_text().strip()
        isbn_type = page.locator('input[name="isbn-type"]:checked').input_value()
        if isbn_type == "FREE":
            match = re.search(r"ISBN:\s*([0-9-]{13,17})", page.locator("body").inner_text())
            isbn = match[1].replace("-", "") if match else None
        else:
            isbn = (
                page.get_by_role("textbox", name="ISBN", exact=True).input_value().replace("-", "")
            )
        trim_text = page.get_by_role("combobox", name="Trim Size", exact=True).evaluate(
            "e => e.tagName === 'SELECT' ? e.selectedOptions[0]?.textContent || '' : e.innerText"
        )
        trim = re.search(r"(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*in", trim_text)
        observed = {
            "url": page.url,
            "title": title,
            "account": account,
            "isbn": isbn,
            "ink": page.locator('input[id^="ink-paper-"]:checked').input_value(),
            "bleed": page.locator("#bleed-yes").is_checked(),
            "finish": page.locator('input[name="cover-finish"]:checked').input_value(),
            "cover_mode": page.locator('input[name="cover-choice"]:checked').input_value(),
            "trim_in": [float(trim[1]), float(trim[2])] if trim else None,
        }
        filenames = {}
        for item in self.plan["files"]:
            panel = page.locator(f'[data-testid="{SECTIONS[item["role"]]}"]').inner_text()
            filenames[item["role"]] = item["filename"] if item["filename"] in panel else None
        return {"target": observed, "filenames": filenames}

    def stage(self, item, path):
        # Native local-file transport avoids whole-PDF base64 messages and payload logging.
        self.page.evaluate("""() => {
          document.querySelector('#mathpub-staged-upload')?.remove();
          const input=document.createElement('input'); input.type='file';
          input.id='mathpub-staged-upload';input.hidden=true;document.body.append(input);
        }""")
        self.page.locator("#mathpub-staged-upload").set_input_files(str(path.resolve()))
        return self.page.evaluate("""async () => {
          const file=document.querySelector('#mathpub-staged-upload').files[0];
          const digest=await crypto.subtle.digest('SHA-256',await file.arrayBuffer());
          return {bytes:file.size,sha256:Array.from(new Uint8Array(digest))
            .map(b=>b.toString(16).padStart(2,'0')).join('')};
        }""")

    def submit(self, item):
        self.page.evaluate(
            """({url,selector}) => {
          if(location.href!==url) throw new Error('Wrong draft');
          const target=document.querySelector(selector);
          const source=document.querySelector('#mathpub-staged-upload');
          if(!target || !source?.files?.length) throw new Error('Missing file control');
          const transfer=new DataTransfer();transfer.items.add(source.files[0]);
          target.files=transfer.files;target.dispatchEvent(new Event('input',{bubbles:true}));
          target.dispatchEvent(new Event('change',{bubbles:true}));source.remove();
        }""",
            {
                "url": self.plan["target"]["url"],
                "selector": f'[data-testid="{SECTIONS[item["role"]]}"] input[type=file]',
            },
        )

    def acknowledge(self, item):
        self.page.wait_for_function(
            """({url,selector,name}) => {
          if(location.href!==url) throw new Error('Wrong draft');
          const text=document.querySelector(selector)?.innerText||'';
          return text.includes(name)&&text.includes('uploaded successfully!');
        }""",
            arg={
                "url": self.plan["target"]["url"],
                "selector": (
                    f'[data-testid="{SECTIONS[item["role"]]}"] '
                    f'[data-testid="{ALERTS[item["role"]]}"]'
                ),
                "name": item["filename"],
            },
            timeout=self.plan["browser"].get("timeout_seconds", 600) * 1000,
        )

    def save(self):
        button = self.page.get_by_role("button", name="Save as Draft", exact=True)
        enabled = button.is_enabled()
        if enabled:
            button.click()
            self.page.wait_for_timeout(5000)
        return enabled

    def reload(self):
        self.page.reload(wait_until="domcontentloaded")
        self.page.get_by_role("heading", name=self.plan["target"]["title"], exact=True).wait_for()
        for item in self.plan["files"]:
            self.page.get_by_text(item["filename"], exact=False).wait_for(timeout=30000)

    def screenshot(self, path):
        self.page.screenshot(path=str(path), full_page=True)

    def close(self):
        if self.context is not None:
            self.context.close()
        if self.runtime is not None:
            self.runtime.stop()


def upload_draft(
    plan_path: Path, output: Path, *, resume=False, retry_uncertain=False, adapter=None
) -> dict:
    try:
        plan = json.loads(plan_path.read_text())
        if plan["adapter"] != ADAPTER_VERSION or plan["sha256"] != plan_hash(plan):
            raise ValueError("unsupported or modified submission plan")
        content_url(plan["target"]["url"])
        release = Path(plan["release"])
        release_report = verify_release(release)
        if sha256((release / "release.json").read_bytes()) != plan["release_sha256"]:
            raise ValueError("release index changed after planning")
        if [file["role"] for file in plan["files"]] != ["interior", "cover"]:
            raise ValueError("submission must contain exactly an interior and cover")
        books = [book for book in release_report["books"] if book["id"] == plan["book"]]
        if len(books) != 1:
            raise ValueError("planned book is not in the release")
        artifacts = {item["role"]: item for item in books[0]["artifacts"]}
        for file in plan["files"]:
            if Path(file["filename"]).name != file["filename"]:
                raise ValueError("unsafe staged filename")
            if not Path(file["path"]).resolve().is_relative_to(release.resolve()):
                raise ValueError("upload file is outside the verified release")
            expected = artifacts[file["role"]]
            if (
                file["sha256"] != expected["sha256"]
                or file["bytes"] != expected["bytes"]
                or Path(file["path"]).resolve() != inside(release, expected["path"])
                or file["filename"] != f"{plan['book']}-{file['role']}-{file['sha256']}.pdf"
            ):
                raise ValueError("planned upload does not match its verified artifact role")
        return execute_submission(
            plan, output, adapter or KDPBrowser(), resume=resume, retry_uncertain=retry_uncertain
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise MathpubError("MP-KDP-001", f"invalid submission: {error}") from error


def login(config_path: Path) -> dict:
    from playwright.sync_api import sync_playwright

    config = load_toml(config_path, "kdp")
    url = content_url(config["url"])
    profile = (config_path.parent / config["profile_dir"]).resolve()
    try:
        with sync_playwright() as runtime:
            context = runtime.chromium.launch_persistent_context(
                str(profile),
                headless=False,
                locale="en-US",
                executable_path=config.get("browser_executable"),
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(url, wait_until="domcontentloaded")
            print(
                "Sign in manually, including MFA if requested, then close the browser window.",
                file=sys.stderr,
            )
            closed = []
            context.on("close", lambda *_: closed.append(True))
            while not closed:
                try:
                    page.wait_for_timeout(500)
                except Exception:
                    if not closed:
                        raise
            return {
                "profile_dir": str(profile),
                "status": "browser-closed",
                "note": "Authentication will be checked when uploading; no draft was modified.",
            }
    except Exception as error:
        raise MathpubError(
            "MP-KDP-002", "browser login session ended unexpectedly; retry setup"
        ) from error
