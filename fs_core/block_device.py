"""Fixed-size block device backed by a mutable buffer (RAM or file)."""

from __future__ import annotations

import mmap
from pathlib import Path

from fs_core.constants import BLOCK_SIZE


class BlockDevice:
    """Linear array of blocks; all I/O is block-aligned."""

    __slots__ = ("_buf", "_num_blocks", "_path", "_mm", "_file_handle")

    def __init__(self, path: Path | None = None, *, num_blocks: int = 256) -> None:
        self._path = path
        self._mm: mmap.mmap | None = None
        self._file_handle = None
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                existing = path.stat().st_size
                if existing % BLOCK_SIZE != 0:
                    raise ValueError("Image size is not a multiple of block size")
                self._num_blocks = existing // BLOCK_SIZE
                size = existing
            else:
                self._num_blocks = num_blocks
                size = self._num_blocks * BLOCK_SIZE
                path.write_bytes(b"\x00" * size)
            self._file_handle = open(path, "r+b")
            self._mm = mmap.mmap(
                self._file_handle.fileno(),
                0,
                access=mmap.ACCESS_WRITE,
            )
            self._buf = self._mm
        else:
            self._num_blocks = num_blocks
            self._buf = bytearray(self._num_blocks * BLOCK_SIZE)

    @property
    def num_blocks(self) -> int:
        return self._num_blocks

    def read_block(self, index: int) -> bytes:
        if not 0 <= index < self._num_blocks:
            raise IndexError(f"block {index} out of range")
        off = index * BLOCK_SIZE
        return bytes(self._buf[off : off + BLOCK_SIZE])

    def write_block(self, index: int, data: bytes) -> None:
        if not 0 <= index < self._num_blocks:
            raise IndexError(f"block {index} out of range")
        if len(data) != BLOCK_SIZE:
            raise ValueError(f"block must be {BLOCK_SIZE} bytes, got {len(data)}")
        off = index * BLOCK_SIZE
        self._buf[off : off + BLOCK_SIZE] = data

    def sync(self) -> None:
        if self._mm is not None:
            self._mm.flush()

    def close(self) -> None:
        if self._mm is not None:
            self._mm.close()
            self._mm = None
        if self._file_handle is not None:
            self._file_handle.close()
            self._file_handle = None

    def copy_memory(self) -> bytearray:
        """Snapshot for fault injection (crash with partial state)."""
        return bytearray(self._buf)

    def restore_memory(self, snapshot: bytearray) -> None:
        if len(snapshot) != len(self._buf):
            raise ValueError("snapshot size mismatch")
        self._buf[:] = snapshot
