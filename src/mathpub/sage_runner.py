"""Executed by Sage's Python to produce one canonical question instance."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# The installed script lives inside a Python 3.12 package while Sage uses its
# own Python. Remove foreign binary-package paths, then make only mathpub's
# pure-Python package discoverable after Sage's native packages.
sys.path[:] = [path for path in sys.path if "python3.12" not in path]
sys.path.append(str(Path(__file__).resolve().parent.parent))

from mathpub.question import (  # noqa: E402
    CheckFailed,
    Context,
    RandomContext,
    Rejected,
    seed_for,
    take_generator,
)


def execute(request: dict) -> dict:
    import sage.all as sage_all
    from sage.repl.preparse import preparse_file

    source = Path(request["generator"]).read_text(encoding="utf-8")
    rejections: dict[str, int] = {}
    for attempt in range(request["max_attempts"]):
        namespace = vars(sage_all).copy()
        try:
            exec(compile(preparse_file(source), request["generator"], "exec"), namespace)
            function = take_generator()
            context = Context(
                RandomContext(
                    seed_for(
                        request["root_seed"],
                        request["variant"],
                        request.get("seed_key", request["question_id"]),
                        attempt,
                    )
                ),
                overrides=request.get("overrides"),
                variant=request["variant"],
                identifier=request["question_id"],
            )
            function(context)
            return {
                "schema": 1,
                "status": "ok",
                "question_id": request["question_id"],
                "attempt": attempt,
                "rng_algorithm": "pcg64-v1",
                **context.instance(),
                "rejections": rejections,
            }
        except Rejected as error:
            rejections[error.name] = rejections.get(error.name, 0) + 1
        except CheckFailed as error:
            return {"schema": 1, "status": "check-failed", "evidence": error.evidence}
    return {"schema": 1, "status": "exhausted", "rejections": rejections}


def main() -> int:
    request_path, output_path = map(Path, sys.argv[1:3])
    request = json.loads(request_path.read_text(encoding="utf-8"))
    try:
        result = execute(request)
    except Exception as error:  # runner boundary returns diagnostics to orchestrator
        result = {"schema": 1, "status": "error", "error": f"{type(error).__name__}: {error}"}
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
