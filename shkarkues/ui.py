"""Ndërfaqja grafike (Tkinter).

Thread-et e shkarkimit nuk prekin kurrë widget-et direkt: ata vendosin ngjarje në
`self.events`, dhe `_poll_events` i përpunon në thread-in kryesor çdo 100 ms.
"""

import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import APP_NAME, __version__
from .config import LOGO_ICO, LOGO_PNG, QUALITIES, Settings, resource_path
from .downloader import Downloader, Status, Summary, TaskUpdate, clean_error
from .history import History

FONT = "Segoe UI"
C = {
    "bg": "#13131c",
    "surface": "#1c1c29",
    "surface2": "#262636",
    "border": "#34344b",
    "text": "#ececf3",
    "muted": "#9494ab",
    "accent": "#e94560",
    "accent_hover": "#ff5a76",
    "accent_dim": "#6e2a3a",
    "success": "#3ecf8e",
    "error": "#ff6b6b",
}

STATUS_ICON = {
    Status.WAITING: "○", Status.FETCHING: "◌", Status.DOWNLOADING: "↓",
    Status.CONVERTING: "♪", Status.DONE: "✓", Status.SKIPPED: "»",
    Status.FAILED: "✕", Status.CANCELLED: "–",
}
STATUS_TAG = {
    Status.WAITING: "muted", Status.FETCHING: "active", Status.DOWNLOADING: "active",
    Status.CONVERTING: "active", Status.DONE: "done", Status.SKIPPED: "muted",
    Status.FAILED: "failed", Status.CANCELLED: "muted",
}
FINISHED = {Status.DONE, Status.SKIPPED, Status.FAILED, Status.CANCELLED}


