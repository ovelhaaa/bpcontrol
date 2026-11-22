"""M1J strictly read-only Music 3D/Plus, Stereo Widener and Exciter HID worker.

Usage is internal to a supervised GUI child process with a 15-second
deadline. This program exposes NO parameter writes, flash operations,
or arbitrary command input. A "read" query uses SET_REPORT only to
request data: ACP CMD LEN=0 (no parameter payload).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def read_once() -> dict:
    from bpcontrol.music_effects import read_music_live, normalize_music_values
    from bpcontrol.usb_snapshot import WindowsSnapshotSession

    with WindowsSnapshotSession() as session:
        observed = normalize_music_values(read_music_live(session))
    return {
        "status": "MUSIC_READ_OK",
        "effects": {str(k): list(values) for k, values in observed.items()},
        "note": "four firmware-gated, read-only ACP effect queries; no save or write",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read-four-music-effects", action="store_true", required=True,
                        help="read exactly 0x97, 0x98, 0x9B, 0x9D; no writes")
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        parser.error("live BP1032 Music read requires Windows")
    try:
        reply = read_once()
    except Exception as exc:
        # No parameter writes can originate from this module.
        reply = {"status": "MUSIC_READ_ERROR", "error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(reply, ensure_ascii=False, separators=(",", ":")), flush=True)
    return 0 if reply["status"] == "MUSIC_READ_OK" else 4


if __name__ == "__main__":
    raise SystemExit(main())
