"""Shared screenshot assertions for browser and native workspace E2E tests."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageChops


class GUIStepHelper:
    """Capture named GUI steps and enforce exact renderer baselines."""

    def __init__(self, scenario_dir: Path, update_baselines: bool = False) -> None:
        self.scenario_dir = scenario_dir
        self.screenshots_dir = scenario_dir / "screenshots"
        self.diffs_dir = scenario_dir / "diffs"
        self.update_baselines = update_baselines
        self.screenshots_dir.mkdir(exist_ok=True)
        self.diffs_dir.mkdir(exist_ok=True)

    def verify(self, page, name: str) -> None:
        baseline_path = self.screenshots_dir / f"{name}.png"
        candidate_path = self.scenario_dir / f"temp-{name}.png"
        page.screenshot(path=str(candidate_path))

        if self.update_baselines or not baseline_path.exists():
            candidate_path.replace(baseline_path)
            return

        candidate = Image.open(candidate_path).convert("RGB")
        baseline = Image.open(baseline_path).convert("RGB")
        diff = ImageChops.difference(candidate, baseline)
        candidate_path.unlink()
        if diff.getbbox() is not None:
            diff.save(self.diffs_dir / f"{name}-diff.png")
            raise AssertionError(
                f"Visual regression in WebKit GUI workspace layout!\nBaseline: {baseline_path}"
            )

    @staticmethod
    def verify_native_capture(png: bytes, artifact_path: Path) -> tuple[int, int]:
        """Validate and preserve a native-driver screenshot without cross-OS pixel claims."""
        image = Image.open(io.BytesIO(png)).convert("RGB")
        width, height = image.size
        if width < 960 or height < 600:
            raise AssertionError(f"native workspace screenshot is unexpectedly small: {image.size}")
        extrema = image.getextrema()
        if all(low == high for low, high in extrema):
            raise AssertionError("native workspace screenshot contains only a single color")
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(png)
        return image.size
