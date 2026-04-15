"""Core VFS: format, paths, read/write, free space, errors."""

from __future__ import annotations

import pytest

from fs_core.block_device import BlockDevice
from fs_core.constants import BLOCK_SIZE, MAX_DIRECT_BLOCKS
from fs_core.inode import inode_unpack
from fs_core.filesystem import FileSystem, FileSystemError


def test_format_and_superblock_magic(fs_small: tuple[FileSystem, BlockDevice]) -> None:
    fs, disk = fs_small
    assert disk.num_blocks == 128
    raw = disk.read_block(0)
    assert int.from_bytes(raw[:4], "little") == 0x46534F53


def test_mkdir_create_write_read(fs_small: tuple[FileSystem, BlockDevice]) -> None:
    fs, _ = fs_small
    fs.mkdir("/docs")
    fs.create_file("/docs/readme.txt")
    fs.write_file("/docs/readme.txt", b"alpha")
    assert fs.read_file("/docs/readme.txt") == b"alpha"


def test_write_overwrite(fs_small: tuple[FileSystem, BlockDevice]) -> None:
    fs, _ = fs_small
    fs.create_file("/x.bin")
    fs.write_file("/x.bin", b"one")
    fs.write_file("/x.bin", b"two longer")
    assert fs.read_file("/x.bin") == b"two longer"


def test_empty_write_frees_blocks(fs_small: tuple[FileSystem, BlockDevice]) -> None:
    fs, _ = fs_small
    fs.create_file("/e.txt")
    fs.write_file("/e.txt", b"pad" * 200)
    before = fs.free_space_report()["free_data_blocks"]
    fs.write_file("/e.txt", b"")
    after = fs.free_space_report()["free_data_blocks"]
    assert after >= before


def test_duplicate_create_raises(fs_small: tuple[FileSystem, BlockDevice]) -> None:
    fs, _ = fs_small
    fs.create_file("/a.txt")
    with pytest.raises(FileSystemError, match="exists"):
        fs.create_file("/a.txt")


def test_missing_parent_raises(fs_small: tuple[FileSystem, BlockDevice]) -> None:
    fs, _ = fs_small
    with pytest.raises(FileSystemError):
        fs.create_file("/no/such/file.txt")


def test_file_too_large(fs_small: tuple[FileSystem, BlockDevice]) -> None:
    fs, _ = fs_small
    fs.create_file("/big.bin")
    too_big = b"x" * (BLOCK_SIZE * (MAX_DIRECT_BLOCKS + 1))
    with pytest.raises(FileSystemError, match="too large"):
        fs.write_file("/big.bin", too_big)


def test_max_direct_file(fs_small: tuple[FileSystem, BlockDevice]) -> None:
    fs, _ = fs_small
    fs.create_file("/max.bin")
    data = b"Z" * (BLOCK_SIZE * MAX_DIRECT_BLOCKS)
    fs.write_file("/max.bin", data)
    assert fs.read_file("/max.bin") == data


def test_file_metadata_defaults(fs_small: tuple[FileSystem, BlockDevice]) -> None:
    fs, _ = fs_small
    fs.create_file("/meta.txt")
    ino = fs._find_in_dir(fs._sb["root_inode"], "meta.txt")
    t, size, n_used, blks, mode, owner, mtime, ctime = inode_unpack(fs._read_inode_raw(ino))
    assert mode == 0o644
    assert owner == 0
    assert isinstance(mtime, int) and isinstance(ctime, int)


def test_defrag_single_block_no_move(fs_small: tuple[FileSystem, BlockDevice]) -> None:
    fs, _ = fs_small
    fs.create_file("/d.txt")
    fs.write_file("/d.txt", b"short")
    moved, nbytes = fs.defragment_file("/d.txt")
    assert moved == 0
    assert nbytes == len(b"short")


def test_free_space_report_nonnegative(fs_small: tuple[FileSystem, BlockDevice]) -> None:
    fs, _ = fs_small
    r = fs.free_space_report()
    assert r["free_data_blocks"] >= 0
    assert r["free_data_blocks"] <= r["total_data_blocks"]


def test_unlink_file(fs_small: tuple[FileSystem, BlockDevice]) -> None:
    fs, _ = fs_small
    fs.create_file("/tmp.txt")
    fs.write_file("/tmp.txt", b"data")
    before = fs.free_space_report()["free_inodes"]
    fs.unlink("/tmp.txt")
    assert fs.free_space_report()["free_inodes"] >= before
    with pytest.raises(FileSystemError):
        fs.read_file("/tmp.txt")


def test_rmdir_and_dir_semantics(fs_small: tuple[FileSystem, BlockDevice]) -> None:
    fs, _ = fs_small
    fs.mkdir("/a")
    fs.rmdir("/a")
    with pytest.raises(FileSystemError):
        fs.rmdir("/")
    fs.mkdir("/b")
    fs.create_file("/b/x.txt")
    with pytest.raises(FileSystemError, match="directory not empty"):
        fs.rmdir("/b")


def test_scan_and_gc(fs_small: tuple[FileSystem, BlockDevice]) -> None:
    fs, _ = fs_small
    fs.create_file("/o1.txt")
    fs.write_file("/o1.txt", b"hello")
    fs.unlink("/o1.txt")
    report = fs.scan_garbage()
    assert "orphan_inodes" in report
    assert "orphan_blocks" in report
    collect = fs.garbage_collect()
    assert collect["freed_inodes"] >= 0
    assert collect["freed_blocks"] >= 0


def test_checkpoint_truncate_journal(fs_small: tuple[FileSystem, BlockDevice]) -> None:
    fs, _ = fs_small
    fs.create_file("/c.txt")
    fs.write_file("/c.txt", b"abc")
    fs.checkpoint()
    fs.truncate_journal()
    n = fs.recover_from_journal()
    assert n == 0


def test_stat_metadata(fs_small: tuple[FileSystem, BlockDevice]) -> None:
    fs, _ = fs_small
    fs.create_file("/info.txt")
    fs.write_file("/info.txt", b"abc")
    sx = fs.stat("/info.txt")
    assert sx["type"] == "file"
    assert sx["size"] == 3
    assert sx["mode"] == oct(0o644)

    dx = fs.stat("/")
    assert dx["type"] == "dir"


