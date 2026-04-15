from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import random


@dataclass
class FileMeta:
    name: str
    size_blocks: int
    block_indices: List[int] = field(default_factory=list)
    allocation: str = "indexed"  # indexed | linked
    deleted: bool = False
    corrupted: bool = False


@dataclass
class DirectoryNode:
    name: str
    parent: Optional["DirectoryNode"] = None
    files: Dict[str, FileMeta] = field(default_factory=dict)
    subdirs: Dict[str, "DirectoryNode"] = field(default_factory=dict)

    def path(self) -> str:
        if self.parent is None:
            return "/"
        parts = []
        node: Optional["DirectoryNode"] = self
        while node and node.parent is not None:
            parts.append(node.name)
            node = node.parent
        return "/" + "/".join(reversed(parts))


class FileSystemCore:
    def __init__(self, total_blocks: int = 128) -> None:
        self.total_blocks = total_blocks
        self.disk: List[Optional[str]] = [None] * total_blocks
        self.root = DirectoryNode(name="/", parent=None)
        self.deleted_log: List[tuple[str, FileMeta]] = []

    def free_blocks(self) -> List[int]:
        return [i for i, val in enumerate(self.disk) if val is None]

    def used_blocks_count(self) -> int:
        return self.total_blocks - len(self.free_blocks())

    def create_directory(self, path: str) -> None:
        parts = [p for p in path.split("/") if p]
        node = self.root
        for part in parts:
            if part not in node.subdirs:
                node.subdirs[part] = DirectoryNode(name=part, parent=node)
            node = node.subdirs[part]

    def _resolve_dir(self, path: str) -> DirectoryNode:
        if path == "/":
            return self.root
        parts = [p for p in path.split("/") if p]
        node = self.root
        for part in parts:
            if part not in node.subdirs:
                raise ValueError(f"Directory not found: {path}")
            node = node.subdirs[part]
        return node

    def create_file(
        self,
        dir_path: str,
        file_name: str,
        size_blocks: int,
        allocation: str = "indexed",
    ) -> FileMeta:
        if size_blocks <= 0:
            raise ValueError("size_blocks must be > 0")
        if allocation not in {"indexed", "linked"}:
            raise ValueError("allocation must be indexed or linked")
        dir_node = self._resolve_dir(dir_path)
        if file_name in dir_node.files and not dir_node.files[file_name].deleted:
            raise ValueError(f"File already exists: {file_name}")
        free = self.free_blocks()
        if len(free) < size_blocks:
            raise ValueError("Not enough free blocks")
        chosen = random.sample(free, size_blocks)
        if allocation == "linked":
            chosen.sort()
        for idx in chosen:
            self.disk[idx] = file_name
        meta = FileMeta(
            name=file_name,
            size_blocks=size_blocks,
            block_indices=chosen,
            allocation=allocation,
        )
        dir_node.files[file_name] = meta
        return meta

    def delete_file(self, dir_path: str, file_name: str, hard: bool = False) -> None:
        dir_node = self._resolve_dir(dir_path)
        if file_name not in dir_node.files:
            raise ValueError(f"File not found: {file_name}")
        meta = dir_node.files[file_name]
        if meta.deleted:
            raise ValueError(f"File already deleted: {file_name}")
        if hard:
            for idx in meta.block_indices:
                self.disk[idx] = None
            meta.deleted = True
            self.deleted_log.append((dir_path, meta))
            return
        meta.deleted = True
        self.deleted_log.append((dir_path, FileMeta(**meta.__dict__)))

    def list_directory(self, dir_path: str) -> dict:
        node = self._resolve_dir(dir_path)
        return {
            "path": node.path(),
            "subdirs": sorted(node.subdirs.keys()),
            "files": sorted(
                [
                    f"{name} ({'deleted' if meta.deleted else 'active'})"
                    for name, meta in node.files.items()
                ]
            ),
        }

    def tree(self) -> str:
        lines: List[str] = []

        def walk(node: DirectoryNode, indent: str) -> None:
            lines.append(f"{indent}{node.name if node.parent else '/'}")
            for sub in sorted(node.subdirs.values(), key=lambda d: d.name):
                walk(sub, indent + "  ")
            for file_name in sorted(node.files.keys()):
                meta = node.files[file_name]
                status = "deleted" if meta.deleted else "ok"
                flag = " CORRUPTED" if meta.corrupted else ""
                lines.append(f"{indent}  - {file_name} [{status}]{flag}")

        walk(self.root, "")
        return "\n".join(lines)
