"""Render a static, self-contained, OFFLINE BPControl snapshot explorer.

The generated HTML contains only snapshot JSON and local CSS/JavaScript.
It never opens a USB device, starts a server, or makes network requests.

Usage:
  py tools/render_snapshot.py artifacts/snapshots/bp1032.json --open
  py tools/render_snapshot.py data/demo_snapshot.json --open
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "ui" / "snapshot_template.html"
MARKER = "__BPCONTROL_JSON__"


def build_html(snapshot: dict, template_text: str) -> str:
    if snapshot.get("format") != "bpcontrol-snapshot-v1":
        raise ValueError("Not a BPControl snapshot v1")
    items = snapshot.get("effects")
    if not isinstance(items, list) or len(items) != 59:
        raise ValueError("Expected exactly 59 snapshot effect entries")
    if template_text.count(MARKER) != 1:
        raise ValueError("The UI template has no unique snapshot placeholder")
    json_text = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    # Secure insertion in application/json script: no literal tag terminators.
    json_text = json_text.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    return template_text.replace(MARKER, json_text)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Convert BPControl JSON snapshot into offline HTML")
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output", type=Path, help="HTML destination; default is snapshot filename + .html")
    parser.add_argument("--open", action="store_true", help="open generated HTML in your browser")
    args = parser.parse_args(argv)

    obj = json.loads(args.snapshot.read_text(encoding="utf-8"))
    html = build_html(obj, TEMPLATE.read_text(encoding="utf-8"))
    target = args.output or args.snapshot.with_suffix(".html")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("x", encoding="utf-8") as output:
            output.write(html)
    except FileExistsError:
        parser.error("HTML already exists; provide a new --output path (no overwrites)")
    print("Created offline HTML: " + str(target))
    print("Read-only UI: NO USB access, HTTP server, or remote dependencies.")
    if args.open:
        webbrowser.open(target.resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