def _int(value: str, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(hi, int(str(value).strip())))
    except ValueError:
        return default


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.settings = Settings.load()
        self.history = History()
        self.events: queue.Queue = queue.Queue()
        self.downloader = Downloader(
            self.history,
            on_task=lambda u: self.events.put(("task", u)),
            on_log=lambda m: self.events.put(("log", m)),
        )
        self.worker: threading.Thread | None = None
        self.total = 0
        self.task_status: dict[int, Status] = {}
        self.task_pct: dict[int, float] = {}
        self.errors: dict[int, str] = {}

        self._setup_window()
        self._setup_style()
        self._build()
        self._reset_progress()
        self.root.after(100, self._poll_events)

    # ------------------------------------------------------------------ setup

    def _setup_window(self) -> None:
        self.root.title(APP_NAME)
        # Madhësia në pikselë varet nga shkallëzimi i ekranit (100%, 125%, 150%…)
        scale = float(self.root.tk.call("tk", "scaling")) / 1.333
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = min(int(1000 * scale), int(sw * 0.92)), min(int(800 * scale), int(sh * 0.88))
        self.root.geometry(f"{w}x{h}+{(sw - w) // 2}+{max(0, (sh - h) // 2 - 20)}")
        self.root.minsize(min(int(820 * scale), w), min(int(600 * scale), h))
        self.root.configure(bg=C["bg"])
        try:
            self.root.iconbitmap(default=str(LOGO_ICO))
        except tk.TclError:
            pass
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_style(self) -> None:
        s = ttk.Style(self.root)
        s.theme_use("clam")
        scale = float(self.root.tk.call("tk", "scaling")) / 1.333

        s.configure(
            ".", background=C["bg"], foreground=C["text"], fieldbackground=C["surface2"],
            bordercolor=C["border"], lightcolor=C["border"], darkcolor=C["border"],
            troughcolor=C["surface2"], focuscolor=C["accent"], selectbackground=C["accent"],
            selectforeground="white", insertcolor=C["text"], font=(FONT, 10),
        )
        s.configure("TFrame", background=C["bg"])
        s.configure("Card.TFrame", background=C["surface"])
        s.configure("TLabel", background=C["bg"], foreground=C["text"])
        s.configure("Card.TLabel", background=C["surface"])
        s.configure("Muted.Card.TLabel", background=C["surface"], foreground=C["muted"], font=(FONT, 9))
        s.configure("Section.Card.TLabel", background=C["surface"], font=(FONT, 11, "bold"))
        s.configure("Title.TLabel", font=(FONT, 20, "bold"))
        s.configure("Subtitle.TLabel", foreground=C["muted"])
        s.configure("Muted.TLabel", foreground=C["muted"], font=(FONT, 9))
        s.configure("Status.TLabel", foreground=C["muted"], font=(FONT, 9))
        s.configure("Done.TLabel", foreground=C["success"], font=(FONT, 10, "bold"))
        s.configure("Skip.TLabel", foreground=C["muted"], font=(FONT, 10, "bold"))
        s.configure("Fail.TLabel", foreground=C["error"], font=(FONT, 10, "bold"))
        s.configure("Link.Card.TLabel", background=C["surface"], foreground=C["accent"], font=(FONT, 9, "underline"))

        for w in ("TEntry", "TSpinbox", "TCombobox"):
            s.configure(
                w, fieldbackground=C["surface2"], foreground=C["text"], bordercolor=C["border"],
                lightcolor=C["surface2"], darkcolor=C["surface2"], arrowcolor=C["text"],
                background=C["surface2"], padding=6,
            )
            s.map(w, bordercolor=[("focus", C["accent"])], lightcolor=[("focus", C["accent"])])
        s.map(
            "TCombobox",
            fieldbackground=[("readonly", C["surface2"])], foreground=[("readonly", C["text"])],
            selectbackground=[("readonly", C["surface2"])], selectforeground=[("readonly", C["text"])],
            bordercolor=[("focus", C["accent"])],
        )
        self.root.option_add("*TCombobox*Listbox.background", C["surface2"])
        self.root.option_add("*TCombobox*Listbox.foreground", C["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", C["accent"])
        self.root.option_add("*TCombobox*Listbox.font", (FONT, 10))

        # Checkbox me ikona tona (ai i "clam" duket si ✕ kur është i zgjedhur)
        try:
            factor = 2 if scale >= 1.25 else 3  # 48px -> 24px ose 16px
            self._check_imgs = [
                tk.PhotoImage(file=str(resource_path("assets", n))).subsample(factor)
                for n in ("check_off.png", "check_on.png")
            ]
            s.element_create(
                "Nice.indicator", "image", self._check_imgs[0],
                ("selected", self._check_imgs[1]), border=0, sticky="w",
            )
            s.layout("Card.TCheckbutton", [("Checkbutton.padding", {"sticky": "nswe", "children": [
                ("Nice.indicator", {"side": "left", "sticky": ""}),
                ("Checkbutton.label", {"side": "left", "sticky": "w"}),
            ]})])
        except tk.TclError:
            pass
        s.configure("Card.TCheckbutton", background=C["surface"], foreground=C["text"], padding=(0, 4))
        s.map("Card.TCheckbutton", background=[("active", C["surface"])])

        s.configure(
            "TButton", background=C["surface2"], foreground=C["text"], bordercolor=C["border"],
            lightcolor=C["surface2"], darkcolor=C["surface2"], padding=(12, 6), focuscolor=C["surface2"],
        )
        s.map(
            "TButton",
            background=[("disabled", C["surface"]), ("pressed", C["border"]), ("active", C["border"])],
            foreground=[("disabled", C["muted"])],
        )
        s.configure(
            "Accent.TButton", background=C["accent"], foreground="white", bordercolor=C["accent"],
            lightcolor=C["accent"], darkcolor=C["accent"], focuscolor=C["accent"],
            font=(FONT, 11, "bold"), padding=(24, 10),
        )
        hover = [("disabled", C["accent_dim"]), ("pressed", C["accent_dim"]), ("active", C["accent_hover"])]
        s.map(
            "Accent.TButton", background=hover, lightcolor=hover, darkcolor=hover, bordercolor=hover,
            foreground=[("disabled", "#c9a3ad")],
        )
        s.configure("Stop.TButton", font=(FONT, 11), padding=(18, 10))

        s.configure("TNotebook", background=C["surface"], borderwidth=0, tabmargins=(0, 0, 0, 0))
        s.configure(
            "TNotebook.Tab", background=C["surface"], foreground=C["muted"], padding=(14, 6),
            bordercolor=C["surface"], lightcolor=C["surface"], font=(FONT, 10),
        )
        s.map(
            "TNotebook.Tab",
            background=[("selected", C["surface2"])], foreground=[("selected", C["text"])],
            lightcolor=[("selected", C["accent"])],
        )
        s.configure("Bottom.TNotebook", background=C["bg"])
        s.configure("Bottom.TNotebook.Tab", background=C["bg"], bordercolor=C["bg"], lightcolor=C["bg"])
        s.map("Bottom.TNotebook.Tab", background=[("selected", C["surface"])],
              foreground=[("selected", C["text"])], lightcolor=[("selected", C["accent"])])

        s.configure(
            "Treeview", background=C["surface"], fieldbackground=C["surface"], foreground=C["text"],
            rowheight=int(30 * scale), bordercolor=C["surface"], borderwidth=0,
        )
        s.map("Treeview", background=[("selected", C["surface2"])], foreground=[("selected", C["text"])])
        s.configure(
            "Treeview.Heading", background=C["surface2"], foreground=C["muted"], relief="flat",
            font=(FONT, 9, "bold"), padding=6, bordercolor=C["surface2"],
        )
        s.map("Treeview.Heading", background=[("active", C["border"])])

        s.configure(
            "Accent.Horizontal.TProgressbar", troughcolor=C["surface2"], background=C["accent"],
            bordercolor=C["surface2"], lightcolor=C["accent"], darkcolor=C["accent"],
            thickness=int(8 * scale),
        )
        s.configure(
            "Vertical.TScrollbar", background=C["surface2"], troughcolor=C["surface"],
            bordercolor=C["surface"], arrowcolor=C["muted"], lightcolor=C["surface2"],
            darkcolor=C["surface2"], gripcount=0,
        )
        quiet = [("disabled", C["surface"]), ("active", C["border"])]
        s.map("Vertical.TScrollbar", background=quiet, lightcolor=quiet, darkcolor=quiet,
              troughcolor=[("disabled", C["surface"])], arrowcolor=[("disabled", C["surface2"])])

    def _card(self, parent, title: str) -> ttk.Frame:
        card = ttk.Frame(parent, style="Card.TFrame", padding=14)
        ttk.Label(card, text=title, style="Section.Card.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 8)
        )
        return card

    def _text(self, parent, **kw) -> tk.Text:
        return tk.Text(
            parent, bg=C["surface2"], fg=C["text"], insertbackground=C["text"],
            selectbackground=C["accent"], relief="flat", highlightthickness=1,
            highlightbackground=C["border"], highlightcolor=C["accent"],
            padx=8, pady=6, **kw,
        )

    # ------------------------------------------------------------------ layout

    def _build(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        outer = ttk.Frame(self.root, padding=(20, 16))
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(4, weight=1)

        self._build_header(outer)

        top = ttk.Frame(outer)
        top.grid(row=1, column=0, sticky="ew")
        top.columnconfigure(0, weight=1, uniform="top")
        top.columnconfigure(1, weight=1, uniform="top")
        self._build_source(top)
        self._build_options(top)
        self._build_destination(outer)
        self._build_actions(outer)
        self._build_activity(outer)

    def _build_header(self, parent) -> None:
        header = ttk.Frame(parent)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.columnconfigure(1, weight=1)
        try:
            self.logo_img = tk.PhotoImage(file=str(resource_path("assets", "logo_64.png")))
            self.root.iconphoto(True, tk.PhotoImage(file=str(LOGO_PNG)))
            ttk.Label(header, image=self.logo_img).grid(row=0, column=0, rowspan=2, padx=(0, 14))
        except tk.TclError:
            pass
        ttk.Label(header, text=APP_NAME, style="Title.TLabel").grid(row=0, column=1, sticky="sw")
        ttk.Label(
            header, text="Shkarko muzikë nga YouTube si MP3, shpejt dhe thjesht.",
            style="Subtitle.TLabel",
        ).grid(row=1, column=1, sticky="nw")
        ttk.Label(header, text=f"v{__version__}", style="Muted.TLabel").grid(row=0, column=2, sticky="ne")

    def _build_source(self, parent) -> None:
        card = self._card(parent, "1   Çfarë do të shkarkosh?")
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        card.columnconfigure(0, weight=1)

        self.mode_nb = ttk.Notebook(card)
        self.mode_nb.grid(row=1, column=0, sticky="nsew")

        # --- Kërko
        search = ttk.Frame(self.mode_nb, style="Card.TFrame", padding=(2, 12, 2, 2))
        search.columnconfigure(1, weight=1)
        self.mode_nb.add(search, text="  Kërko në YouTube  ")
        ttk.Label(search, text="Emri i këngës, këngëtarit ose zhanrit:", style="Card.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w"
        )
        self.query_var = tk.StringVar(value=self.settings.last_query)
        self.query_entry = ttk.Entry(search, textvariable=self.query_var, font=(FONT, 11))
        self.query_entry.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(6, 10))
        self.query_entry.bind("<Return>", lambda e: self.start())
        ttk.Label(search, text="Sa këngë:", style="Card.TLabel").grid(row=2, column=0, sticky="w")
        self.num_var = tk.StringVar(value=str(self.settings.num_songs))
        ttk.Spinbox(search, from_=1, to=200, width=6, textvariable=self.num_var).grid(
            row=2, column=1, sticky="w", padx=(10, 0)
        )
        ttk.Label(
            search, text="Shtyp Enter për të filluar", style="Muted.Card.TLabel"
        ).grid(row=2, column=2, sticky="e")

        # --- Link-e
        links = ttk.Frame(self.mode_nb, style="Card.TFrame", padding=(2, 12, 2, 2))
        links.columnconfigure(0, weight=1)
        links.rowconfigure(1, weight=1)
        self.mode_nb.add(links, text="  Link-e / Playlist  ")
        ttk.Label(
            links, text="Ngjit link-e YouTube, një për rresht. Pranohen edhe playlist-at.",
            style="Card.TLabel",
        ).grid(row=0, column=0, columnspan=3, sticky="w")
        self.links_text = self._text(links, height=4, font=("Consolas", 10), wrap="none")
        self.links_text.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(6, 8))
        btns = ttk.Frame(links, style="Card.TFrame")
        btns.grid(row=2, column=0, sticky="w")
        ttk.Button(btns, text="Ngjit nga clipboard", command=self._paste_links).pack(side="left")
        ttk.Button(btns, text="Pastro", command=lambda: self.links_text.delete("1.0", "end")).pack(
            side="left", padx=8
        )

    def _build_options(self, parent) -> None:
        card = self._card(parent, "2   Cilësimet")
        card.grid(row=0, column=1, sticky="nsew")
        card.columnconfigure(1, weight=1)

        ttk.Label(card, text="Cilësia e MP3:", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        self.quality_var = tk.StringVar(value=f"{self.settings.quality} kbps")
        ttk.Combobox(
            card, textvariable=self.quality_var, state="readonly", width=10,
            values=[f"{q} kbps" for q in QUALITIES],
        ).grid(row=1, column=1, sticky="w", padx=(10, 0), pady=4)

        ttk.Label(card, text="Njëkohësisht:", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=4)
        self.parallel_var = tk.StringVar(value=str(self.settings.parallel))
        ttk.Spinbox(card, from_=1, to=8, width=6, textvariable=self.parallel_var).grid(
            row=2, column=1, sticky="w", padx=(10, 0), pady=4
        )
        ttk.Label(card, text="Sa këngë shkarkohen në të njëjtën kohë (4 = optimale)", style="Muted.Card.TLabel").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(0, 6)
        )

        self.skip_var = tk.BooleanVar(value=self.settings.skip_duplicates)
        ttk.Checkbutton(
            card, text="  Mos i shkarko sërish këngët e vjetra", variable=self.skip_var,
            style="Card.TCheckbutton",
        ).grid(row=4, column=0, columnspan=2, sticky="w")
        self.meta_var = tk.BooleanVar(value=self.settings.embed_metadata)
        ttk.Checkbutton(
            card, text="  Shto kopertinën dhe artistin", variable=self.meta_var,
            style="Card.TCheckbutton",
        ).grid(row=5, column=0, columnspan=2, sticky="w")

    def _build_destination(self, parent) -> None:
        card = ttk.Frame(parent, style="Card.TFrame", padding=14)
        card.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        card.columnconfigure(1, weight=1)

        ttk.Label(card, text="3   Ruaj te:", style="Section.Card.TLabel").grid(row=0, column=0, padx=(0, 12))
        self.dest_var = tk.StringVar(value=self.settings.output_dir)
        ttk.Entry(card, textvariable=self.dest_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(card, text="Zgjidh…", command=self._choose_folder).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(card, text="Hap dosjen", command=self._open_folder).grid(row=0, column=3, padx=(8, 0))

        hist = ttk.Frame(card, style="Card.TFrame")
        hist.grid(row=1, column=1, columnspan=3, sticky="w", pady=(6, 0))
        self.history_var = tk.StringVar()
        ttk.Label(hist, textvariable=self.history_var, style="Muted.Card.TLabel").pack(side="left")
        clear = ttk.Label(hist, text="Pastro historikun", style="Link.Card.TLabel", cursor="hand2")
        clear.pack(side="left", padx=(10, 0))
        clear.bind("<Button-1>", lambda e: self._clear_history())
        self._update_history_label()

    def _build_actions(self, parent) -> None:
        bar = ttk.Frame(parent)
        bar.grid(row=3, column=0, sticky="ew", pady=14)
        bar.columnconfigure(2, weight=1)

        self.start_btn = ttk.Button(bar, text="▶  Fillo shkarkimin", style="Accent.TButton", command=self.start)
        self.start_btn.grid(row=0, column=0, rowspan=2)
        self.stop_btn = ttk.Button(bar, text="■  Ndalo", style="Stop.TButton", command=self.stop, state="disabled")
        self.stop_btn.grid(row=0, column=1, rowspan=2, padx=(8, 16))

        self.status_var = tk.StringVar()
        ttk.Label(bar, textvariable=self.status_var, style="Status.TLabel").grid(row=0, column=2, sticky="sw")
        self.progress = ttk.Progressbar(bar, style="Accent.Horizontal.TProgressbar", maximum=100)
        self.progress.grid(row=1, column=2, sticky="ew", pady=(4, 0))

        stats = ttk.Frame(bar)
        stats.grid(row=0, column=3, rowspan=2, padx=(16, 0))
        self.done_var, self.skip_count_var, self.fail_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
        ttk.Label(stats, textvariable=self.done_var, style="Done.TLabel").pack(side="left", padx=4)
        ttk.Label(stats, textvariable=self.skip_count_var, style="Skip.TLabel").pack(side="left", padx=4)
        ttk.Label(stats, textvariable=self.fail_var, style="Fail.TLabel").pack(side="left", padx=4)

    def _build_activity(self, parent) -> None:
        nb = ttk.Notebook(parent, style="Bottom.TNotebook")
        nb.grid(row=4, column=0, sticky="nsew")

        # --- Tabela e këngëve
        act = ttk.Frame(nb, style="Card.TFrame")
        act.columnconfigure(0, weight=1)
        act.rowconfigure(0, weight=1)
        nb.add(act, text="  Këngët  ")
        scale = float(self.root.tk.call("tk", "scaling")) / 1.333
        cols = ("status", "title", "progress", "speed", "info")
        self.tree = ttk.Treeview(act, columns=cols, show="headings", selectmode="browse")
        for col, text, width, anchor, stretch in (
            ("status", "Statusi", 150, "w", False),
            ("title", "Kënga", 360, "w", True),
            ("progress", "Progresi", 80, "center", False),
            ("speed", "Shpejtësia", 100, "center", False),
            ("info", "Info", 160, "w", False),
        ):
            self.tree.heading(col, text=text, anchor=anchor)
            self.tree.column(col, width=int(width * scale), anchor=anchor, stretch=stretch, minwidth=60)
        self.tree.tag_configure("done", foreground=C["success"])
        self.tree.tag_configure("failed", foreground=C["error"])
        self.tree.tag_configure("muted", foreground=C["muted"])
        self.tree.tag_configure("active", foreground=C["text"])
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(act, orient="vertical", command=self.tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<Double-1>", self._on_row_double)

        # --- Log
        log = ttk.Frame(nb, style="Card.TFrame")
        log.columnconfigure(0, weight=1)
        log.rowconfigure(0, weight=1)
        nb.add(log, text="  Log  ")
        self.log_text = self._text(log, height=6, font=("Consolas", 9), wrap="word", state="disabled")
        self.log_text.configure(highlightthickness=0, bg=C["surface"])
        self.log_text.grid(row=0, column=0, sticky="nsew")
        lsb = ttk.Scrollbar(log, orient="vertical", command=self.log_text.yview)
        lsb.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=lsb.set)

    # ------------------------------------------------------------------ veprimet

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        mode = "search" if self.mode_nb.index("current") == 0 else "links"
        if mode == "search":
            source = self.query_var.get().strip()
            if not source:
                messagebox.showwarning(APP_NAME, "Shkruaj çfarë do të kërkosh.")
                self.query_entry.focus_set()
                return
        else:
            lines = [l.strip() for l in self.links_text.get("1.0", "end").splitlines()]
            lines = [l for l in lines if l and not l.startswith("#")]
            source = [l for l in lines if l.startswith(("http://", "https://"))]
            bad = len(lines) - len(source)
            if not source:
                messagebox.showwarning(APP_NAME, "Ngjit të paktën një link YouTube (që fillon me https://).")
                return
            if bad and not messagebox.askyesno(
                APP_NAME, f"{bad} rreshta nuk duken si link-e dhe do të anashkalohen. Vazhdo?"
            ):
                return

        out = self.dest_var.get().strip()
        try:
            os.makedirs(out, exist_ok=True)
        except OSError as e:
            messagebox.showerror(APP_NAME, f"Dosja nuk mund të krijohet:\n{out}\n\n{e}")
            return

        self._save_settings()
        self._reset_progress()
        self.tree.delete(*self.tree.get_children())
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self._set_running(True)

        params = dict(
            output_dir=out,
            quality=self.settings.quality,
            parallel=self.settings.parallel,
            skip_duplicates=self.settings.skip_duplicates,
            embed_metadata=self.settings.embed_metadata,
        )
        self.downloader.reset()
        self.worker = threading.Thread(
            target=self._work, args=(mode, source, self.settings.num_songs, params), daemon=True
        )
        self.worker.start()

    def _work(self, mode, source, num_songs, params) -> None:
        log = lambda m: self.events.put(("log", m))  # noqa: E731
        try:
            if mode == "search":
                self.events.put(("status", f"Duke kërkuar “{source}”…"))
                log(f"Duke kërkuar '{source}'…")
                jobs = self.downloader.search(source, num_songs)
                log(f"U gjetën {len(jobs)} këngë")
            else:
                self.events.put(("status", "Duke përgatitur link-et…"))
                jobs = self.downloader.expand_urls(source)
            if self.downloader.cancelled:
                self.events.put(("done", Summary()))
                return
            if not jobs:
                self.events.put(("error", "Nuk u gjet asnjë këngë."))
                return
            self.events.put(("total", len(jobs)))
            self.events.put(("done", self.downloader.run(jobs, **params)))
        except Exception as e:  # noqa: BLE001
            self.events.put(("error", clean_error(e)))

    def stop(self) -> None:
        self.downloader.cancel()
        self.stop_btn.configure(state="disabled")
        self.status_var.set("Duke ndaluar… këngët që po konvertohen do të përfundojnë.")

    # ------------------------------------------------------------------ ngjarjet

    def _poll_events(self) -> None:
        try:
            for _ in range(500):
                kind, payload = self.events.get_nowait()
                if kind == "task":
                    self._update_row(payload)
                elif kind == "log":
                    self._log(payload)
                elif kind == "status":
                    self.status_var.set(payload)
                elif kind == "total":
                    self.total = payload
                    self._refresh_progress()
                elif kind == "done":
                    self._finish(payload)
                elif kind == "error":
                    self._set_running(False)
                    self.status_var.set("Ndodhi një gabim.")
                    self._log(f"GABIM: {payload}")
                    messagebox.showerror(APP_NAME, payload)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _update_row(self, u: TaskUpdate) -> None:
        iid = str(u.index)
        first_time = u.index not in self.task_status
        self.task_status[u.index] = u.status
        if u.percent is not None:
            self.task_pct[u.index] = u.percent
        if u.error:
            self.errors[u.index] = u.error

        if u.status in (Status.DONE, Status.CONVERTING):
            progress = "100%"
        elif u.status == Status.DOWNLOADING and u.percent is not None:
            progress = f"{u.percent:.0f}%"
        else:
            progress = ""
        if u.status == Status.FAILED:
            info = u.error
        elif u.status == Status.SKIPPED:
            info = "Ekziston tashmë"
        elif u.status == Status.DOWNLOADING and u.eta:
            info = f"edhe {u.eta}"
        else:
            info = ""
        values = (
            f"{STATUS_ICON[u.status]}  {u.status.value}",
            u.title,
            progress,
            u.speed if u.status == Status.DOWNLOADING else "",
            info,
        )
        tags = (STATUS_TAG[u.status],)
        if self.tree.exists(iid):
            self.tree.item(iid, values=values, tags=tags)
        else:
            self.tree.insert("", "end", iid=iid, values=values, tags=tags)
        if not first_time and u.status == Status.FETCHING:
            self.tree.see(iid)
        self._refresh_progress()

    def _refresh_progress(self) -> None:
        total = self.total or len(self.task_status)
        statuses = list(self.task_status.values())
        done = statuses.count(Status.DONE)
        skipped = statuses.count(Status.SKIPPED)
        failed = statuses.count(Status.FAILED)
        finished = sum(s in FINISHED for s in statuses)
        active = sum(s in (Status.FETCHING, Status.DOWNLOADING, Status.CONVERTING) for s in statuses)

        self.done_var.set(f"✓ {done}")
        self.skip_count_var.set(f"» {skipped}")
        self.fail_var.set(f"✕ {failed}")
        if not total:
            return
        fraction = 0.0
        for idx, st in self.task_status.items():
            if st in FINISHED:
                fraction += 1
            elif st == Status.CONVERTING:
                fraction += 0.95
            elif st == Status.DOWNLOADING:
                fraction += 0.9 * self.task_pct.get(idx, 0) / 100
        pct = fraction / total * 100
        self.progress["value"] = pct
        if self.worker and self.worker.is_alive() and not self.downloader.cancelled:
            self.status_var.set(f"{finished} nga {total} këngë gati · {active} në punë")
            self.root.title(f"{pct:.0f}% · {APP_NAME}")

    def _finish(self, summary: Summary) -> None:
        self._set_running(False)
        self.root.title(APP_NAME)
        self._update_history_label()
        self._refresh_progress()

        parts = [f"{summary.completed} këngë të reja"]
        if summary.skipped:
            parts.append(f"{summary.skipped} të anashkaluara")
        if summary.failed:
            parts.append(f"{summary.failed} dështuan")
        if summary.cancelled:
            parts.append(f"{summary.cancelled} të anuluara")
        text = ", ".join(parts)

        if self.downloader.cancelled:
            self.status_var.set(f"U ndal. {text}.")
            self._log(f"U ndal nga përdoruesi. {text}.")
            return
        self.progress["value"] = 100
        self.status_var.set(f"Përfundoi! {text}.")
        self._log(f"PËRFUNDOI: {text}.")
        if summary.failed:
            text += "\n\nKliko dy herë mbi një këngë të dështuar për të parë arsyen."
        if summary.completed and messagebox.askyesno(
            "Përfundoi", f"{text}\n\nTë hap dosjen me këngët?"
        ):
            self._open_folder()
        elif not summary.completed:
            messagebox.showinfo("Përfundoi", text)

    # ------------------------------------------------------------------ ndihmëse

    def _set_running(self, running: bool) -> None:
        self.start_btn.configure(state="disabled" if running else "normal")
        self.stop_btn.configure(state="normal" if running else "disabled")

    def _reset_progress(self) -> None:
        self.total = 0
        self.task_status.clear()
        self.task_pct.clear()
        self.errors.clear()
        self.progress["value"] = 0
        self.status_var.set("Gati. Zgjidh çfarë do të shkarkosh dhe shtyp “Fillo”.")
        self._refresh_progress()

    def _log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _save_settings(self) -> None:
        s = self.settings
        s.output_dir = self.dest_var.get().strip()
        s.last_query = self.query_var.get().strip()
        s.num_songs = _int(self.num_var.get(), 1, 200, 10)
        s.parallel = _int(self.parallel_var.get(), 1, 8, 4)
        quality = self.quality_var.get().split()[0] if self.quality_var.get() else "192"
        s.quality = quality if quality in QUALITIES else "192"
        s.skip_duplicates = self.skip_var.get()
        s.embed_metadata = self.meta_var.get()
        self.num_var.set(str(s.num_songs))
        self.parallel_var.set(str(s.parallel))
        s.save()

    def _update_history_label(self) -> None:
        self.history_var.set(f"{len(self.history)} këngë në historik")

    def _clear_history(self) -> None:
        if messagebox.askyesno(
            APP_NAME,
            "Të pastrohet historiku?\n\nKëngët e shkarkuara më parë do të mund të shkarkohen sërish. "
            "Skedarët MP3 nuk fshihen.",
        ):
            self.history.clear()
            self._update_history_label()
            self._log("Historiku u pastrua.")

    def _choose_folder(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.dest_var.get() or None)
        if folder:
            self.dest_var.set(os.path.normpath(folder))

    def _open_folder(self) -> None:
        path = self.dest_var.get().strip()
        if not os.path.isdir(path):
            messagebox.showinfo(APP_NAME, "Dosja nuk ekziston ende. Do të krijohet kur të shkarkosh.")
            return
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606
        else:
            import subprocess

            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])

    def _paste_links(self) -> None:
        try:
            text = self.root.clipboard_get().strip()
        except tk.TclError:
            return
        if text:
            current = self.links_text.get("1.0", "end").strip()
            self.links_text.insert("end", ("\n" if current else "") + text)

    def _on_row_double(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        idx = int(iid)
        if idx in self.errors:
            messagebox.showerror("Pse dështoi kjo këngë?", self.errors[idx])
        elif self.task_status.get(idx) == Status.DONE:
            self._open_folder()

    def _on_close(self) -> None:
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno(APP_NAME, "Shkarkimi është në proces. Të ndalohet dhe të mbyllet?"):
                return
            self.downloader.cancel()
        self._save_settings()
        self.root.destroy()


def run() -> None:
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # tekst i qartë në ekrane me shkallëzim
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ShkarkuesMP3")  # ikona në taskbar
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    App(root)
    root.mainloop()
