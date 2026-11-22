"""BPControl M1J Music FX Inspector — 4 effects, read-only.

Explore Music 3D, Music 3D Plus, Stereo Widener and Harmonic Exciter
without a single parameter write. Offline mode never touches USB.

    py tools/music_inspector_gui.py
    py tools/music_inspector_gui.py --enable-live-reads

Live reads require Windows, a connected BP1032, and ACPWorkbench CLOSED.
The supervised child runs a strictly firmware-gated read-only HID session.
The PC's USB audio streaming can continue on the separate audio interface.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import threading
import queue

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from bpcontrol.music_effects import (
    MUSIC_EFFECT_INDICES, MUSIC_EFFECTS, MUSIC_BY_INDEX,
    make_music_rows, validate_music_worker_reply,
)
from tools.chorus_editor_gui import validate_snapshot_for_viewing

DEFAULT_SNAPSHOT = ROOT / "artifacts" / "snapshots" / "bp1032-01.json"
DEMO_SNAPSHOT = ROOT / "data" / "demo_snapshot.json"
WORKER = ROOT / "tools" / "music_read_worker.py"
TIMEOUT_S = 15

BG = "#F5F1E9"
PANEL = "#FFFDF9"
INK = "#272626"
DARK = "#252627"
ACCENT = "#EF6426"
MUTED = "#777067"
LINE = "#DCD5CA"
GOOD = "#286D55"
ERR = "#B3422A"


def run_music_worker_once(*, python: str = sys.executable) -> dict:
    """Only four firmware-gated reads. One killable child; no retries."""
    try:
        result = subprocess.run(
            [python, str(WORKER), "--read-four-music-effects"],
            capture_output=True, text=True, timeout=TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"status": "MUSIC_READ_ERROR",
                "error": "Timeout USB. Não repetir automaticamente."}
    except OSError as exc:
        return {"status": "MUSIC_READ_ERROR", "error": f"Erro ao iniciar worker: {exc}"}
    try:
        payload = json.loads(result.stdout)
        if type(payload) is not dict:
            raise ValueError("Resposta do processo não é JSON objeto")
        if result.returncode != 0:
            raise ValueError("Worker encerrou com erro: " +
                             str(payload.get("error", result.returncode)))
        validate_music_worker_reply(payload)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        return {"status": "MUSIC_READ_ERROR", "error": str(exc)}
    return payload


def load_snapshot(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    validate_snapshot_for_viewing(raw)
    # Check the target four catalog records and their field shapes,
    # even when the file is an offline/demo capture.
    make_music_rows(raw["effects"])
    return raw


def launch_gui(snapshot: dict, source: Path, *, enable_live: bool) -> None:
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError as exc:
        raise RuntimeError("Esta instalação do Python não inclui tkinter") from exc

    app = tk.Tk()
    app.title("BPControl · M1J · Music FX Inspector")
    app.geometry("1190x750")
    app.minsize(900, 580)
    app.configure(bg=BG)

    style = ttk.Style(app)
    style.theme_use("clam")
    style.configure(
        "Music.Treeview", background=PANEL, fieldbackground=PANEL,
        foreground=INK, rowheight=36, font=("Segoe UI", 10), borderwidth=0,
    )
    style.configure(
        "Music.Treeview.Heading", background="#EDE7DD", foreground=INK,
        font=("Segoe UI", 9, "bold"), relief="flat",
    )
    style.map(
        "Music.Treeview", background=[("selected", "#F8D6C1")],
        foreground=[("selected", INK)],
    )

    live = [None]           # only filled after manual physical USB read
    selected = [23]
    busy = [False]
    results: queue.SimpleQueue = queue.SimpleQueue()

    sidebar = tk.Frame(app, bg=DARK, width=262)
    sidebar.pack(side="left", fill="y")
    sidebar.pack_propagate(False)

    tk.Label(
        sidebar, text="BPCONTROL", bg=DARK, fg="#F7F1E7",
        font=("Segoe UI", 21, "bold"),
    ).pack(anchor="w", padx=19, pady=(24, 0))
    tk.Label(
        sidebar, text="M1J / MUSIC FX LAB", bg=DARK, fg=ACCENT,
        font=("Segoe UI", 10, "bold"),
    ).pack(anchor="w", padx=19, pady=(2, 25))
    tk.Label(
        sidebar, text="EFEITOS MUSIC / USB",
        bg=DARK, fg="#B6B0A5", font=("Segoe UI", 9, "bold"),
    ).pack(anchor="w", padx=19, pady=(0, 10))
    buttons = {}
    for effect in MUSIC_EFFECTS:
        label = tk.Button(
            sidebar, text=f"  {effect.command:#04x}   {effect.name}",
            bg=DARK, fg="#EEE6DB", activebackground="#5C4232",
            activeforeground="white", anchor="w", relief="flat",
            font=("Segoe UI", 11), padx=8, pady=13,
        )
        label.pack(fill="x", padx=12, pady=3)
        buttons[effect.index] = label

    tk.Label(
        sidebar, text="SEM COMANDOS DE ESCRITA\nSEM GRAVAÇÃO NA FLASH",
        bg=DARK, fg="#C4B6A5", justify="left",
        font=("Segoe UI", 9),
    ).pack(side="bottom", anchor="w", padx=19, pady=25)

    main = tk.Frame(app, bg=BG, padx=26, pady=20)
    main.pack(side="left", fill="both", expand=True)

    tk.Label(
        main, text="BP1032 / MUSIC INSPECTOR",
        bg=BG, fg=ACCENT, font=("Segoe UI", 9, "bold"),
    ).pack(anchor="w")
    header = tk.Frame(main, bg=BG)
    header.pack(fill="x", pady=(3, 10))
    title = tk.Label(
        header, text="Music 3D", bg=BG, fg=INK,
        font=("Segoe UI", 24, "bold"),
    )
    title.pack(side="left")
    read_btn = tk.Button(
        header, text="↻  CONSULTAR 4 EFEITOS (USB)",
        relief="flat", bg=DARK, fg="white", padx=12, pady=11,
        font=("Segoe UI", 9, "bold"),
    )
    read_btn.pack(side="right")

    detail = tk.Label(
        main, text="", bg=BG, fg=MUTED, anchor="w",
        justify="left", font=("Segoe UI", 10),
    )
    detail.pack(anchor="w", pady=(0, 10))
    notice = tk.Label(
        main,
        text="Edição do Chorus permanece no editor M1I. "
             "Neste painel todos os campos são SOMENTE LEITURA.",
        bg=BG, fg=GOOD, anchor="w", justify="left",
        font=("Segoe UI", 10, "bold"),
    )
    notice.pack(anchor="w", pady=(0, 9))
    status = tk.Label(
        main, text="Nenhuma consulta USB iniciada.",
        bg=BG, fg=MUTED, anchor="w", justify="left",
        font=("Segoe UI", 10), wraplength=780,
    )
    status.pack(anchor="w", pady=(0, 9))

    content = tk.Frame(
        main, bg=PANEL, highlightbackground=LINE,
        highlightthickness=1, padx=13, pady=12,
    )
    content.pack(fill="both", expand=True)
    tk.Label(
        content, text="PARÂMETROS E EVIDÊNCIAS DOCUMENTAIS",
        bg=PANEL, fg=MUTED, font=("Segoe UI", 10, "bold"),
    ).pack(anchor="w", pady=(0, 10))
    table_frame = tk.Frame(content, bg=PANEL)
    table_frame.pack(fill="both", expand=True)
    cols = ("parameter", "raw", "unit", "nominal", "origin")
    tree = ttk.Treeview(
        table_frame, columns=cols, show="headings",
        style="Music.Treeview", selectmode="browse",
    )
    for key, label, width in (
        ("parameter", "Parâmetro", 190),
        ("raw", "RAW", 70),
        ("unit", "Unidade", 80),
        ("nominal", "Faixa nominal / conflito", 230),
        ("origin", "Origem", 110),
    ):
        tree.heading(key, text=label)
        tree.column(key, width=width, stretch=(key == "nominal"),
                    anchor="e" if key == "raw" else "w")
    vscroll = ttk.Scrollbar(table_frame, command=tree.yview)
    hscroll = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vscroll.set, xscrollcommand=hscroll.set)
    hscroll.pack(side="bottom", fill="x")
    vscroll.pack(side="right", fill="y")
    tree.pack(side="left", fill="both", expand=True)

    tk.Label(
        content, text="NOTAS E SUGESTÕES DE AUDIÇÃO",
        bg=PANEL, fg=MUTED, font=("Segoe UI", 10, "bold"),
    ).pack(anchor="w", pady=(11, 5))
    notes = tk.Text(
        content, height=7, wrap="word", state="disabled",
        bg="#F1EBE1", fg=INK, relief="flat",
        font=("Segoe UI", 10), padx=12, pady=8,
    )
    notes.pack(fill="x")
    tk.Label(
        main,
        text=f"Snapshot local: {source.name}. ACPWorkbench deve estar FECHADO "
             "durante consultas USB. Fones: áudio da cadeia Music.",
        bg=BG, fg=MUTED, font=("Segoe UI", 9),
        wraplength=795, justify="left",
    ).pack(anchor="w", pady=(12, 0))

    def set_notes(text: str) -> None:
        notes.configure(state="normal")
        notes.delete("1.0", "end")
        notes.insert("1.0", text)
        notes.configure(state="disabled")

    def refresh_effect(index: int) -> None:
        selected[0] = index
        meta = MUSIC_BY_INDEX[index]
        title.configure(text=meta.name)
        detail.configure(
            text=f"Instância #{index:02d}  ·  ACP 0x{meta.command:02X}"
                 f"  ·  tipo {meta.type_id}  ·  {meta.word_count} campos"
        )
        for item in tree.get_children():
            tree.delete(item)
        rows = [r for r in make_music_rows(snapshot["effects"], live[0])
                if r["effect_index"] == index]
        for row in rows:
            tree.insert(
                "", "end", iid=str(row["field_index"]),
                values=(
                    row["field_label"],
                    str(row["value"]) if row["value"] is not None else "—",
                    row["unit"], row["nominal_range"], row["origin"],
                ),
            )
        notes_text = (
            f"ESQUEMA: {meta.name}\n"
            f"OUVIR: {meta.listening_note}\n"
            "FONTES: protocolo MVSilicon V2.40.0 e, quando indicado, "
            "manual ACPWorkbench / SDK BP1048.\n"
            "Limites do manual não são limites experimentalmente "
            "homologados na BP1032. Nenhum campo é gravável."
        )
        set_notes(notes_text)
        for i, button in buttons.items():
            button.configure(
                bg="#67402D" if i == index else DARK,
                fg="white" if i == index else "#EEE6DB",
            )

    def on_tree_select(event=None):
        active = tree.selection()
        if not active:
            return
        position = int(active[0])
        meta = MUSIC_BY_INDEX[selected[0]]
        p = meta.parameters[position]
        reading = [r for r in make_music_rows(snapshot["effects"], live[0])
                   if r["effect_index"] == selected[0] and r["field_index"] == position][0]
        set_notes(
            f"{meta.name} · {p.label} ({p.key})\n"
            f"RAW: {reading['value']}  ·  fonte: {reading['origin']}\n"
            f"Faixa documentada: {p.nominal_range}\n"
            f"Evidência e cautelas: {p.evidence}\n"
            f"Teste auditivo: {meta.listening_note}\n"
            "SEM ESCRITA: esta tela apenas consulta os parâmetros."
        )

    tree.bind("<<TreeviewSelect>>", on_tree_select)

    def read_music():
        if busy[0] or not enable_live:
            return
        busy[0] = True
        read_btn.configure(state="disabled")
        status.configure(text="Consultando firmware e quatro efeitos Music…",
                         fg=ACCENT)

        def worker():
            response = run_music_worker_once()
            results.put(response)

        threading.Thread(target=worker, name="bpcontrol-music-read",
                         daemon=True).start()

    def poll():
        try:
            while True:
                response = results.get_nowait()
                busy[0] = False
                if response.get("status") == "MUSIC_READ_OK":
                    try:
                        live[0] = validate_music_worker_reply(response)
                    except ValueError as exc:
                        live[0] = None
                        status.configure(text=f"Resposta Music inválida: {exc}",
                                         fg=ERR)
                    else:
                        status.configure(
                            text="4 efeitos Music lidos via USB, "
                                 "sem alterar nenhum parâmetro. "
                                 "Agora os valores são do dispositivo.",
                            fg=GOOD,
                        )
                else:
                    live[0] = None
                    status.configure(
                        text="Falha na leitura Music; nenhum valor foi escrito. " +
                             str(response.get("error", "")), fg=ERR,
                    )
                refresh_effect(selected[0])
                read_btn.configure(
                    state="normal" if enable_live else "disabled",
                )
        except queue.Empty:
            pass
        app.after(100, poll)

    for idx, btn in buttons.items():
        btn.configure(command=lambda i=idx: refresh_effect(i))
    read_btn.configure(
        command=read_music, state="normal" if enable_live else "disabled",
    )

    def close():
        if busy[0]:
            from tkinter import messagebox
            messagebox.showwarning(
                "Leitura Music em andamento",
                "Aguarde a finalização da consulta ou do limite do worker "
                "antes de fechar.",
            )
            return
        app.destroy()

    app.protocol("WM_DELETE_WINDOW", close)
    refresh_effect(23)
    if not enable_live:
        status.configure(
            text="MODO OFFLINE · sem acesso USB. Abra com "
                 "--enable-live-reads para consultar os parâmetros reais.",
            fg=MUTED,
        )
    app.after(100, poll)
    app.mainloop()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path,
                        help="saved 59-effect snapshot JSON")
    parser.add_argument("--enable-live-reads", action="store_true",
                        help="explicitly enable four read-only Music USB queries")
    args = parser.parse_args(argv)
    if args.enable_live_reads and sys.platform != "win32":
        parser.error("Windows required for live BP1032 USB HID")
    source = args.snapshot or (
        DEFAULT_SNAPSHOT if DEFAULT_SNAPSHOT.exists() else DEMO_SNAPSHOT
    )
    try:
        snapshot = load_snapshot(source)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        parser.error(f"invalid snapshot: {exc}")
    print(f"BPControl M1J Music read-only · {source}", flush=True)
    print("MODE: FOUR MANUAL USB READS ONLY" if args.enable_live_reads
          else "MODE: OFFLINE, NO USB", flush=True)
    try:
        launch_gui(snapshot, source, enable_live=args.enable_live_reads)
    except RuntimeError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
