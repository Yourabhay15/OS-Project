#!/usr/bin/env python3
"""Tkinter visualizer and control panel for the simulated file system."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from fs_core.block_device import BlockDevice
from fs_core.filesystem import FileSystem, FileSystemError
from simulation.crash import crash_before_inode_apply, snapshot_inode_table
from viz import ROLE_COLORS, block_roles


class FSViewerApp:
    COLS = 32
    CELL = 16  # Larger cells for better visibility

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("FS Recovery Lab - block map and tools")
        self.root.minsize(920, 560)
        self._style()
        self.fs: FileSystem | None = None
        self.disk: BlockDevice | None = None
        self._image_path = tk.StringVar(value=str(Path.cwd() / "fs_lab.bin"))
        self._blocks = tk.IntVar(value=256)
        self._path_var = tk.StringVar(value="/hello.txt")
        self._write_text = tk.StringVar(value="Hello FS Lab! Try the buttons below.")
        self._status = tk.StringVar(value="Open or format a volume to begin.")
        self._explain = tk.StringVar(
            value="What happens: format creates metadata areas; write allocates data blocks; recover replays journaled inode updates."
        )
        self._rect_ids: list[int] = []
        self._roles_cache: list[str] | None = None
        self._build_ui()

    def _style(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TButton", padding=6)
        style.configure("TLabelframe", padding=8)
        style.configure("TLabelframe.Label", font=("Segoe UI", 11, "bold"))
        style.configure("TLabel", font=("Segoe UI", 9))

    def _build_ui(self) -> None:
        outer = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        outer.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        left = ttk.Frame(outer, width=380)
        outer.add(left, weight=0)

        right = ttk.Frame(outer)
        outer.add(right, weight=1)

        # --- Volume ---
        vol = ttk.LabelFrame(left, text="Volume")
        vol.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(vol, text="Image file").grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        ent = ttk.Entry(vol, textvariable=self._image_path, width=36)
        ent.grid(row=0, column=1, columnspan=2, sticky=tk.EW, padx=4, pady=2)
        ttk.Button(vol, text="Browse…", command=self._browse).grid(row=0, column=3, padx=4)
        ttk.Label(vol, text="Block count (new only)").grid(row=1, column=0, sticky=tk.W, padx=4)
        ttk.Spinbox(vol, from_=64, to=4096, textvariable=self._blocks, width=10).grid(
            row=1, column=1, sticky=tk.W, padx=4
        )
        bf = ttk.Frame(vol)
        bf.grid(row=2, column=0, columnspan=4, pady=6)
        ttk.Button(bf, text="Format (new)", command=self._cmd_format).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="Open", command=self._cmd_open).pack(side=tk.LEFT, padx=2)
        vol.columnconfigure(1, weight=1)

        # --- Paths ---
        paths = ttk.LabelFrame(left, text="Paths & content")
        paths.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(paths, text="Path").grid(row=0, column=0, sticky=tk.W, padx=4)
        ttk.Entry(paths, textvariable=self._path_var, width=40).grid(
            row=0, column=1, columnspan=2, sticky=tk.EW, padx=4, pady=2
        )
        ttk.Label(paths, text="Write text").grid(row=1, column=0, sticky=tk.NW, padx=4)
        wt = ttk.Entry(paths, textvariable=self._write_text, width=40)
        wt.grid(row=1, column=1, columnspan=2, sticky=tk.EW, padx=4, pady=2)
        paths.columnconfigure(1, weight=1)

        guide = ttk.LabelFrame(left, text="What Happens")
        guide.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(
            guide,
            textvariable=self._explain,
            wraplength=350,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, padx=4, pady=2)

        ops = ttk.LabelFrame(left, text="Operations")
        ops.pack(fill=tk.X, pady=(0, 8))
        r1 = ttk.Frame(ops)
        r1.pack(fill=tk.X)
        for text, cmd in (
            ("mkdir", self._cmd_mkdir),
            ("create", self._cmd_create),
            ("write", self._cmd_write),
            ("read", self._cmd_read),
        ):
            ttk.Button(r1, text=text, width=9, command=cmd).pack(side=tk.LEFT, padx=2, pady=4)
        r2 = ttk.Frame(ops)
        r2.pack(fill=tk.X)
        for text, cmd in (
            ("defrag", self._cmd_defrag),
            ("recover", self._cmd_recover),
            ("demo crash", self._cmd_demo_crash),
        ):
            ttk.Button(r2, text=text, width=11, command=cmd).pack(side=tk.LEFT, padx=2, pady=4)
        r3 = ttk.Frame(ops)
        r3.pack(fill=tk.X)
        ttk.Button(r3, text="guided demo", width=16, command=self._cmd_guided_demo).pack(
            side=tk.LEFT, padx=2, pady=4
        )

        met = ttk.LabelFrame(left, text="Metrics and Log")
        met.pack(fill=tk.BOTH, expand=True)
        self._metrics_label = ttk.Label(met, text="—", justify=tk.LEFT, font=("Consolas", 9))
        self._metrics_label.pack(anchor=tk.W, padx=4)
        self._log = scrolledtext.ScrolledText(met, height=14, width=44, font=("Consolas", 10), wrap=tk.WORD)
        self._log.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # --- Map ---
        map_frame = ttk.LabelFrame(right, text="Block map (hover for index & role)")
        map_frame.pack(fill=tk.BOTH, expand=True)
        legend = ttk.Frame(map_frame)
        legend.pack(fill=tk.X, padx=4, pady=4)
        for role, color in ROLE_COLORS.items():
            if role == "other":
                continue
            f = ttk.Frame(legend)
            f.pack(side=tk.LEFT, padx=4)
            c = tk.Canvas(f, width=14, height=14, highlightthickness=0, bg=color)
            c.pack(side=tk.LEFT)
            ttk.Label(f, text=role.replace("_", " "), font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=2)

        wrap = ttk.Frame(map_frame)
        wrap.pack(fill=tk.BOTH, expand=True)
        self._cv_scroll = ttk.Scrollbar(wrap)
        self._cv_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas = tk.Canvas(
            wrap,
            bg="#111827",
            highlightthickness=0,
            yscrollcommand=self._cv_scroll.set,
        )
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._cv_scroll.config(command=self.canvas.yview)
        self.canvas.bind("<Motion>", self._on_canvas_motion)
        self.canvas.bind("<Leave>", lambda e: self._status.set(""))

        sb = ttk.Label(self.root, textvariable=self._status, relief=tk.SUNKEN, anchor=tk.W)
        sb.pack(fill=tk.X, side=tk.BOTTOM, padx=8, pady=(0, 6))

    def _browse(self) -> None:
        p = filedialog.asksaveasfilename(
            title="Disk image",
            defaultextension=".bin",
            filetypes=[("Binary", "*.bin"), ("All", "*.*")],
        )
        if p:
            self._image_path.set(p)

    def _logln(self, s: str) -> None:
        self._log.insert(tk.END, s + "\n")
        self._log.see(tk.END)

    def _set_explain(self, text: str) -> None:
        self._explain.set(text)

    def _ensure_fs(self) -> tuple[FileSystem, BlockDevice] | None:
        if self.fs is None or self.disk is None:
            messagebox.showwarning("Volume", "Format or open a volume first.")
            return None
        return self.fs, self.disk

    def _cmd_format(self) -> None:
        path = Path(self._image_path.get())
        try:
            if path.exists():
                path.unlink()
            self.disk = BlockDevice(path, num_blocks=int(self._blocks.get()))
            self.fs = FileSystem(self.disk)
            self.fs.format_disk()
            self._logln(f"Formatted {path} ({self.disk.num_blocks} blocks).")
            self._set_explain(
                "Format created superblock, inode bitmap, block bitmap, inode table, data region, and journal region."
            )
            self._refresh_all()
        except (OSError, ValueError, FileSystemError) as e:
            messagebox.showerror("Format", str(e))

    def _cmd_open(self) -> None:
        path = Path(self._image_path.get())
        if not path.exists():
            messagebox.showerror("Open", f"File not found:\n{path}")
            return
        try:
            self.disk = BlockDevice(path)
            self.fs = FileSystem(self.disk)
            self.fs.load_existing()
            self._logln(f"Opened {path} ({self.disk.num_blocks} blocks).")
            self._set_explain("Opened existing image. You can now inspect or modify files and watch block usage.")
            self._refresh_all()
        except (OSError, ValueError, FileSystemError) as e:
            messagebox.showerror("Open", str(e))

    def _refresh_metrics(self) -> None:
        if not self.fs:
            return
        fs = self.fs
        m = fs.metrics
        fr = fs.free_space_report()
        self._metrics_label.configure(
            text=(
                f"reads={m['block_reads']}  writes={m['block_writes']}  "
                f"journal={m['journal_writes']}  recovery_ms={m['recovery_time_ms']:.3f}\n"
                f"data free {fr['free_data_blocks']}/{fr['total_data_blocks']}  "
                f"inodes free {fr['free_inodes']}/{fr['total_inodes']}"
            )
        )

    def _refresh_map(self) -> None:
        if not self.fs or not self.disk:
            return
        self.canvas.delete("all")
        self._rect_ids.clear()
        roles = block_roles(self.fs, self.disk)
        self._roles_cache = roles
        n = len(roles)
        cols = self.COLS
        cell = self.CELL
        rows = (n + cols - 1) // cols
        cw = cols * cell + 2
        ch = rows * cell + 2
        self.canvas.config(scrollregion=(0, 0, cw, ch))
        for i, role in enumerate(roles):
            r, c = divmod(i, cols)
            x1, y1 = c * cell + 1, r * cell + 1
            x2, y2 = x1 + cell - 2, y1 + cell - 2
            color = ROLE_COLORS.get(role, ROLE_COLORS["other"])
            rid = self.canvas.create_rectangle(
                x1, y1, x2, y2, fill=color, outline="#1f2937", width=1, tags=("block", str(i), role)
            )
            self._rect_ids.append(rid)

    def _on_canvas_motion(self, event: tk.Event) -> None:  # type: ignore[name-defined]
        if not self.fs or not self.disk or not self._roles_cache:
            return
        cell = self.CELL
        cols = self.COLS
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        c = int(x) // cell
        r = int(y) // cell
        if c < 0 or r < 0:
            return
        idx = r * cols + c
        if idx >= len(self._roles_cache):
            return
        self._status.set(f"Block {idx}: {self._roles_cache[idx]}")

    def _refresh_all(self) -> None:
        self._refresh_metrics()
        self._refresh_map()

    def _cmd_mkdir(self) -> None:
        p = self._ensure_fs()
        if not p:
            return
        fs, _ = p
        try:
            fs.mkdir(self._path_var.get())
            self._logln(f"mkdir {self._path_var.get()}")
            self._set_explain("mkdir allocated an inode for a directory and inserted an entry in the parent directory.")
            self._refresh_all()
        except FileSystemError as e:
            messagebox.showerror("mkdir", str(e))

    def _cmd_create(self) -> None:
        p = self._ensure_fs()
        if not p:
            return
        fs, _ = p
        try:
            fs.create_file(self._path_var.get())
            self._logln(f"create {self._path_var.get()}")
            self._set_explain("create reserved a file inode. Data blocks are not allocated until write.")
            self._refresh_all()
        except FileSystemError as e:
            messagebox.showerror("create", str(e))

    def _cmd_write(self) -> None:
        p = self._ensure_fs()
        if not p:
            return
        fs, _ = p
        try:
            data = self._write_text.get().encode("utf-8")
            fs.write_file(self._path_var.get(), data)
            self._logln(f"write {self._path_var.get()} ({len(data)} bytes)")
            self._set_explain(
                "write allocated/updated data blocks, journaled inode metadata, then committed updates."
            )
            self._refresh_all()
        except FileSystemError as e:
            messagebox.showerror("write", str(e))

    def _cmd_read(self) -> None:
        p = self._ensure_fs()
        if not p:
            return
        fs, _ = p
        try:
            data = fs.read_file(self._path_var.get())
            self._logln(f"read {self._path_var.get()}:\n{data.decode('utf-8', errors='replace')}")
            self._set_explain("read looked up path in directories, fetched inode metadata, then read file data blocks.")
            self._refresh_all()
        except FileSystemError as e:
            messagebox.showerror("read", str(e))

    def _cmd_defrag(self) -> None:
        p = self._ensure_fs()
        if not p:
            return
        fs, _ = p
        try:
            moved, nbytes = fs.defragment_file(self._path_var.get())
            self._logln(f"defrag: blocks moved={moved}, bytes={nbytes}")
            self._set_explain("defrag rewrote the file to improve data block locality and sequential read behavior.")
            self._refresh_all()
        except FileSystemError as e:
            messagebox.showerror("defrag", str(e))

    def _cmd_recover(self) -> None:
        p = self._ensure_fs()
        if not p:
            return
        fs, _ = p
        n = fs.recover_from_journal()
        self._logln(f"recover: applied {n} inode record(s), {fs.metrics['recovery_time_ms']:.3f} ms")
        self._set_explain("recover scanned journal records and replayed committed inode updates.")
        self._refresh_all()

    def _cmd_demo_crash(self) -> None:
        p = self._ensure_fs()
        if not p:
            return
        fs, disk = p
        path = self._path_var.get()
        data = self._write_text.get().encode("utf-8")
        try:
            snap = snapshot_inode_table(fs, disk)
            fs.write_file(path, data)
            crash_before_inode_apply(fs, disk, snap)
            n = fs.recover_from_journal()
            out = fs.read_file(path)
            self._logln(
                f"demo crash: inode records replayed={n}, read back: "
                f"{out.decode('utf-8', errors='replace')!r}"
            )
            self._set_explain(
                "demo crash restored stale inode table, then recovery replayed journaled metadata to restore file state."
            )
            self._refresh_all()
        except FileSystemError as e:
            messagebox.showerror("demo crash", str(e))

    def _cmd_guided_demo(self) -> None:
        p = self._ensure_fs()
        if not p:
            return
        fs, disk = p
        try:
            self._path_var.set("/demo.txt")
            self._write_text.set("Step 1 data")
            if fs.stat("/demo.txt"):
                pass
        except Exception:
            # ignore if file does not exist
            pass
        try:
            try:
                fs.create_file("/demo.txt")
            except FileSystemError:
                pass
            fs.write_file("/demo.txt", b"Step 1 data")
            snap = snapshot_inode_table(fs, disk)
            fs.write_file("/demo.txt", b"Recovered step data")
            crash_before_inode_apply(fs, disk, snap)
            n = fs.recover_from_journal()
            out = fs.read_file("/demo.txt").decode("utf-8", errors="replace")
            self._logln("guided demo complete:")
            self._logln("- wrote /demo.txt, simulated crash, replayed journal")
            self._logln(f"- replayed records: {n}, final text: {out!r}")
            self._set_explain(
                "Guided demo summary: file write changed data + inode metadata, crash removed latest inode table state, journal replay restored it."
            )
            self._refresh_all()
        except FileSystemError as e:
            messagebox.showerror("guided demo", str(e))

    def run(self) -> None:
        self.root.mainloop()


def run_app() -> None:
    FSViewerApp().run()


if __name__ == "__main__":
    run_app()
