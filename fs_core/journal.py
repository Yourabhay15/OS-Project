"""Write-ahead journal: persist metadata before commit; replay on recovery."""

from __future__ import annotations

import struct

from fs_core.constants import BLOCK_SIZE

JR_TX_BEGIN = 1
JR_INODE = 2
JR_COMMIT = 3


def serialize_journal(tx_id: int, inode_records: list[tuple[int, bytes]]) -> bytes:
    parts: list[bytes] = [struct.pack("<II", JR_TX_BEGIN, tx_id)]
    for ino, raw in inode_records:
        parts.append(struct.pack("<II", JR_INODE, ino))
        parts.append(raw[:64].ljust(64, b"\x00"))
    parts.append(struct.pack("<I", JR_COMMIT))
    return b"".join(parts)


def parse_journal(blob: bytes) -> list[tuple[int, list[tuple[int, bytes]], bool]]:
    """
    Parse linear journal bytes into transactions (tx_id, inode records, committed).
    """
    out: list[tuple[int, list[tuple[int, bytes]], bool]] = []
    off = 0
    while off + 8 <= len(blob):
        tag = struct.unpack_from("<I", blob, off)[0]
        if tag != JR_TX_BEGIN:
            break
        tx_id = struct.unpack_from("<I", blob, off + 4)[0]
        off += 8
        recs: list[tuple[int, bytes]] = []
        committed = False
        while off + 4 <= len(blob):
            t = struct.unpack_from("<I", blob, off)[0]
            if t == JR_INODE:
                if off + 8 + 64 > len(blob):
                    break
                ino = struct.unpack_from("<I", blob, off + 4)[0]
                raw = bytes(blob[off + 8 : off + 8 + 64])
                recs.append((ino, raw))
                off += 8 + 64
            elif t == JR_COMMIT:
                committed = True
                off += 4
                break
            else:
                break
        out.append((tx_id, recs, committed))
    return out


def journal_bytes_to_blocks(data: bytes, journal_block_count: int) -> list[bytes]:
    cap = journal_block_count * BLOCK_SIZE
    padded = data[:cap].ljust(cap, b"\x00")
    return [padded[i * BLOCK_SIZE : (i + 1) * BLOCK_SIZE] for i in range(journal_block_count)]


def blocks_to_journal_bytes(blocks: list[bytes]) -> bytes:
    return b"".join(blocks)
