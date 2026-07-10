"""Lightweight checks for the static app shell."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


def _read(name: str) -> str:
    path = STATIC / name
    assert path.exists(), f"missing static file: {path}"
    return path.read_text(encoding="utf-8")


def main() -> None:
    html = _read("index.html")
    css = _read("styles.css")
    js = _read("app.js")

    for asset_ref in ("/styles.css?v=", "/app.js?v="):
        assert asset_ref in html, f"missing asset ref: {asset_ref}"

    for dom_id in (
        "batchScriptCount",
        "scriptSubmitBtn",
        "continueGenerateScriptBtn",
        "regenerateScriptBtn",
        "scriptForm",
        "scriptCandidateList",
        "scriptDetailPanel",
        "creationPlanner",
        "continueGenerateScriptBtn",
    ):
        assert f'id="{dom_id}"' in html, f"missing DOM id: {dom_id}"

    for selector in (
        ".navMore",
        ".videoPlanWorkbench",
        ".drawerMoreActions",
        ".candidateCountControl",
        ".scriptTitleDetails",
        ".scriptReviewSummary",
    ):
        assert selector in css, f"missing CSS selector: {selector}"

    for js_token in (
        "#batchScriptCount",
        "#scriptCandidateList",
        "#scriptDetailPanel",
        "generateOneMoreScript",
    ):
        assert js_token in js, f"missing JS token: {js_token}"

    node = shutil.which("node")
    if node:
        subprocess.run([node, "--check", str(STATIC / "app.js")], check=True)

    print("frontend static smoke ok")


if __name__ == "__main__":
    main()
