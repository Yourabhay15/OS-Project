from __future__ import annotations

from typing import Dict, List, Optional
import random

from core import FileMeta, FileSystemCore


class RecoveryOptimizationEngine:
    def __init__(self, fs: FileSystemCore) -> None:
        self.fs = fs
        self.backup_log: List[tuple[str, FileMeta]] = []

    def snapshot_file(self, dir_path: str, file_name: str) -> None:
        node = self.fs._resolve_dir(dir_path)
        meta = node.files.get(file_name)
        if not meta:
            raise ValueError("File not found for snapshot")
        self.backup_log.append((dir_path, FileMeta(**meta.__dict__)))

    def simulate_crash(self, corruption_rate: float = 0.15) -> Dict[str, int]:
        if not 0 <= corruption_rate <= 1:
            raise ValueError("corruption_rate must be in [0,1]")
        all_files = []

        def collect(node):
            for meta in node.files.values():
                if not meta.deleted:
                    all_files.append(meta)
            for sub in node.subdirs.values():
                collect(sub)

        collect(self.fs.root)
        if not all_files:
            return {"files_corrupted": 0, "blocks_zeroed": 0}

        n_corrupt = max(1, int(len(all_files) * corruption_rate))
        chosen = random.sample(all_files, min(n_corrupt, len(all_files)))
        blocks_zeroed = 0
        for meta in chosen:
            meta.corrupted = True
            if meta.block_indices:
                broken_block = random.choice(meta.block_indices)
                if self.fs.disk[broken_block] is not None:
                    self.fs.disk[broken_block] = None
                    blocks_zeroed += 1
        return {"files_corrupted": len(chosen), "blocks_zeroed": blocks_zeroed}

    def recover_deleted_files(self) -> int:
        recovered = 0
        while self.fs.deleted_log:
            dir_path, meta = self.fs.deleted_log.pop()
            node = self.fs._resolve_dir(dir_path)
            if meta.name in node.files and not node.files[meta.name].deleted:
                continue
            free = self.fs.free_blocks()
            if len(free) < meta.size_blocks:
                continue
            restored = free[: meta.size_blocks]
            for idx in restored:
                self.fs.disk[idx] = meta.name
            meta.deleted = False
            meta.corrupted = False
            meta.block_indices = restored
            node.files[meta.name] = meta
            recovered += 1
        return recovered

    def recover_corrupted_files(self) -> int:
        recovered = 0

        def walk(node):
            nonlocal recovered
            for name, meta in node.files.items():
                if meta.deleted or not meta.corrupted:
                    continue
                backup: Optional[FileMeta] = None
                for dir_path, snap in reversed(self.backup_log):
                    if dir_path == node.path() and snap.name == name:
                        backup = snap
                        break
                if backup:
                    for idx in meta.block_indices:
                        self.fs.disk[idx] = None
                    free = self.fs.free_blocks()
                    if len(free) < backup.size_blocks:
                        continue
                    restored = free[: backup.size_blocks]
                    for idx in restored:
                        self.fs.disk[idx] = backup.name
                    meta.block_indices = restored
                    meta.corrupted = False
                    recovered += 1
            for sub in node.subdirs.values():
                walk(sub)

        walk(self.fs.root)
        return recovered

    def defragment_disk(self) -> Dict[str, int]:
        files: List[FileMeta] = []

        def walk(node):
            for meta in node.files.values():
                if not meta.deleted:
                    files.append(meta)
            for sub in node.subdirs.values():
                walk(sub)

        walk(self.fs.root)
        files.sort(key=lambda m: m.name)

        new_disk = [None] * self.fs.total_blocks
        cursor = 0
        moved_blocks = 0
        for meta in files:
            new_blocks = list(range(cursor, cursor + meta.size_blocks))
            moved_blocks += sum(
                1 for old, new in zip(sorted(meta.block_indices), new_blocks) if old != new
            )
            meta.block_indices = new_blocks
            for idx in new_blocks:
                new_disk[idx] = meta.name
            cursor += meta.size_blocks

        self.fs.disk = new_disk
        return {
            "files_reordered": len(files),
            "moved_blocks": moved_blocks,
            "free_blocks": self.fs.total_blocks - cursor,
        }

    def disk_usage(self) -> Dict[str, float]:
        used = self.fs.used_blocks_count()
        total = self.fs.total_blocks
        return {
            "used_blocks": float(used),
            "free_blocks": float(total - used),
            "used_percent": (used / total) * 100.0 if total else 0.0,
        }

    def fragmentation_score(self) -> float:
        occupied_positions = [i for i, v in enumerate(self.fs.disk) if v is not None]
        if len(occupied_positions) < 2:
            return 0.0
        gaps = 0
        for a, b in zip(occupied_positions, occupied_positions[1:]):
            if b - a > 1:
                gaps += 1
        return (gaps / (len(occupied_positions) - 1)) * 100.0
