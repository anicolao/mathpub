"""Narrow GUI publishing operations; paths stay in the currently open library."""

from __future__ import annotations

import json
from urllib.parse import quote, urlparse

from mathpub.errors import MathpubError
from mathpub.releases import inside


def trusted_request(headers: dict) -> bool:
    origin, host = headers.get("origin", ""), headers.get("host", "")
    return (
        headers.get("x-mathpub-publishing") == "1"
        and headers.get("content-type", "").split(";", 1)[0] == "application/json"
        and bool(origin)
        and urlparse(origin).netloc == host
        and urlparse(origin).hostname in ("localhost", "127.0.0.1", "::1")
        and urlparse(origin).scheme in ("http", "https")
    )


def publishing_operation(project, payload: dict) -> dict:
    def path(key):
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise MathpubError("MP-GUI-020", f"{key} must be a library-relative path")
        try:
            return inside(project.root, value)
        except ValueError as error:
            raise MathpubError(
                "MP-GUI-020", "publishing paths must stay inside the library"
            ) from error

    action = payload.get("action")
    if action == "review":
        from mathpub.edition_review import create_review, create_review_set

        result = (
            create_review_set(path("review_config"), path("output"), allowed_root=project.root)
            if payload.get("review_config")
            else create_review(
                path("before"),
                path("after"),
                path("output"),
                label=str(payload.get("label", "Edition comparison")),
                notes=str(payload.get("notes", "")),
                baseline_revision=str(payload.get("baseline_revision", "")),
                attachments=[path("attachment")] if payload.get("attachment") else [],
            )
        )
        return {
            "report": result,
            "url": "/api/tools/reviews/"
            + quote(str(path("output").relative_to(project.root) / "index.html")),
        }
    if action == "kdp-plan":
        from mathpub.kdp import create_plan

        return create_plan(
            path("release"), str(payload.get("book", "")), path("config"), path("output")
        )
    if action == "kdp-login":
        from mathpub.kdp import login

        return login(path("config"))
    if action == "kdp-upload":
        from mathpub.kdp import upload_draft

        plan_path = path("plan")
        plan = json.loads(plan_path.read_text())
        if payload.get("confirmation") != plan.get("sha256") or not plan.get("sha256"):
            raise MathpubError(
                "MP-GUI-020", "review and explicitly confirm this exact submission plan"
            )
        return upload_draft(
            plan_path,
            path("output"),
            resume=payload.get("resume") is True,
            retry_uncertain=payload.get("retry_uncertain") is True,
        )
    if action == "kdp-load-plan":
        from mathpub.submissions import plan_hash

        plan = json.loads(path("plan").read_text())
        if plan.get("sha256") != plan_hash(plan):
            raise MathpubError("MP-GUI-020", "invalid or modified submission plan")
        return plan
    raise MathpubError("MP-GUI-020", "unknown publishing operation")
