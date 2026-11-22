"""M1K-A offline-only staged Harmonic Exciter (0x9D) editor prototype.

Never opens USB/HID, never sends ACP packets, and never writes to flash.
Intended solely to preview staged numeric edits, ACP 0x9D packet hex, and
V2.40 vs BP1048 SDK vs operator-reported schema evidence offline.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bpcontrol.exciter_editor import (  # noqa: E402
    EXCITER_LIVE_WRITE_ENABLED,
    EXCITER_STAGED_BOUNDS,
    ExciterOfflineSession,
    assess_exciter_draft,
)
from bpcontrol.exciter_evidence import (  # noqa: E402
    EXCITER_AUDIT_FIELDS,
    EXCITER_INDEX,
)

DEFAULT_OFFLINE_BASELINE = (1, 1000, 80, 50)


def load_exciter_baseline(snapshot_path: Path) -> tuple[tuple[int, int, int, int], str]:
    """Load Exciter (index 29) raw values from a local snapshot if present."""
    if not snapshot_path.exists():
        return DEFAULT_OFFLINE_BASELINE, "Baseline sintético offline (sem snapshot)"
    try:
        data = json.loads(snapshot_path.read_text(encoding="utf-8"))
        for entry in data.get("effects", []):
            if entry.get("index") == EXCITER_INDEX and entry.get("status") == "ok":
                fields = entry.get("fields", [])
                if len(fields) == 4:
                    vals = tuple(int(f["signed"]) for f in fields)
                    return vals, f"Snapshot local: {snapshot_path.name}"  # type: ignore[return-value]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return DEFAULT_OFFLINE_BASELINE, f"Baseline sintético offline ({snapshot_path.name} sem leitura 0x9D)"


class ExciterOfflineEditorApp:
    def __init__(self, root: tk.Tk, snapshot_path: Path) -> None:
        self.root = root
        self.root.title("BPControl M1K-A — Exciter (0x9D) Staged Prototype [OFFLINE]")
        self.root.geometry("860x560")

        baseline, origin = load_exciter_baseline(snapshot_path)
        self.session = ExciterOfflineSession(baseline)
        self.origin_var = tk.StringVar(value=origin)
        self.field_var = tk.StringVar(value="cutoff_frequency")
        self.draft_var = tk.StringVar(value=str(baseline[1]))
        self.status_var = tk.StringVar(
            value=(
                "PROTÓTIPO OFFLINE M1K-A — Escrita USB desabilitada "
                f"(EXCITER_LIVE_WRITE_ENABLED={EXCITER_LIVE_WRITE_ENABLED})."
            )
        )
        self.preview_var = tk.StringVar(value="ACP preview: —")

        self._build_ui()
        self._refresh_table()
        self._update_preview()

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 6}
        banner = ttk.Label(
            self.root,
            text="M1K-A Harmonic Exciter (0x9D) — Protótipo Staged Offline (SEM USB / SEM FLASH)",
            font=("Segoe UI", 11, "bold"),
        )
        banner.pack(anchor="w", **pad)

        ttk.Label(self.root, textvariable=self.origin_var).pack(anchor="w", padx=10)

        cols = ("idx", "key", "value", "v240", "sdk", "perm")
        self.tree = ttk.Treeview(self.root, columns=cols, show="headings", height=5)
        for col, title, width in (
            ("idx", "#", 36),
            ("key", "Campo", 130),
            ("value", "Valor Staged", 95),
            ("v240", "ACP V2.40", 160),
            ("sdk", "SDK BP1048", 160),
            ("perm", "Permissão", 160),
        ):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="x", **pad)
        self.tree.bind("<<TreeviewSelect>>", self._on_select_row)

        frame = ttk.LabelFrame(self.root, text="Edição Staged Local (sem sliders contínuos, sem USB)")
        frame.pack(fill="x", **pad)

        ttk.Label(frame, text="Campo:").grid(row=0, column=0, padx=6, pady=6, sticky="w")
        combo = ttk.Combobox(
            frame,
            textvariable=self.field_var,
            values=[f.key for f in EXCITER_AUDIT_FIELDS],
            state="readonly",
            width=22,
        )
        combo.grid(row=0, column=1, padx=6, pady=6, sticky="w")
        combo.bind("<<ComboboxSelected>>", lambda _e: self._on_field_change())

        ttk.Label(frame, text="Novo valor inteiro:").grid(row=0, column=2, padx=6, pady=6, sticky="w")
        entry = ttk.Entry(frame, textvariable=self.draft_var, width=14)
        entry.grid(row=0, column=3, padx=6, pady=6, sticky="w")
        entry.bind("<KeyRelease>", lambda _e: self._update_preview())
        entry.bind("<Return>", lambda _e: self._stage_apply())

        self.apply_btn = ttk.Button(frame, text="Stage Offline", command=self._stage_apply)
        self.apply_btn.grid(row=0, column=4, padx=6, pady=6)
        self.undo_btn = ttk.Button(frame, text="Desfazer Stage", command=self._stage_undo)
        self.undo_btn.grid(row=0, column=5, padx=6, pady=6)

        ttk.Label(frame, textvariable=self.preview_var).grid(
            row=1, column=0, columnspan=6, padx=6, pady=4, sticky="w"
        )

        notes = tk.Text(self.root, height=8, wrap="word")
        notes.insert(
            "1.0",
            "Evidência M1K-A (somente leitura):\n"
            "- Cutoff: ACP V2.40 §5.20.26 = 300–10000 Hz; SDK BP1048 exciter.h = 1000–10000 Hz.\n"
            "- Operador observou mínimo aparente de 1000 Hz no ACPWorkbench (BP1032 fw 0.3.0 / lib 2.24.0).\n"
            "- Mantido como evidência reportada; faixa completa e escrita USB aguardam captura USBPcap passiva.\n",
        )
        notes.configure(state="disabled")
        notes.pack(fill="both", expand=True, **pad)

        ttk.Label(self.root, textvariable=self.status_var, relief="sunken").pack(
            fill="x", side="bottom", padx=6, pady=4
        )

    def _on_select_row(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        values = self.tree.item(sel[0], "values")
        if values and len(values) >= 2:
            self.field_var.set(values[1])
            self._on_field_change()

    def _on_field_change(self) -> None:
        key = self.field_var.get()
        idx = next(f.index for f in EXCITER_AUDIT_FIELDS if f.key == key)
        self.draft_var.set(str(self.session.current[idx]))
        self._update_preview()

    def _update_preview(self) -> None:
        view = assess_exciter_draft(self.field_var.get(), self.draft_var.get(), self.session.current)
        if view.acp_preview_hex:
            self.preview_var.set(f"{view.summary} | Preview: {view.acp_preview_hex}")
        else:
            low, high = EXCITER_STAGED_BOUNDS.get(self.field_var.get(), (0, 0))
            self.preview_var.set(f"{view.summary} (faixa protótipo: {low}..{high})")

    def _refresh_table(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for f in EXCITER_AUDIT_FIELDS:
            self.tree.insert(
                "",
                "end",
                values=(
                    f.index,
                    f.key,
                    self.session.current[f.index],
                    f.v240_range,
                    f.sdk_range,
                    f.permission_label,
                ),
            )

    def _stage_apply(self) -> None:
        try:
            view = self.session.stage_apply(self.field_var.get(), self.draft_var.get().strip())
        except ValueError as exc:
            self.status_var.set(f"Stage recusado: {exc}")
            return
        self._refresh_table()
        self._update_preview()
        self.status_var.set(
            f"Staged offline: {view.field_key}={view.target} (nenhum dado enviado via USB)."
        )

    def _stage_undo(self) -> None:
        try:
            key, old_t, prev = self.session.stage_undo()
        except ValueError as exc:
            self.status_var.set(str(exc))
            return
        if self.field_var.get() == key:
            self.draft_var.set(str(prev))
        self._refresh_table()
        self._update_preview()
        self.status_var.set(f"Stage desfeito offline: {key} {old_t} → {prev} (sem USB).")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=ROOT / "data" / "demo_snapshot.json",
        help="Optional local snapshot JSON for offline baseline",
    )
    args = parser.parse_args()
    root = tk.Tk()
    ExciterOfflineEditorApp(root, args.snapshot)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
