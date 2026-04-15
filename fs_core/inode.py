"""Inode encode/decode (64-byte records in inode table)."""

from __future__ import annotations

import struct

from fs_core.constants import MAX_DIRECT_BLOCKS

# type, size, used_count, 8 block ids + 4 metadata fields (mode, owner, mtime, ctime)
_INODE_PACK = struct.Struct("<B3xI B7x 8I 4I")


def inode_pack(
    inode_type: int,
    size: int,
    n_used: int,
    blocks: list[int],
    mode: int = 0,
    owner: int = 0,
    mtime: int = 0,
    ctime: int = 0,
) -> bytes:
    bl = list(blocks[:MAX_DIRECT_BLOCKS]) + [0] * MAX_DIRECT_BLOCKS
    bl = bl[:MAX_DIRECT_BLOCKS]
    return _INODE_PACK.pack(inode_type, size, n_used, *bl, mode, owner, mtime, ctime)


def inode_unpack(raw: bytes) -> tuple[int, int, int, list[int], int, int, int, int]:
    if len(raw) < _INODE_PACK.size:
        raw = raw + b"\x00" * (_INODE_PACK.size - len(raw))
    t, size, n_used, *rest = _INODE_PACK.unpack(raw[: _INODE_PACK.size])
    bl = list(rest[:8])
    mode, owner, mtime, ctime = rest[8:12]
    n_used = min(max(int(n_used), 0), MAX_DIRECT_BLOCKS)
    bl = bl[:n_used] if n_used else []
    return int(t), int(size), n_used, bl, int(mode), int(owner), int(mtime), int(ctime)

