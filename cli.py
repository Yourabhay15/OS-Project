from __future__ import annotations

import shlex
from typing import List

from core import FileSystemCore
from engine import RecoveryOptimizationEngine
from persistence import load_json, load_pickle, save_json, save_pickle


def _help_text() -> str:
    return (
        "Commands:\n"
        "  help\n"
        "  tree\n"
        "  mkd <path>\n"
        "  mkf <dir> <name> <size> [indexed|linked]\n"
        "  del <dir> <name>\n"
        "  ls <dir>\n"
        "  crash [rate]\n"
        "  recover\n"
        "  defrag\n"
        "  usage\n"
        "  save_json <path>\n"
        "  load_json <path>\n"
        "  save_pickle <path>\n"
        "  load_pickle <path>\n"
        "  exit\n"
    )


def run_cli() -> None:
    fs = FileSystemCore(total_blocks=80)
    engine = RecoveryOptimizationEngine(fs)
    fs.create_directory("/docs")
    print("File System CLI started. Type 'help' for commands.")
    while True:
        try:
            raw = input("fs> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting CLI.")
            return
        if not raw:
            continue
        parts: List[str] = shlex.split(raw)
        cmd = parts[0].lower()
        try:
            if cmd == "help":
                print(_help_text())
            elif cmd == "exit":
                print("Goodbye.")
                return
            elif cmd == "tree":
                print(fs.tree())
            elif cmd == "mkd":
                fs.create_directory(parts[1])
                print(f"Directory created: {parts[1]}")
            elif cmd == "mkf":
                allocation = parts[4] if len(parts) > 4 else "indexed"
                fs.create_file(parts[1], parts[2], int(parts[3]), allocation)
                engine.snapshot_file(parts[1], parts[2])
                print(f"File created: {parts[2]}")
            elif cmd == "del":
                fs.delete_file(parts[1], parts[2])
                print(f"File deleted (recoverable): {parts[2]}")
            elif cmd == "ls":
                print(fs.list_directory(parts[1]))
            elif cmd == "crash":
                rate = float(parts[1]) if len(parts) > 1 else 0.3
                print(engine.simulate_crash(rate))
            elif cmd == "recover":
                d = engine.recover_deleted_files()
                c = engine.recover_corrupted_files()
                print(f"Recovered deleted={d}, corrupted={c}")
            elif cmd == "defrag":
                print(engine.defragment_disk())
            elif cmd == "usage":
                print(engine.disk_usage(), {"fragmentation_percent": engine.fragmentation_score()})
            elif cmd == "save_json":
                save_json(parts[1], fs, engine)
                print(f"Saved JSON state to: {parts[1]}")
            elif cmd == "load_json":
                fs, engine = load_json(parts[1])
                print(f"Loaded JSON state from: {parts[1]}")
            elif cmd == "save_pickle":
                save_pickle(parts[1], fs, engine)
                print(f"Saved pickle state to: {parts[1]}")
            elif cmd == "load_pickle":
                fs, engine = load_pickle(parts[1])
                print(f"Loaded pickle state from: {parts[1]}")
            else:
                print("Unknown command. Type 'help'.")
        except Exception as exc:
            print(f"Error: {exc}")
