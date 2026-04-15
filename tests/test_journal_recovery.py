"""Journal replay and crash simulation."""

from __future__ import annotations

import pytest

from fs_core.block_device import BlockDevice
from fs_core.filesystem import FileSystem
from simulation.crash import crash_before_inode_apply, snapshot_inode_table


def test_recover_after_inode_table_rollback(fs_small: tuple[FileSystem, BlockDevice]) -> None:
    fs, disk = fs_small
    fs.create_file("/j.txt")
    snap = snapshot_inode_table(fs, disk)
    fs.write_file("/j.txt", b"journal-recovery-test")
    crash_before_inode_apply(fs, disk, snap)
    # Stale inode table: empty or old file metadata
    n = fs.recover_from_journal()
    assert n >= 1
    assert fs.read_file("/j.txt") == b"journal-recovery-test"


def test_recover_idempotent(fs_small: tuple[FileSystem, BlockDevice]) -> None:
    fs, disk = fs_small
    fs.create_file("/id.txt")
    fs.write_file("/id.txt", b"ok")
    n1 = fs.recover_from_journal()
    n2 = fs.recover_from_journal()
    assert fs.read_file("/id.txt") == b"ok"
    assert n1 >= 0 and n2 >= 0


def test_parse_journal_empty() -> None:
    from fs_core import journal as jr

    assert jr.parse_journal(b"") == []
    assert jr.parse_journal(b"\x00" * 64) == []
