from __future__ import annotations

import random
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from core import FileSystemCore
from engine import RecoveryOptimizationEngine
from persistence import load_json, load_pickle, save_json, save_pickle


class FileSystemApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("File System Recovery and Optimization Tool")
        self.geometry("1080x700")

        self.fs = FileSystemCore(total_blocks=80)
        self.engine = RecoveryOptimizationEngine(self.fs)
        self.fs.create_directory("/docs")
        self.fs.create_directory("/media")

        self._build_layout()
        self._seed_sample_data()
        self.refresh_view()

    def _build_layout(self) -> None:
        main = ttk.Frame(self, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        controls = ttk.Frame(main)
        controls.pack(fill=tk.X)

        ttk.Button(controls, text="Create File", command=self.create_file).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Delete File", command=self.delete_file).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Create Directory", command=self.create_dir).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Simulate Crash", command=self.crash).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Recover Files", command=self.recover).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Defragment", command=self.defrag).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Save JSON", command=self.save_json_state).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Load JSON", command=self.load_json_state).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Save Pickle", command=self.save_pickle_state).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Load Pickle", command=self.load_pickle_state).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Refresh", command=self.refresh_view).pack(side=tk.LEFT, padx=4)

        body = ttk.Frame(main)
        body.pack(fill=tk.BOTH, expand=True, pady=8)

        left = ttk.Frame(body)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        right = ttk.Frame(body)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))

        ttk.Label(left, text="Directory Tree").pack(anchor=tk.W)
        self.tree_text = tk.Text(left, height=20, width=55, wrap=tk.NONE)
        self.tree_text.pack(fill=tk.BOTH, expand=True)

        ttk.Label(left, text="Disk Blocks").pack(anchor=tk.W, pady=(8, 0))
        self.block_text = tk.Text(left, height=10, width=55, wrap=tk.WORD)
        self.block_text.pack(fill=tk.BOTH, expand=True)

        ttk.Label(right, text="Usage & Fragmentation").pack(anchor=tk.W)
        self.figure = Figure(figsize=(5, 4), dpi=100)
        self.ax1 = self.figure.add_subplot(121)
        self.ax2 = self.figure.add_subplot(122)
        self.canvas = FigureCanvasTkAgg(self.figure, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.status = tk.StringVar(value="Ready")
        ttk.Label(main, textvariable=self.status).pack(anchor=tk.W, pady=(6, 0))

    def _seed_sample_data(self) -> None:
        for i in range(3):
            name = f"file_{i+1}.txt"
            size = random.randint(2, 6)
            allocation = "indexed" if i % 2 == 0 else "linked"
            self.fs.create_file("/docs", name, size, allocation)
            self.engine.snapshot_file("/docs", name)

    def create_file(self) -> None:
        dir_path = simpledialog.askstring("Directory", "Directory path:", initialvalue="/docs")
        if not dir_path:
            return
        name = simpledialog.askstring("File Name", "File name:")
        if not name:
            return
        size = simpledialog.askinteger("Size", "File size in blocks:", initialvalue=3, minvalue=1, maxvalue=20)
        if not size:
            return
        allocation = simpledialog.askstring("Allocation", "Allocation method (indexed/linked):", initialvalue="indexed")
        if not allocation:
            return
        try:
            self.fs.create_file(dir_path, name, size, allocation.lower().strip())
            self.engine.snapshot_file(dir_path, name)
            self.status.set(f"Created {name} in {dir_path}")
            self.refresh_view()
        except Exception as exc:
            messagebox.showerror("Error", str(exc))

    def delete_file(self) -> None:
        dir_path = simpledialog.askstring("Directory", "Directory path:", initialvalue="/docs")
        if not dir_path:
            return
        name = simpledialog.askstring("File Name", "File name to delete:")
        if not name:
            return
        try:
            self.fs.delete_file(dir_path, name)
            self.status.set(f"Deleted {name} (recoverable)")
            self.refresh_view()
        except Exception as exc:
            messagebox.showerror("Error", str(exc))

    def create_dir(self) -> None:
        dir_path = simpledialog.askstring("New Directory", "Path (e.g. /docs/reports):")
        if not dir_path:
            return
        try:
            self.fs.create_directory(dir_path)
            self.status.set(f"Created directory {dir_path}")
            self.refresh_view()
        except Exception as exc:
            messagebox.showerror("Error", str(exc))

    def crash(self) -> None:
        try:
            result = self.engine.simulate_crash(0.3)
            self.status.set(
                f"Crash simulated: corrupted={result['files_corrupted']}, zeroed_blocks={result['blocks_zeroed']}"
            )
            self.refresh_view()
        except Exception as exc:
            messagebox.showerror("Error", str(exc))

    def recover(self) -> None:
        recovered_deleted = self.engine.recover_deleted_files()
        recovered_corrupted = self.engine.recover_corrupted_files()
        self.status.set(
            f"Recovery complete: deleted={recovered_deleted}, corrupted={recovered_corrupted}"
        )
        self.refresh_view()

    def defrag(self) -> None:
        result = self.engine.defragment_disk()
        self.status.set(
            f"Defragmented: files={result['files_reordered']}, moved_blocks={result['moved_blocks']}"
        )
        self.refresh_view()

    def save_json_state(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save JSON State",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            save_json(path, self.fs, self.engine)
            self.status.set(f"State saved (JSON): {path}")
        except Exception as exc:
            messagebox.showerror("Error", str(exc))

    def load_json_state(self) -> None:
        path = filedialog.askopenfilename(
            title="Load JSON State",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self.fs, self.engine = load_json(path)
            self.status.set(f"State loaded (JSON): {path}")
            self.refresh_view()
        except Exception as exc:
            messagebox.showerror("Error", str(exc))

    def save_pickle_state(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save Pickle State",
            defaultextension=".pkl",
            filetypes=[("Pickle files", "*.pkl"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            save_pickle(path, self.fs, self.engine)
            self.status.set(f"State saved (Pickle): {path}")
        except Exception as exc:
            messagebox.showerror("Error", str(exc))

    def load_pickle_state(self) -> None:
        path = filedialog.askopenfilename(
            title="Load Pickle State",
            filetypes=[("Pickle files", "*.pkl"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self.fs, self.engine = load_pickle(path)
            self.status.set(f"State loaded (Pickle): {path}")
            self.refresh_view()
        except Exception as exc:
            messagebox.showerror("Error", str(exc))

    def render_block_map(self) -> str:
        tokens = []
        for item in self.fs.disk:
            if item is None:
                tokens.append("[Free]")
            else:
                tokens.append(f"[{item[:4]}]")
        return "".join(tokens)

    def refresh_view(self) -> None:
        self.tree_text.delete("1.0", tk.END)
        self.tree_text.insert(tk.END, self.fs.tree())

        self.block_text.delete("1.0", tk.END)
        self.block_text.insert(tk.END, self.render_block_map())

        usage = self.engine.disk_usage()
        frag = self.engine.fragmentation_score()
        self.ax1.clear()
        self.ax2.clear()
        self.ax1.pie(
            [usage["used_blocks"], usage["free_blocks"]],
            labels=["Used", "Free"],
            autopct="%1.1f%%",
            colors=["#4C72B0", "#DDDDDD"],
        )
        self.ax1.set_title("Disk Usage")

        self.ax2.bar(["Fragmentation"], [frag], color="#C44E52")
        self.ax2.set_ylim(0, 100)
        self.ax2.set_ylabel("%")
        self.ax2.set_title("Fragmentation")
        self.canvas.draw()
