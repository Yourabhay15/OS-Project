"""Simulated file system: allocation, directories, files, journaling hooks."""

from __future__ import annotations

import math
import struct
import time

from fs_core.bitmap import bitmap_get, bitmap_set
from fs_core.block_device import BlockDevice
from fs_core.constants import (
    BLOCK_SIZE,
    DIR_ENTRY_SIZE,
    FORMAT_VERSION,
    INODE_DIR,
    INODE_FILE,
    INODE_SIZE,
    MAX_DIRECT_BLOCKS,
    MAX_NAME_LEN,
    NUM_INODES,
    SUPERBLOCK_MAGIC,
    SUPERBLOCK_STRUCT,
)
from fs_core.inode import inode_pack, inode_unpack
from fs_core import journal as jr

_DIR_ENTRY = struct.Struct("<I60s")


class FileSystemError(Exception):
    pass


class FileSystem:
    def __init__(self, disk: BlockDevice) -> None:
        self._disk = disk
        self._sb: dict[str, int] = {}
        self._tx_id = 1
        self._pending_inode: list[tuple[int, bytes]] = []
        self._in_tx = False
        # Metrics (simulated I/O cost)
        self.metrics = {
            "block_reads": 0,
            "block_writes": 0,
            "bytes_read": 0,
            "bytes_written": 0,
            "journal_writes": 0,
            "recovery_time_ms": 0.0,
        }

    # --- superblock & bitmaps ---

    def _read_superblock(self) -> dict[str, int]:
        raw = self._disk.read_block(0)
        self.metrics["block_reads"] += 1
        vals = SUPERBLOCK_STRUCT.unpack(raw[: SUPERBLOCK_STRUCT.size])
        keys = (
            "magic",
            "version",
            "total_blocks",
            "block_size",
            "inode_bitmap_start",
            "inode_bitmap_blocks",
            "block_bitmap_start",
            "block_bitmap_blocks",
            "inode_table_start",
            "inode_table_blocks",
            "data_start",
            "data_block_count",
            "journal_start",
            "journal_block_count",
            "root_inode",
            "journal_seq",
        )
        return dict(zip(keys, vals, strict=True))

    def _write_superblock(self) -> None:
        vals = (
            self._sb["magic"],
            self._sb["version"],
            self._sb["total_blocks"],
            self._sb["block_size"],
            self._sb["inode_bitmap_start"],
            self._sb["inode_bitmap_blocks"],
            self._sb["block_bitmap_start"],
            self._sb["block_bitmap_blocks"],
            self._sb["inode_table_start"],
            self._sb["inode_table_blocks"],
            self._sb["data_start"],
            self._sb["data_block_count"],
            self._sb["journal_start"],
            self._sb["journal_block_count"],
            self._sb["root_inode"],
            self._sb["journal_seq"],
        )
        buf = bytearray(BLOCK_SIZE)
        buf[: SUPERBLOCK_STRUCT.size] = SUPERBLOCK_STRUCT.pack(*vals)
        self._disk.write_block(0, bytes(buf))
        self.metrics["block_writes"] += 1

    def _inode_bitmap_block(self) -> bytes:
        return self._disk.read_block(self._sb["inode_bitmap_start"])

    def _block_bitmap_block(self) -> bytes:
        return self._disk.read_block(self._sb["block_bitmap_start"])

    def _write_inode_bitmap(self, data: bytes) -> None:
        buf = bytearray(BLOCK_SIZE)
        buf[: len(data)] = data
        self._disk.write_block(self._sb["inode_bitmap_start"], bytes(buf))
        self.metrics["block_writes"] += 1

    def _write_block_bitmap(self, data: bytes) -> None:
        buf = bytearray(BLOCK_SIZE)
        buf[: len(data)] = data
        self._disk.write_block(self._sb["block_bitmap_start"], bytes(buf))
        self.metrics["block_writes"] += 1

    def _read_inode_raw(self, ino: int) -> bytes:
        if not 0 <= ino < NUM_INODES:
            raise FileSystemError(f"bad inode {ino}")
        off = ino * INODE_SIZE
        block = self._sb["inode_table_start"] + off // BLOCK_SIZE
        rel = off % BLOCK_SIZE
        raw = self._disk.read_block(block)
        self.metrics["block_reads"] += 1
        return raw[rel : rel + INODE_SIZE]

    def _write_inode_raw(self, ino: int, raw: bytes) -> None:
        if not 0 <= ino < NUM_INODES:
            raise FileSystemError(f"bad inode {ino}")
        off = ino * INODE_SIZE
        block = self._sb["inode_table_start"] + off // BLOCK_SIZE
        rel = off % BLOCK_SIZE
        br = self._disk.read_block(block)
        self.metrics["block_reads"] += 1
        buf = bytearray(br)
        buf[rel : rel + INODE_SIZE] = raw[:INODE_SIZE].ljust(INODE_SIZE, b"\x00")
        self._disk.write_block(block, bytes(buf))
        self.metrics["block_writes"] += 1

    def format_disk(self) -> None:
        tb = self._disk.num_blocks
        if tb < 32:
            raise FileSystemError("disk too small (need >= 32 blocks)")
        inode_table_blocks = math.ceil((NUM_INODES * INODE_SIZE) / BLOCK_SIZE)
        journal_block_count = min(8, max(1, tb // 32))
        inode_bitmap_start = 1
        block_bitmap_start = 2
        inode_table_start = 3
        data_start = inode_table_start + inode_table_blocks
        data_block_count = tb - data_start - journal_block_count
        if data_block_count < 4:
            raise FileSystemError("disk too small for data region")
        journal_start = data_start + data_block_count
        self._sb = {
            "magic": SUPERBLOCK_MAGIC,
            "version": FORMAT_VERSION,
            "total_blocks": tb,
            "block_size": BLOCK_SIZE,
            "inode_bitmap_start": inode_bitmap_start,
            "inode_bitmap_blocks": 1,
            "block_bitmap_start": block_bitmap_start,
            "block_bitmap_blocks": 1,
            "inode_table_start": inode_table_start,
            "inode_table_blocks": inode_table_blocks,
            "data_start": data_start,
            "data_block_count": data_block_count,
            "journal_start": journal_start,
            "journal_block_count": journal_block_count,
            "root_inode": 1,
            "journal_seq": 0,
        }
        # clear disk
        for i in range(tb):
            self._disk.write_block(i, b"\x00" * BLOCK_SIZE)
            self.metrics["block_writes"] += 1
        self._write_superblock()
        ibm = bytearray(BLOCK_SIZE)
        bbm = bytearray(BLOCK_SIZE)
        bitmap_set(ibm, 0, True)
        bitmap_set(ibm, 1, True)
        self._write_inode_bitmap(bytes(ibm))
        self._write_block_bitmap(bytes(bbm))
        # root directory inode + one data block for entries
        root_block_rel = self._alloc_data_block()
        root_raw = inode_pack(INODE_DIR, 0, 1, [root_block_rel])
        self._write_inode_raw(1, root_raw)
        # write . and .. in root block
        ent = self._encode_dir_entry(1, ".") + self._encode_dir_entry(1, "..")
        self._write_data_block_rel(root_block_rel, ent.ljust(BLOCK_SIZE, b"\x00"))

    @staticmethod
    def _encode_dir_entry(ino: int, name: str) -> bytes:
        n = name.encode("utf-8")[:MAX_NAME_LEN]
        return _DIR_ENTRY.pack(ino, n.ljust(60, b"\x00"))

    def _decode_dir_block(self, data: bytes) -> list[tuple[int, str]]:
        entries: list[tuple[int, str]] = []
        for off in range(0, len(data), DIR_ENTRY_SIZE):
            chunk = data[off : off + DIR_ENTRY_SIZE]
            if len(chunk) < DIR_ENTRY_SIZE:
                break
            ino, raw = _DIR_ENTRY.unpack(chunk)
            if ino == 0:
                continue
            name = raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
            entries.append((ino, name))
        return entries

    def _alloc_inode(self) -> int:
        ibm = bytearray(self._inode_bitmap_block())
        self.metrics["block_reads"] += 1
        for i in range(NUM_INODES):
            if not bitmap_get(bytes(ibm), i):
                bitmap_set(ibm, i, True)
                self._write_inode_bitmap(bytes(ibm))
                return i
        raise FileSystemError("out of inodes")

    def _free_inode(self, ino: int) -> None:
        ibm = bytearray(self._inode_bitmap_block())
        self.metrics["block_reads"] += 1
        bitmap_set(ibm, ino, False)
        self._write_inode_bitmap(bytes(ibm))

    def _alloc_data_block(self) -> int:
        """Return relative index (0..data_block_count-1); caller maps to absolute."""
        bbm = bytearray(self._block_bitmap_block())
        self.metrics["block_reads"] += 1
        n = self._sb["data_block_count"]
        for i in range(n):
            if not bitmap_get(bytes(bbm), i):
                bitmap_set(bbm, i, True)
                self._write_block_bitmap(bytes(bbm))
                return i
        raise FileSystemError("disk full")

    def _rel_to_abs(self, rel: int) -> int:
        return self._sb["data_start"] + rel

    def _free_data_block(self, rel: int) -> None:
        bbm = bytearray(self._block_bitmap_block())
        self.metrics["block_reads"] += 1
        bitmap_set(bbm, rel, False)
        self._write_block_bitmap(bytes(bbm))

    def _write_data_block_rel(self, rel: int, data: bytes) -> None:
        if len(data) != BLOCK_SIZE:
            data = data.ljust(BLOCK_SIZE, b"\x00")[:BLOCK_SIZE]
        self._disk.write_block(self._rel_to_abs(rel), data)
        self.metrics["block_writes"] += 1

    def _read_data_block_rel(self, rel: int) -> bytes:
        self.metrics["block_reads"] += 1
        return self._disk.read_block(self._rel_to_abs(rel))

    def load_existing(self) -> None:
        self._sb = self._read_superblock()
        if self._sb["magic"] != SUPERBLOCK_MAGIC:
            raise FileSystemError("not a formatted volume")

    # --- paths ---

    def _resolve(self, path: str) -> tuple[int, str | None]:
        """Return (existing_inode, None) if the full path exists; else (parent_inode, basename)."""
        parts = [p for p in path.strip("/").split("/") if p]
        if not parts:
            return self._sb["root_inode"], None
        cur = self._sb["root_inode"]
        for i, name in enumerate(parts):
            is_last = i == len(parts) - 1
            t, _size, n_used, blks, _mode, _owner, _mtime, _ctime = inode_unpack(self._read_inode_raw(cur))
            if t != INODE_DIR:
                raise FileSystemError("not a directory")
            found = self._find_in_dir(cur, name)
            if is_last:
                if found is not None:
                    return (found, None)
                return (cur, name)
            if found is None:
                raise FileSystemError(f"not found: {name}")
            cur = found
        return cur, None

    def _find_in_dir(self, dir_ino: int, name: str) -> int | None:
        t, _size, n_used, blks, _mode, _owner, _mtime, _ctime = inode_unpack(self._read_inode_raw(dir_ino))
        for j in range(n_used):
            rel = blks[j]
            data = self._read_data_block_rel(rel)
            for ino, nm in self._decode_dir_block(data):
                if nm == name:
                    return ino
        return None

    def _add_dir_entry(self, dir_ino: int, name: str, child_ino: int) -> None:
        t, size, n_used, blks, mode, owner, mtime, ctime = inode_unpack(self._read_inode_raw(dir_ino))
        if t != INODE_DIR:
            raise FileSystemError("not a directory")
        if self._find_in_dir(dir_ino, name) is not None:
            raise FileSystemError("entry exists")
        ent = self._encode_dir_entry(child_ino, name)
        blks_list = list(blks[:MAX_DIRECT_BLOCKS]) + [0] * max(0, MAX_DIRECT_BLOCKS - len(blks))
        blks_list = blks_list[:MAX_DIRECT_BLOCKS]
        if n_used == 0:
            rel = self._alloc_data_block()
            blks_list[0] = rel
            n_used = 1
            now = int(time.time())
            buf = bytearray(BLOCK_SIZE)
            buf[0:DIR_ENTRY_SIZE] = ent
            self._write_data_block_rel(rel, bytes(buf))
            new_raw = inode_pack(INODE_DIR, size + len(ent), n_used, blks_list, mode=mode, owner=owner, mtime=now, ctime=ctime)
            self._journal_inode(dir_ino, new_raw)
            return
        for i in range(n_used):
            rel = blks_list[i]
            block = bytearray(self._read_data_block_rel(rel))
            for off in range(0, BLOCK_SIZE, DIR_ENTRY_SIZE):
                chunk = block[off : off + DIR_ENTRY_SIZE]
                if len(chunk) < DIR_ENTRY_SIZE:
                    break
                ino_e, _ = _DIR_ENTRY.unpack(chunk)
                if ino_e == 0:
                    block[off : off + DIR_ENTRY_SIZE] = ent
                    self._write_data_block_rel(rel, bytes(block))
                    now = int(time.time())
                    new_raw = inode_pack(INODE_DIR, size + len(ent), n_used, blks_list, mode=mode, owner=owner, mtime=now, ctime=ctime)
                    self._journal_inode(dir_ino, new_raw)
                    return
        if n_used >= MAX_DIRECT_BLOCKS:
            raise FileSystemError("directory full")
        rel = self._alloc_data_block()
        blks_list[n_used] = rel
        n_used += 1
        now = int(time.time())
        buf = bytearray(BLOCK_SIZE)
        buf[0:DIR_ENTRY_SIZE] = ent
        self._write_data_block_rel(rel, bytes(buf))
        new_raw = inode_pack(INODE_DIR, size + len(ent), n_used, blks_list, mode=mode, owner=owner, mtime=now, ctime=ctime)
        self._journal_inode(dir_ino, new_raw)

    def _remove_dir_entry(self, dir_ino: int, name: str) -> None:
        t, size, n_used, blks, mode, owner, mtime, ctime = inode_unpack(self._read_inode_raw(dir_ino))
        if t != INODE_DIR:
            raise FileSystemError("not a directory")
        if name in (".", ".."):
            raise FileSystemError("cannot remove special directory entry")

        removed = False
        for i in range(n_used):
            rel = blks[i]
            data = bytearray(self._read_data_block_rel(rel))
            for off in range(0, BLOCK_SIZE, DIR_ENTRY_SIZE):
                ino_e, nm = _DIR_ENTRY.unpack(data[off : off + DIR_ENTRY_SIZE])
                if ino_e != 0 and nm.split(b"\x00", 1)[0].decode("utf-8") == name:
                    data[off : off + 4] = b"\x00\x00\x00\x00"
                    self._write_data_block_rel(rel, bytes(data))
                    removed = True
                    break
            if removed:
                break

        if not removed:
            raise FileSystemError("not found")

        # Adjust directory size but keep block structure simple
        new_size = max(0, size - DIR_ENTRY_SIZE)
        now = int(time.time())
        raw = inode_pack(INODE_DIR, new_size, n_used, blks, mode=mode, owner=owner, mtime=now, ctime=ctime)
        self._journal_inode(dir_ino, raw)

    def _is_dir_empty(self, dir_ino: int) -> bool:
        t, _size, n_used, blks, _mode, _owner, _mtime, _ctime = inode_unpack(self._read_inode_raw(dir_ino))
        if t != INODE_DIR:
            raise FileSystemError("not a directory")
        for i in range(n_used):
            rel = blks[i]
            data = self._read_data_block_rel(rel)
            for ino, nm in self._decode_dir_block(data):
                if nm not in (".", ".."):
                    return False
        return True

    def _resolve_parent(self, path: str) -> tuple[int, str]:
        parts = [p for p in path.strip("/").split("/") if p]
        if not parts:
            raise FileSystemError("invalid path")
        parent = self._sb["root_inode"]
        for name in parts[:-1]:
            nxt = self._find_in_dir(parent, name)
            if nxt is None:
                raise FileSystemError(f"not found: {name}")
            parent = nxt
        return parent, parts[-1]

    def mkdir(self, path: str) -> None:
        self.begin_transaction()
        try:
            parent, name = self._resolve(path)
            if name is None:
                raise FileSystemError("exists")
            ino = self._alloc_inode()
            rel = self._alloc_data_block()
            ent = self._encode_dir_entry(ino, ".") + self._encode_dir_entry(parent, "..")
            self._write_data_block_rel(rel, ent.ljust(BLOCK_SIZE, b"\x00"))
            now = int(time.time())
            raw = inode_pack(INODE_DIR, len(ent), 1, [rel], mode=0o755, owner=0, mtime=now, ctime=now)
            self._journal_inode(ino, raw)
            self._add_dir_entry(parent, name, ino)
            self.commit_transaction()
        except Exception:
            self._pending_inode.clear()
            self._in_tx = False
            raise

    def create_file(self, path: str) -> None:
        self.begin_transaction()
        try:
            parent, name = self._resolve(path)
            if name is None:
                raise FileSystemError("exists")
            ino = self._alloc_inode()
            now = int(time.time())
            raw = inode_pack(INODE_FILE, 0, 0, [], mode=0o644, owner=0, mtime=now, ctime=now)
            self._journal_inode(ino, raw)
            self._add_dir_entry(parent, name, ino)
            self.commit_transaction()
        except Exception:
            self._pending_inode.clear()
            self._in_tx = False
            raise

    def unlink(self, path: str) -> None:
        parent, name = self._resolve_parent(path)
        if not name:
            raise FileSystemError("invalid path")
        target = self._find_in_dir(parent, name)
        if target is None:
            raise FileSystemError("not found")

        t, size, n_used, blks, mode, owner, mtime, ctime = inode_unpack(self._read_inode_raw(target))
        if t != INODE_FILE:
            raise FileSystemError("not a file")

        self.begin_transaction()
        try:
            self._remove_dir_entry(parent, name)
            self._journal_inode(target, inode_pack(0, 0, 0, [], mode=0, owner=0, mtime=0, ctime=0))
            self.commit_transaction()
        except Exception:
            self._pending_inode.clear()
            self._in_tx = False
            raise

        for rel in blks[:n_used]:
            self._free_data_block(rel)
        self._free_inode(target)

    def rmdir(self, path: str) -> None:
        if path == "/":
            raise FileSystemError("cannot remove root")

        parent, name = self._resolve_parent(path)
        target = self._find_in_dir(parent, name)
        if target is None:
            raise FileSystemError("not found")

        t, size, n_used, blks, mode, owner, mtime, ctime = inode_unpack(self._read_inode_raw(target))
        if t != INODE_DIR:
            raise FileSystemError("not a directory")
        if not self._is_dir_empty(target):
            raise FileSystemError("directory not empty")

        t, size, n_used, blks, mode, owner, mtime, ctime = inode_unpack(self._read_inode_raw(target))
        if t != INODE_DIR:
            raise FileSystemError("not a directory")
        if not self._is_dir_empty(target):
            raise FileSystemError("directory not empty")

        self.begin_transaction()
        try:
            self._remove_dir_entry(parent, name)
            self._journal_inode(target, inode_pack(0, 0, 0, [], mode=0, owner=0, mtime=0, ctime=0))
            self.commit_transaction()
        except Exception:
            self._pending_inode.clear()
            self._in_tx = False
            raise

        for rel in blks[:n_used]:
            self._free_data_block(rel)
        self._free_inode(target)

    def write_file(self, path: str, data: bytes) -> None:
        parts = [p for p in path.strip("/").split("/") if p]
        if not parts:
            raise FileSystemError("cannot write root")
        parent_ino = self._sb["root_inode"]
        for name in parts[:-1]:
            nxt = self._find_in_dir(parent_ino, name)
            if nxt is None:
                raise FileSystemError(f"missing dir {name}")
            parent_ino = nxt
        fname = parts[-1]
        ino = self._find_in_dir(parent_ino, fname)
        if ino is None:
            raise FileSystemError("file not found")
        t, size, n_used, blks, mode, owner, mtime, ctime = inode_unpack(self._read_inode_raw(ino))
        if t != INODE_FILE:
            raise FileSystemError("not a file")
        old_blks = list(blks[:n_used])
        now = int(time.time())
        self.begin_transaction()
        try:
            if len(data) == 0:
                raw = inode_pack(INODE_FILE, 0, 0, [], mode=mode, owner=owner, mtime=now, ctime=ctime)
                self._journal_inode(ino, raw)
                self.commit_transaction()
                for old in old_blks:
                    self._free_data_block(old)
                return
            need = math.ceil(len(data) / BLOCK_SIZE)
            if need > MAX_DIRECT_BLOCKS:
                raise FileSystemError("file too large for direct blocks")
            new_blks: list[int] = []
            for i in range(need):
                rel = self._alloc_data_block()
                new_blks.append(rel)
                chunk = data[i * BLOCK_SIZE : (i + 1) * BLOCK_SIZE]
                self._write_data_block_rel(rel, chunk.ljust(BLOCK_SIZE, b"\x00"))
            raw = inode_pack(INODE_FILE, len(data), need, new_blks, mode=mode, owner=owner, mtime=now, ctime=ctime)
            self._journal_inode(ino, raw)
            self.commit_transaction()
            for old in old_blks:
                self._free_data_block(old)
            self.metrics["bytes_written"] += len(data)
        except Exception:
            self._pending_inode.clear()
            self._in_tx = False
            raise

    def read_file(self, path: str) -> bytes:
        parts = [p for p in path.strip("/").split("/") if p]
        if not parts:
            raise FileSystemError("cannot read root as file")
        parent_ino = self._sb["root_inode"]
        for name in parts[:-1]:
            nxt = self._find_in_dir(parent_ino, name)
            if nxt is None:
                raise FileSystemError(f"missing dir {name}")
            parent_ino = nxt
        ino = self._find_in_dir(parent_ino, parts[-1])
        if ino is None:
            raise FileSystemError("not found")
        t, size, n_used, blks, _mode, _owner, _mtime, _ctime = inode_unpack(self._read_inode_raw(ino))
        if t != INODE_FILE:
            raise FileSystemError("not a file")
        out = bytearray()
        for i in range(n_used):
            out.extend(self._read_data_block_rel(blks[i]))
        self.metrics["bytes_read"] += min(size, len(out))
        return bytes(out[:size])

    def stat(self, path: str) -> dict[str, int | str]:
        parent, name = self._resolve(path)
        if name is not None:
            raise FileSystemError("not found")
        ino = parent
        t, size, n_used, blks, mode, owner, mtime, ctime = inode_unpack(self._read_inode_raw(ino))
        info = {
            "inode": ino,
            "type": "dir" if t == INODE_DIR else "file" if t == INODE_FILE else "unknown",
            "size": size,
            "blocks": n_used,
            "mode": oct(mode),
            "owner": owner,
            "mtime": mtime,
            "ctime": ctime,
        }
        return info

    # --- journaling ---

    def begin_transaction(self) -> None:
        self._in_tx = True
        self._pending_inode = []

    def _journal_inode(self, ino: int, raw: bytes) -> None:
        self._pending_inode.append((ino, raw))
        if not self._in_tx:
            self._write_inode_raw(ino, raw)

    def commit_transaction(self) -> None:
        if not self._pending_inode:
            self._in_tx = False
            return
        blob = jr.serialize_journal(self._tx_id, self._pending_inode)
        self._tx_id += 1
        blocks = jr.journal_bytes_to_blocks(blob, self._sb["journal_block_count"])
        js = self._sb["journal_start"]
        for i, blk in enumerate(blocks):
            self._disk.write_block(js + i, blk)
            self.metrics["block_writes"] += 1
        self.metrics["journal_writes"] += 1
        self._disk.sync()
        for ino, raw in self._pending_inode:
            self._write_inode_raw(ino, raw)
        self._sb["journal_seq"] = self._sb.get("journal_seq", 0) + 1
        self._write_superblock()
        self._disk.sync()
        self._pending_inode = []
        self._in_tx = False

    def recover_from_journal(self) -> int:
        """Replay journal; return number of inode updates applied."""
        t0 = time.perf_counter()
        js = self._sb["journal_start"]
        jc = self._sb["journal_block_count"]
        parts = [self._disk.read_block(js + i) for i in range(jc)]
        self.metrics["block_reads"] += jc
        blob = jr.blocks_to_journal_bytes(parts)
        txs = jr.parse_journal(blob)
        applied = 0
        for _tx_id, recs, committed in txs:
            if not committed or not recs:
                continue
            for ino, raw in recs:
                self._write_inode_raw(ino, raw)
                applied += 1
        self.metrics["recovery_time_ms"] = (time.perf_counter() - t0) * 1000
        return applied

    # --- optimization: sequentialize file blocks ---

    def defragment_file(self, path: str) -> tuple[int, int]:
        """Relocate file blocks to lowest free slots (greedy). Returns (blocks_moved, bytes)."""
        parts = [p for p in path.strip("/").split("/") if p]
        parent_ino = self._sb["root_inode"]
        for name in parts[:-1]:
            nxt = self._find_in_dir(parent_ino, name)
            if nxt is None:
                raise FileSystemError(f"missing dir {name}")
            parent_ino = nxt
        ino = self._find_in_dir(parent_ino, parts[-1])
        if ino is None:
            raise FileSystemError("not found")
        t, size, n_used, blks, mode, owner, mtime, ctime = inode_unpack(self._read_inode_raw(ino))
        if t != INODE_FILE:
            raise FileSystemError("not a file")
        if n_used <= 1:
            return 0, size
        data = self.read_file(path)
        self.write_file(path, data)
        old_order = blks[:n_used]
        t2, _, n2, new_blks, _mode2, _owner2, _mtime2, _ctime2 = inode_unpack(self._read_inode_raw(ino))
        moved = sum(1 for a, b in zip(old_order, new_blks[:n_used], strict=False) if a != b)
        return moved, size

    def free_space_report(self) -> dict[str, int]:
        bbm = self._block_bitmap_block()
        self.metrics["block_reads"] += 1
        free = sum(
            1 for i in range(self._sb["data_block_count"]) if not bitmap_get(bytes(bbm), i)
        )
        ibm = self._inode_bitmap_block()
        self.metrics["block_reads"] += 1
        ifree = sum(1 for i in range(NUM_INODES) if not bitmap_get(bytes(ibm), i))
        return {
            "free_data_blocks": free,
            "total_data_blocks": self._sb["data_block_count"],
            "free_inodes": ifree,
            "total_inodes": NUM_INODES,
        }

    def scan_garbage(self) -> dict[str, list[int]]:
        live_inodes = set()
        pending = [self._sb["root_inode"]]
        while pending:
            ino = pending.pop()
            if ino in live_inodes:
                continue
            live_inodes.add(ino)
            t, _size, n_used, blks, _mode, _owner, _mtime, _ctime = inode_unpack(self._read_inode_raw(ino))
            if t == INODE_DIR:
                for i in range(n_used):
                    for child_ino, child_name in self._decode_dir_block(self._read_data_block_rel(blks[i])):
                        if child_ino and child_name not in (".", ".."):
                            pending.append(child_ino)

        ibm = self._inode_bitmap_block()
        used_inodes = {i for i in range(NUM_INODES) if bitmap_get(bytes(ibm), i)}
        orphan_inodes = sorted(list(used_inodes - live_inodes))

        bbm = self._block_bitmap_block()
        in_use_blocks = set()
        for ino in live_inodes:
            t, _size, n_used, blks, _mode, _owner, _mtime, _ctime = inode_unpack(self._read_inode_raw(ino))
            for rel in blks[:n_used]:
                in_use_blocks.add(rel)

        allocated_blocks = {i for i in range(self._sb["data_block_count"]) if bitmap_get(bytes(bbm), i)}
        orphan_blocks = sorted(list(allocated_blocks - in_use_blocks))

        return {
            "live_inodes": sorted(list(live_inodes)),
            "orphan_inodes": orphan_inodes,
            "orphan_blocks": orphan_blocks,
        }

    def garbage_collect(self) -> dict[str, int]:
        stats = self.scan_garbage()
        ibm = bytearray(self._inode_bitmap_block())
        bbm = bytearray(self._block_bitmap_block())

        for ino in stats["orphan_inodes"]:
            bitmap_set(ibm, ino, False)

        for rel in stats["orphan_blocks"]:
            bitmap_set(bbm, rel, False)

        self._write_inode_bitmap(bytes(ibm))
        self._write_block_bitmap(bytes(bbm))

        return {
            "freed_inodes": len(stats["orphan_inodes"]),
            "freed_blocks": len(stats["orphan_blocks"]),
        }

    def truncate_journal(self) -> None:
        for i in range(self._sb["journal_block_count"]):
            self._disk.write_block(self._sb["journal_start"] + i, b"\x00" * BLOCK_SIZE)
            self.metrics["block_writes"] += 1
        self._sb["journal_seq"] = 0
        self._write_superblock()
        self._disk.sync()

    def checkpoint(self) -> None:
        self.recover_from_journal()
        self.truncate_journal()
        return

