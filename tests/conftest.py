"""Shared fixtures for filesystem tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from fs_core.block_device import BlockDevice
from fs_core.filesystem import FileSystem


@pytest.fixture
def tmp_disk_path(tmp_path: Path) -> Path:
    return tmp_path / "vol.bin"


@pytest.fixture
def fs_small(tmp_disk_path: Path) -> tuple[FileSystem, BlockDevice]:
    """Fresh 128-block formatted volume."""
    disk = BlockDevice(tmp_disk_path, num_blocks=128)
    fs = FileSystem(disk)
    fs.format_disk()
    return fs, disk
