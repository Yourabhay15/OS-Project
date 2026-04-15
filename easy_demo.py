#!/usr/bin/env python3
"""One-command demonstration flow for project presentations."""

from __future__ import annotations

from pathlib import Path

from fs_core.block_device import BlockDevice
from fs_core.filesystem import FileSystem
from simulation.crash import crash_before_inode_apply, snapshot_inode_table
from viz import block_map


def _wait(interactive: bool, message: str = "Press Enter to continue...") -> None:
    if interactive:
        input(f"\n{message}")


def run_easy_demo(
    image: Path = Path("easy_demo.bin"),
    blocks: int = 256,
    *,
    interactive: bool = False,
) -> None:
    if image.exists():
        image.unlink()

    disk = BlockDevice(image, num_blocks=blocks)
    fs = FileSystem(disk)

    print("\n=== STEP 1: Format volume ===")
    _wait(interactive, "Ready to format the virtual disk. Press Enter...")
    fs.format_disk()
    print(f"Created {image} with {disk.num_blocks} blocks")

    print("\n=== STEP 2: Create directory and file ===")
    _wait(interactive, "Next: create directory + file. Press Enter...")
    fs.mkdir("/docs")
    fs.create_file("/docs/note.txt")
    content = "Initial content"
    if interactive:
        typed = input("Type initial file text (or press Enter for default): ").strip()
        if typed:
            content = typed
    fs.write_file("/docs/note.txt", content.encode("utf-8"))
    print("Wrote /docs/note.txt")
    print("Read back:", fs.read_file("/docs/note.txt").decode("utf-8", errors="replace"))

    print("\n=== STEP 3: Show block map ===")
    _wait(interactive, "View block map now. Press Enter...")
    print(block_map(fs, disk))

    print("\n=== STEP 4: Simulate crash and recover ===")
    _wait(interactive, "Now simulate crash + recovery. Press Enter...")
    snap = snapshot_inode_table(fs, disk)
    recover_text = "Recovered by journal"
    if interactive:
        typed = input("Type recovery write text (or press Enter for default): ").strip()
        if typed:
            recover_text = typed
    fs.write_file("/docs/note.txt", recover_text.encode("utf-8"))
    crash_before_inode_apply(fs, disk, snap)
    applied = fs.recover_from_journal()
    print("Journal records replayed:", applied)
    print("Recovered file:", fs.read_file("/docs/note.txt").decode("utf-8", errors="replace"))

    print("\n=== STEP 5: Show metrics ===")
    _wait(interactive, "Final step: show metrics. Press Enter...")
    print(fs.free_space_report())
    print(fs.metrics)

    print("\nDemo complete. Optional GUI: python main.py gui")


if __name__ == "__main__":
    run_easy_demo()
