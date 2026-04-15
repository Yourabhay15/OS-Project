"""Visualization helpers."""

from __future__ import annotations

from fs_core.block_device import BlockDevice
from fs_core.filesystem import FileSystem
from viz import block_map, block_roles


def test_block_roles_length_matches_disk(tmp_path) -> None:
    p = tmp_path / "v.bin"
    disk = BlockDevice(p, num_blocks=64)
    fs = FileSystem(disk)
    fs.format_disk()
    roles = block_roles(fs, disk)
    assert len(roles) == disk.num_blocks
    assert roles[0] == "superblock"
    m = block_map(fs, disk)
    assert "S" in m and "J" in m
