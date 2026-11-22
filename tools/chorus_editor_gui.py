"""BPControl M1G — staged, single-step GUI for Guitar Chorus wet.

Windows tkinter desktop prototype. Retains the full 59-effect read-only
snapshot explorer. The ONLY writable field is Guitar Chorus (ACP 0x8F)
wet (field 6) and each explicit Apply may change it by exactly ONE point.

NO USB at startup, while typing, searching, changing effects or losing focus.
A separate supervised Windows worker performs USB only on a user click.
No flash save, no automatic retries, no background device polling.

Start offline:
    py tools/chorus_editor_gui.py
Opt into live reads and single-step Apply:
    py tools/chorus_editor_gui.py --enable-live-writes
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from bpcontrol.chorus_editor import parse_wet_draft, validate_editor_target
from bpcontrol.snapshot import read_catalog
from tools.audit_snapshot import audit_snapshot

LIVE_WORKER = ROOT / "tools" / "chorus_editor_worker.py"
DEFAULT_SNAPSHOT = ROOT / "artifacts" / "snapshots" / "bp1032-01.json"
DEMO_SNAPSHOT = ROOT / "data" / "demo_snapshot.json"
WORKER_TIMEOUT_SECONDS = 15

BG = "#F5F1E9"
PANEL = "#FFFDF9"
INK = "#272626"
SIDEBAR = "#252627"
ORANGE = "#EF6426"
MUTED = "#7E796F"
LINE = "#DED8CE"
GREEN = "#286D55"
RED = "#B3422A"


def validate_snapshot_for_viewing(snapshot: dict) -> None:
    report = audit_snapshot(snapshot, read_catalog())
    if report["audit_errors"]:
        raise ValueError(
            f"Snapshot failed structural audit ({report['audit_errors']} errors); "
            "viewer refuses this file"
        )


def run_worker_once(mode: str, expected: tuple[int, ...] | None = None,
                    target: int | None = None, *, python=sys.executable) -> dict:
    """Run one killable child. Never reattempt timeout or failing writes."""
    if mode not in ("read", "apply"):
        raise ValueError("Unexpected editor operation")
    command = [python, str(LIVE_WORKER)]
    if mode == "read":
        if expected is not None or target is not None:
            raise ValueError("Read must not include write arguments")
        command.append("--read")
    else:
        validate_editor_target(expected, target)
        command.extend([
            "--apply",
            "--expected-fields", json.dumps(list(expected), separators=(",", ":")),
            "--target", str(target),
            "--authorize-one-apply",
        ])
    try:
        child = subprocess.run(
            command, capture_output=True, text=True,
            timeout=WORKER_TIMEOUT_SECONDS, check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "STATE_UNCERTAIN" if mode == "apply" else "READ_ERROR",
            "error": "HID worker timed out; never repeat automatically.",
        }
    except OSError as exc:
        return {
            "status": "STATE_UNCERTAIN" if mode == "apply" else "READ_ERROR",
            "error": f"Cannot start HID worker: {exc}",
        }
    try:
        payload = json.loads(child.stdout)
        if not isinstance(payload, dict) or not isinstance(payload.get("status"), str):
            raise ValueError("Unexpected worker JSON format")
    except (json.JSONDecodeError, ValueError):
        return {
            "status": "STATE_UNCERTAIN" if mode == "apply" else "READ_ERROR",
            "error": f"Invalid HID worker reply (exit {child.returncode}); "
                     "do not automatically retry.",
        }
    return payload


def launch_gui(snapshot: dict, *, allow_live: bool, source: Path) -> None:
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
    except ImportError as exc:
        raise RuntimeError("This Python installation has no tkinter/Tcl-Tk") from exc

    root = tk.Tk()
    root.title("BPControl · M1G · Chorus Editor")
    root.geometry("1210x770")
    root.minsize(880, 610)
    root.configure(bg=BG)

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(
        "BP.Treeview", background=PANEL, foreground=INK, fieldbackground=PANEL,
        rowheight=30, borderwidth=0, font=("Segoe UI", 10),
    )
    style.configure(
        "BP.Treeview.Heading", background="#EDE7DD", foreground=INK,
        relief="flat", font=("Segoe UI", 9, "bold"),
    )
    style.map("BP.Treeview", background=[("selected", "#F8D6C1")],
              foreground=[("selected", INK)])

    effects = snapshot["effects"]
    all_indices = [e["index"] for e in effects]
    visible_indices = all_indices[:]
    selected = [15]
    manual_live = [None]       # most recent explicitly requested physical read
    undo_value = [None]        # previous full seven-field state, one step back
    busy = [False]
    locked = [False]           # irreversible for this GUI session after uncertainty
    response_queue: queue.SimpleQueue = queue.SimpleQueue()

    left = tk.Frame(root, bg=SIDEBAR, width=292)
    left.pack(side="left", fill="y")
    left.pack_propagate(False)
    main = tk.Frame(root, bg=BG, padx=29, pady=25)
    main.pack(side="left", fill="both", expand=True)

    tk.Label(left, text="BP", font=("Segoe UI", 24, "bold"),
             bg=SIDEBAR, fg=ORANGE).place(x=20, y=16)
    tk.Label(left, text="CONTROL", font=("Segoe UI", 24, "bold"),
             bg=SIDEBAR, fg="#FAF5ED").place(x=57, y=16)
    tk.Label(left, text="M1G  /  DEVICE INSPECTOR",
             bg=SIDEBAR, fg="#B6AEA2", font=("Segoe UI", 9)).place(x=23, y=67)
    search = tk.StringVar()
    find = tk.Entry(
        left, textvariable=search, relief="flat", bg="#3A3B3A",
        fg="white", insertbackground="white", font=("Segoe UI", 11),
    )
    find.place(x=18, y=104, width=255, height=35)
    tk.Label(left, text="59 INSTÂNCIAS · DADOS DO SNAPSHOT",
             bg=SIDEBAR, fg="#B4ABA1", font=("Segoe UI", 8)).place(x=19, y=157)
    list_frame = tk.Frame(left, bg=SIDEBAR)
    list_frame.place(x=16, y=184, relwidth=.93, relheight=.66)
    entries = tk.Listbox(
        list_frame, font=("Segoe UI", 10), bg=SIDEBAR, fg="#DDD9D0",
        selectbackground="#63412F", selectforeground="white",
        highlightthickness=0, borderwidth=0, activestyle="none",
        exportselection=False,
    )
    scrollbar = tk.Scrollbar(list_frame, command=entries.yview)
    entries.configure(yscrollcommand=scrollbar.set)
    entries.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    tk.Label(left, text="BP1032 · USB HID / MI_04",
             bg=SIDEBAR, fg="#C2BCB2", font=("Segoe UI", 9)).pack(
        side="bottom", pady=20
    )

    heading = tk.Frame(main, bg=BG)
    heading.pack(fill="x")
    tk.Label(
        heading, text="BP1032 / EDITOR LOCAL",
        bg=BG, fg=ORANGE, font=("Segoe UI", 10, "bold"),
    ).pack(anchor="w")
    title = tk.Label(
        heading, text="Guitar Chorus", bg=BG, fg=INK,
        font=("Segoe UI", 26, "bold"),
    )
    title.pack(anchor="w", pady=(4, 1))
    detail = tk.Label(
        heading, text="", bg=BG, fg=MUTED, font=("Segoe UI", 9),
        wraplength=850, justify="left",
    )
    detail.pack(anchor="w")

    state_row = tk.Frame(main, bg=BG)
    state_row.pack(fill="x", pady=(19, 14))
    mode_label = tk.Label(
        state_row,
        text="● LEITURA + EDIÇÃO HABILITADA" if allow_live else
             "● SOMENTE LEITURA — MODO OFFLINE",
        bg=BG, fg=GREEN if allow_live else MUTED,
        font=("Segoe UI", 10, "bold"),
    )
    mode_label.pack(side="left")
    refresh_button = tk.Button(
        state_row, text="↻  Consultar Chorus (USB)", relief="flat",
        bg=SIDEBAR, fg="white", activebackground="#474747",
        activeforeground="white", padx=13, pady=8, cursor="hand2",
    )
    refresh_button.pack(side="right")
    snapshot_label = tk.Label(
        main, bg=BG, fg=MUTED, font=("Segoe UI", 9), wraplength=890,
        justify="left",
        text=(
            f"Snapshot: {source.name} · "
            f"{snapshot.get('created_at_utc', 'sem data')} · "
            "outros efeitos são SOMENTE LEITURA. "
            "Snapshot NÃO autoriza escrita."
        ),
    )
    snapshot_label.pack(anchor="w", pady=(0, 16))

    tablebox = tk.Frame(main, bg=PANEL, highlightthickness=1,
                        highlightbackground=LINE, padx=12, pady=12)
    tablebox.pack(fill="both", expand=True)
    tk.Label(
        tablebox, text="PARÂMETROS E VALORES OBSERVADOS",
        bg=PANEL, fg=MUTED, font=("Segoe UI", 10, "bold"),
    ).pack(anchor="w", pady=(3, 10))

    tree_area = tk.Frame(tablebox, bg=PANEL)
    tree_area.pack(fill="both", expand=True)
    columns = ("field", "name", "value", "unit", "evidence")
    tree = ttk.Treeview(
        tree_area, columns=columns, show="headings", style="BP.Treeview",
        selectmode="browse",
    )
    for key, text, width, anchor in (
        ("field", "#", 42, "center"),
        ("name", "Campo", 210, "w"),
        ("value", "Valor", 85, "e"),
        ("unit", "Unidade", 95, "w"),
        ("evidence", "Evidência", 195, "w"),
    ):
        tree.heading(key, text=text)
        tree.column(key, width=width, anchor=anchor, stretch=key=="name")
    tree_scroll = ttk.Scrollbar(tree_area, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=tree_scroll.set)
    tree.pack(side="left", fill="both", expand=True)
    tree_scroll.pack(side="right", fill="y")

    editor = tk.Frame(main, bg=PANEL, highlightthickness=1,
                      highlightbackground=LINE, padx=18, pady=14)
    editor.pack(fill="x", pady=(17, 12))
    editor_top = tk.Frame(editor, bg=PANEL)
    editor_top.pack(fill="x")
    tk.Label(
        editor_top, text="CHORUS · WET / CAMPO 06",
        bg=PANEL, fg=INK, font=("Segoe UI", 11, "bold"),
    ).pack(side="left")
    editor_state = tk.Label(
        editor_top, text="Somente leitura", bg=PANEL,
        fg=MUTED, font=("Segoe UI", 9),
    )
    editor_state.pack(side="right")

    editrow = tk.Frame(editor, bg=PANEL)
    editrow.pack(fill="x", pady=(14, 7))
    tk.Label(editrow, text="Novo valor (%)", bg=PANEL, fg=MUTED).pack(side="left")
    draft = tk.StringVar(value="")
    entry = tk.Entry(
        editrow, textvariable=draft, width=9, justify="center",
        font=("Segoe UI", 15, "bold"), relief="solid", bd=1, fg=INK,
        insertbackground=INK,
    )
    entry.pack(side="left", padx=(15, 10), ipady=6)
    apply_btn = tk.Button(
        editrow, text="Aplicar", bg=ORANGE, fg="white", relief="flat",
        activebackground="#D7521B", activeforeground="white",
        padx=19, pady=11, cursor="hand2",
    )
    apply_btn.pack(side="left", padx=4)
    undo_btn = tk.Button(
        editrow, text="Desfazer último Apply", bg="#3B3C3B", fg="white",
        relief="flat", padx=12, pady=11, cursor="hand2",
    )
    undo_btn.pack(side="left", padx=4)
    cancel_btn = tk.Button(
        editrow, text="Cancelar rascunho", bg="#E8E0D4",
        fg=INK, relief="flat", padx=10, pady=11, cursor="hand2",
    )
    cancel_btn.pack(side="left", padx=4)
    hint = tk.Label(
        editor, bg=PANEL, fg=MUTED, justify="left", anchor="w",
        wraplength=810, font=("Segoe UI", 9),
        text=("Nenhum comando é emitido durante digitação, Backspace ou perda de foco. "
              "Aplicar exige valor inteiro e diferença EXATA de 1 ponto. "
              "A mudança é volátil; não é salva em flash."),
    )
    hint.pack(anchor="w", pady=(5, 0))

    status = tk.Label(
        main, text="Nenhuma operação USB iniciada.", fg=MUTED,
        bg=BG, wraplength=900, justify="left",
        font=("Segoe UI", 10),
    )
    status.pack(anchor="w", pady=(7, 2))

    def set_status(message, fg=MUTED):
        status.configure(text=message, fg=fg)

    def effect_row():
        return effects[selected[0]-1]

    def choose_effect(index):
        selected[0] = index
        e = effect_row()
        title.configure(text=e["name"].split(":")[-1].strip())
        detail.configure(
            text=f"Instância #{index:02d} · ACP {e['command']} · "
                 f"Tipo {e['type_name']} · "
                 f"Status no snapshot: {e['status']}"
        )
        for key in tree.get_children():
            tree.delete(key)
        fields = e.get("fields", [])
        if not fields:
            tree.insert("", "end", values=("", "Nenhum valor no snapshot",
                                           "—", "—", "read-only"))
        for f in fields:
            actual_value = f["signed"]
            evidence = f.get("mapping", "unknown")
            if index == 15 and manual_live[0] is not None:
                actual_value = manual_live[0][f["index"]]
                evidence = "readback USB atual" if f["index"] == 6 else evidence
            tree.insert("", "end", values=(
                f"{f['index']:02d}", f.get("name", "field"),
                actual_value, f.get("unit", "raw"), evidence
            ))
        refresh_editor_state()

    def select_list(event=None):
        active = entries.curselection()
        if active and active[0] < len(visible_indices):
            choose_effect(visible_indices[active[0]])

    def filter_list(*_):
        phrase = search.get().casefold().strip()
        visible_indices[:] = [
            e["index"] for e in effects
            if phrase in (e["name"] + " " + e["command"] +
                          " " + e["type_name"]).casefold()
        ]
        entries.delete(0, tk.END)
        for i in visible_indices:
            e = effects[i-1]
            entries.insert(tk.END, f"{e['command']}   {e['name'].split(':')[-1]}")
        if selected[0] in visible_indices:
            pos = visible_indices.index(selected[0])
            entries.selection_set(pos)
            entries.see(pos)

    def refresh_editor_state():
        editing = selected[0] == 15
        ready = editing and allow_live and manual_live[0] is not None
        enabled = ready and not busy[0] and not locked[0]
        button_read = allow_live and not busy[0] and not locked[0]
        refresh_button.configure(state="normal" if button_read else "disabled")
        entry.configure(state="normal" if enabled else "disabled")
        apply_btn.configure(state="normal" if enabled else "disabled")
        cancel_btn.configure(state="normal" if enabled else "disabled")
        undo_btn.configure(
            state="normal" if enabled and undo_value[0] is not None
            else "disabled"
        )
        if not editing:
            editor_state.configure(text="Outro efeito: somente leitura", fg=MUTED)
        elif locked[0]:
            editor_state.configure(text="BLOQUEADO — VERIFICAR NA PLACA", fg=RED)
        elif busy[0]:
            editor_state.configure(text="Operação HID em andamento", fg=ORANGE)
        elif not allow_live:
            editor_state.configure(text="Inicie com --enable-live-writes", fg=MUTED)
        elif manual_live[0] is None:
            editor_state.configure(text="Consulte a placa antes de editar", fg=ORANGE)
        else:
            editor_state.configure(
                text=f"Readback USB: wet={manual_live[0][6]} · valor volátil",
                fg=GREEN,
            )

    def apply_response(mode, result, undo=False):
        busy[0] = False
        code = result.get("status")
        if mode == "read":
            if code == "READ_OK":
                values = tuple(result.get("fields", ()))
                if len(values) == 7 and all(type(v) is int for v in values):
                    manual_live[0] = values
                    undo_value[0] = None
                    draft.set(str(values[6]))
                    set_status(
                        f"Leitura atual confirmada: Chorus wet={values[6]}. "
                        "Os demais 58 efeitos continuam vindos do snapshot.",
                        GREEN,
                    )
                else:
                    manual_live[0] = None
                    set_status("Erro: leitura devolveu campos inválidos.", RED)
            else:
                manual_live[0] = None
                set_status(
                    "Leitura USB não confirmada: " + result.get("error", str(result)),
                    RED,
                )
        elif code == "APPLIED_VERIFIED":
            values = tuple(result.get("applied_readback", ()))
            previous = tuple(result.get("initial", ()))
            if len(values) == 7 and len(previous) == 7:
                manual_live[0] = values
                undo_value[0] = None if undo else previous
                draft.set(str(values[6]))
                set_status(
                    f"APPLIED_VERIFIED: Chorus wet={values[6]} confirmado por "
                    "readback. A mudança permanece VOLÁTIL; nenhuma flash foi gravada.",
                    GREEN,
                )
            else:
                locked[0] = True
                manual_live[0] = None
                set_status("Resposta inconsistente: estado incerto; verificar manualmente.", RED)
        elif code == "REFUSED_NO_WRITE":
            manual_live[0] = None
            undo_value[0] = None
            set_status(
                "REFUSED_NO_WRITE: valor ou estado do Chorus mudou. "
                "Nenhuma escrita foi tentada. Consulte a placa novamente. "
                + result.get("error", ""), RED,
            )
        elif code == "ERROR_BUT_RESTORED":
            manual_live[0] = None
            undo_value[0] = None
            set_status(
                "ERROR_BUT_RESTORED: houve erro, porém o readback final "
                "confirmou os sete campos iniciais. Atualize manualmente a leitura. "
                + "; ".join(result.get("errors", [])), RED,
            )
        else:
            # Even if the process exits without output, write may have happened.
            locked[0] = True
            manual_live[0] = None
            undo_value[0] = None
            set_status(
                "STATE_UNCERTAIN: o último Apply pode não ter sido revertido. "
                "Feche este editor e verifique o Chorus pelo ACPWorkbench. "
                "Não faça uma nova escrita automaticamente. "
                + result.get("error", "; ".join(result.get("errors", []))), RED,
            )
            messagebox.showwarning(
                "BPControl — estado incerto",
                "O estado da BP1032 não pôde ser confirmado.\n"
                "Esta sessão ficou bloqueada. Depois de encerrar o editor,\n"
                "verifique e, se necessário, restaure manualmente o Chorus no ACPWorkbench.",
            )
        choose_effect(selected[0])

    def poll():
        try:
            while True:
                mode, result, undo = response_queue.get_nowait()
                apply_response(mode, result, undo)
        except queue.Empty:
            pass
        root.after(100, poll)

    def run_operation(mode, target=None, undo=False):
        if busy[0] or locked[0] or not allow_live:
            return
        expected = manual_live[0] if mode == "apply" else None
        if mode == "apply" and expected is None:
            return
        busy[0] = True
        refresh_editor_state()
        set_status(
            "Lendo o firmware e a BP1032…" if mode == "read" else
            "Aplicando uma alteração USB e verificando o readback…",
            ORANGE,
        )

        def background():
            response = run_worker_once(mode, expected=expected, target=target)
            response_queue.put((mode, response, undo))

        threading.Thread(target=background, name="bpcontrol-hid-worker",
                         daemon=True).start()

    def read_clicked():
        if not allow_live:
            return
        if locked[0]:
            return
        run_operation("read")

    def apply_clicked():
        if selected[0] != 15 or manual_live[0] is None or not allow_live:
            return
        try:
            target = parse_wet_draft(draft.get())
            validate_editor_target(manual_live[0], target)
        except ValueError as exc:
            set_status(f"Rascunho não aplicado: {exc}", RED)
            return
        current = manual_live[0][6]
        approved = messagebox.askyesno(
            "Confirmar alteração no DSP",
            f"Enviar uma alteração VOLÁTIL para a BP1032?\n\n"
            f"Guitar Chorus · wet: {current} → {target}\n\n"
            "O programa confere os sete campos novamente antes de escrever.\n"
            "Não salva na flash. Em caso de falha após escrita, tentará "
            "uma restauração, que pode não ser possível se a USB desconectar.",
            default="no",
        )
        if approved:
            run_operation("apply", target)

    def undo_clicked():
        if undo_value[0] is None or manual_live[0] is None:
            return
        old = undo_value[0]
        if not messagebox.askyesno(
            "Desfazer última alteração",
            f"Restaurar o valor anterior do Chorus wet "
            f"{manual_live[0][6]} → {old[6]}?\n\n"
            "Será uma nova escrita VOLÁTIL de um ponto, com readback.",
            default="no",
        ):
            return
        try:
            validate_editor_target(manual_live[0], old[6])
        except ValueError as exc:
            set_status(f"Desfazer indisponível: {exc}", RED)
            return
        run_operation("apply", old[6], undo=True)

    def cancel_clicked():
        if manual_live[0] is not None:
            draft.set(str(manual_live[0][6]))
        set_status("Rascunho cancelado; nenhum comando USB enviado.", MUTED)

    def on_draft_edit(*_):
        if not busy[0] and not locked[0] and manual_live[0] is not None:
            set_status(
                "Rascunho local alterado. Nada foi enviado ao DSP. "
                "Use Aplicar (ou Enter) para confirmar.",
                MUTED,
            )

    def close():
        if busy[0]:
            messagebox.showwarning(
                "Operação USB em andamento",
                "A operação USB ainda está em andamento. Não feche o editor "
                "antes do readback ou timeout do worker.",
            )
            return
        root.destroy()

    def return_key(event):
        if selected[0] == 15 and not busy[0] and not locked[0]:
            apply_clicked()
        return "break"

    entries.bind("<<ListboxSelect>>", select_list)
    search.trace_add("write", filter_list)
    draft.trace_add("write", on_draft_edit)
    entry.bind("<Return>", return_key)
    refresh_button.configure(command=read_clicked)
    apply_btn.configure(command=apply_clicked)
    undo_btn.configure(command=undo_clicked)
    cancel_btn.configure(command=cancel_clicked)
    root.protocol("WM_DELETE_WINDOW", close)
    filter_list()
    choose_effect(15)
    if not allow_live:
        set_status(
            "MODO OFFLINE: nenhuma ação USB disponível. Para habilitar leitura "
            "manual e Apply limitado: iniciar com --enable-live-writes.", MUTED,
        )
    elif snapshot.get("source") != "live_windows_hid":
        set_status(
            "Aviso: catálogo é demo/parcial. Só a consulta USB manual do "
            "Chorus poderá habilitar a edição do wet.", ORANGE,
        )
    root.after(100, poll)
    root.mainloop()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--snapshot", type=Path,
        help="full local 59-effect JSON; if omitted use last capture or clearly labeled demo"
    )
    parser.add_argument(
        "--enable-live-writes", action="store_true",
        help="enable manual USB read + confirmation-gated Chorus wet ±1 Apply"
    )
    args = parser.parse_args(argv)
    if args.enable_live_writes and sys.platform != "win32":
        parser.error("live USB editor is Windows-only")
    path = args.snapshot or (
        DEFAULT_SNAPSHOT if DEFAULT_SNAPSHOT.exists() else DEMO_SNAPSHOT
    )
    if not path.is_file():
        parser.error("snapshot not found: " + str(path))
    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        validate_snapshot_for_viewing(snapshot)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(f"invalid snapshot: {exc}")
    print(f"BPControl M1G — snapshot {path}", flush=True)
    print(
        "MODE: MANUAL USB CHORUS WET ±1, no flash writes."
        if args.enable_live_writes else "MODE: OFFLINE / NO USB ACCESS.",
        flush=True,
    )
    try:
        launch_gui(snapshot, allow_live=args.enable_live_writes, source=path)
    except RuntimeError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
