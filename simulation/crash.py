"""Simulate partial-commit failures for WAL recovery testing."""

from __future__ import annotations

from fs_core.block_device import BlockDevice
from fs_core.constants import BLOCK_SIZE
from fs_core.filesystem import FileSystem



def snapshot_inode_table(fs: FileSystem, disk: BlockDevice) -> list[bytes]:
    """Copy inode table blocks (for simulating stale metadata after a crash)."""
    sb = fs._sb  # noqa: SLF001 — recovery drill helper
    start = sb["inode_table_start"]
    n = sb["inode_table_blocks"]
    return [disk.read_block(start + i) for i in range(n)]


def restore_inode_table(snapshot: list[bytes], fs: FileSystem, disk: BlockDevice) -> None:
    """Restore inode table from snapshot (e.g. metadata not persisted after journal write)."""
    sb = fs._sb  # noqa: SLF001
    start = sb["inode_table_start"]
    for i, blk in enumerate(snapshot):
        disk.write_block(start + i, blk)
    disk.sync()


def crash_before_inode_apply(
    fs: FileSystem,
    disk: BlockDevice,
    snapshot: list[bytes],
) -> None:
    """Restore inode table to `snapshot` while leaving journal + data blocks as on disk."""
    restore_inode_table(snapshot, fs, disk)


def simulate_random_crash(
    fs: FileSystem,
    disk: BlockDevice,
    operations: list[tuple[str, tuple]],
    crash_probability: float = 0.3,
) -> None:
    """Run ops and possibly crash mid-sequence, then recover."""
    import random

    snapshot = disk.copy_memory()
    for method_name, args in operations:
        if random.random() < crash_probability:
            disk.restore_memory(snapshot)
            break
        method = getattr(fs, method_name)
        method(*args)
        snapshot = disk.copy_memory()
    fs.recover_from_journal()

