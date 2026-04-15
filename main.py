#!/usr/bin/env python3
"""CLI for the simulated file system: format, files, journal recovery, scenarios."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from fs_core.block_device import BlockDevice
from fs_core.filesystem import FileSystem, FileSystemError
from simulation.crash import crash_before_inode_apply, snapshot_inode_table
from viz import block_map


def _open_fs(path: Path, blocks: int, create: bool) -> tuple[FileSystem, BlockDevice]:
    if not create and not path.exists():
        raise SystemExit(f"missing image: {path}")
    if create and path.exists():
        path.unlink()
    disk = BlockDevice(path, num_blocks=blocks)
    fs = FileSystem(disk)
    if create:
        fs.format_disk()
    else:
        fs.load_existing()
    return fs, disk


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="File system recovery & optimization simulator",
        epilog="""Put global options before subcommand, e.g.:
  python main.py --image demo.bin --blocks 256 format

Quick examples:
  python main.py --image demo.bin --blocks 256 format
  python main.py --image demo.bin create /hello.txt
  python main.py --image demo.bin write /hello.txt "Hello FS!"
  python main.py --image demo.bin map
  python main.py --image demo.bin demo-crash /hello.txt "Recovered!"
  python main.py gui

See README.md for full tutorial.""",
    )
    p.add_argument("--image", type=Path, default=Path("fs_image.bin"))
    p.add_argument("--blocks", type=int, default=256, help="total block count")
    sub = p.add_subparsers(dest="cmd", required=True)

    s_fmt = sub.add_parser("format", help="create new volume")
    s_mk = sub.add_parser("mkdir", help="create directory")
    s_mk.add_argument("path")
    s_touch = sub.add_parser("create", help="create empty file")
    s_touch.add_argument("path")
    s_w = sub.add_parser("write", help="write file contents (UTF-8)")
    s_w.add_argument("path")
    s_w.add_argument("text")
    s_r = sub.add_parser("read", help="read file")
    s_r.add_argument("path")
    s_map = sub.add_parser("map", help="print block layout map")
    s_fs = sub.add_parser("free", help="free space / inode report")
    s_def = sub.add_parser("defrag", help="rewrite file blocks (sequential placement)")
    s_def.add_argument("path")
    s_unlink = sub.add_parser("unlink", help="remove file")
    s_unlink.add_argument("path")
    s_rmdir = sub.add_parser("rmdir", help="remove empty directory")
    s_rmdir.add_argument("path")
    s_scan = sub.add_parser("scan", help="scan filesystem garbage")
    s_gc = sub.add_parser("gc", help="garbage collect orphaned inodes/blocks")
    s_trunc = sub.add_parser("truncate-journal", help="clear journal with checkpoint")
    s_checkpoint = sub.add_parser("checkpoint", help="replay and truncate journal")
    s_rec = sub.add_parser("recover", help="replay committed journal transactions")
    s_demo = sub.add_parser("demo-crash", help="snapshot -> write -> crash -> recover")
    s_demo.add_argument("path")
    s_demo.add_argument("text", nargs="?", default="recovered-by-journal")
    s_stat = sub.add_parser("stat", help="show inode metadata")
    s_stat.add_argument("path")
    s_rand = sub.add_parser("random-crash", help="run operations with random crash sim")
    s_rand.add_argument("path")
    s_rand.add_argument("text", nargs="?", default="random-crash")
    s_help = sub.add_parser("help", help="show overview and examples")
    s_easy = sub.add_parser("easy-demo", help="run one-command full project demonstration")
    s_easy.add_argument(
        "--interactive",
        action="store_true",
        help="pause between steps and ask for demo text inputs",
    )
    sub.add_parser("gui", help="open Tkinter block map and tools")

    args = p.parse_args(argv)

    try:
        if args.cmd == "help":
            print("""FS Recovery Lab CLI Help

Quick Examples:
  format --blocks 256 demo.bin
  --image demo.bin create /hello.txt
  --image demo.bin write /hello.txt "Hi!"
  --image demo.bin map
  --image demo.bin demo-crash /test.txt

Full list: format mkdir create write read map free stat defrag unlink rmdir scan gc recover checkpoint demo-crash random-crash gui help

See README.md for tutorial!""")
            return 0

        if args.cmd == "gui":
            from fs_gui import run_app

            run_app()
            return 0

        if args.cmd == "easy-demo":
            from easy_demo import run_easy_demo

            run_easy_demo(args.image, args.blocks, interactive=args.interactive)
            return 0

        if args.cmd == "format":
            fs, disk = _open_fs(args.image, args.blocks, create=True)
            print("Formatted:", args.image, "blocks=", disk.num_blocks)
            print(block_map(fs, disk))
            return 0

        if args.cmd == "demo-crash":
            fs, disk = _open_fs(args.image, args.blocks, create=False)
            snap = snapshot_inode_table(fs, disk)
            fs.write_file(args.path, args.text.encode("utf-8"))
            crash_before_inode_apply(fs, disk, snap)
            n = fs.recover_from_journal()
            data = fs.read_file(args.path)
            print("Recovered inode updates:", n)
            print("Read back:", data.decode("utf-8", errors="replace"))
            return 0

        fs, disk = _open_fs(args.image, args.blocks, create=False)

        if args.cmd == "mkdir":
            fs.mkdir(args.path)
            print("mkdir:", args.path)
        elif args.cmd == "create":
            fs.create_file(args.path)
            print("create:", args.path)
        elif args.cmd == "unlink":
            fs.unlink(args.path)
            print("unlink:", args.path)
        elif args.cmd == "rmdir":
            fs.rmdir(args.path)
            print("rmdir:", args.path)
        elif args.cmd == "write":
            fs.write_file(args.path, args.text.encode("utf-8"))
            print("write:", args.path, "bytes=", len(args.text.encode("utf-8")))
        elif args.cmd == "read":
            print(fs.read_file(args.path).decode("utf-8", errors="replace"))
        elif args.cmd == "map":
            print(block_map(fs, disk))
        elif args.cmd == "free":
            print(fs.free_space_report())
            print("metrics:", fs.metrics)
        elif args.cmd == "defrag":
            moved, nbytes = fs.defragment_file(args.path)
            print("blocks_relocated=", moved, "file_bytes=", nbytes)
        elif args.cmd == "scan":
            print(fs.scan_garbage())
        elif args.cmd == "gc":
            print(fs.garbage_collect())
        elif args.cmd == "truncate-journal":
            fs.truncate_journal()
            print("journal truncated")
        elif args.cmd == "checkpoint":
            fs.checkpoint()
            print("checkpoint complete")
        elif args.cmd == "stat":
            info = fs.stat(args.path)
            print(info)
        elif args.cmd == "recover":
            n = fs.recover_from_journal()
            print("applied inode records:", n, "recovery_ms=", fs.metrics.get("recovery_time_ms"))
        elif args.cmd == "random-crash":
            from simulation.crash import simulate_random_crash

            operations = [
                ("write_file", (args.path, args.text.encode("utf-8"))),
                ("read_file", (args.path,)),
            ]
            simulate_random_crash(fs, disk, operations)
            print("random crash simulation complete")
        return 0
    except FileSystemError as e:
        print("FS error:", e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
