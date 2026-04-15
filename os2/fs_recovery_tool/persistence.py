from __future__ import annotations

import json
import pickle
from typing import Any, Dict, List, Tuple

from core import DirectoryNode, FileMeta, FileSystemCore
from engine import RecoveryOptimizationEngine


def _meta_to_dict(meta: FileMeta) -> Dict[str, Any]:
    return {
        "name": meta.name,
        "size_blocks": meta.size_blocks,
        "block_indices": list(meta.block_indices),
        "allocation": meta.allocation,
        "deleted": meta.deleted,
        "corrupted": meta.corrupted,
    }


def _meta_from_dict(data: Dict[str, Any]) -> FileMeta:
    return FileMeta(
        name=data["name"],
        size_blocks=int(data["size_blocks"]),
        block_indices=list(data.get("block_indices", [])),
        allocation=data.get("allocation", "indexed"),
        deleted=bool(data.get("deleted", False)),
        corrupted=bool(data.get("corrupted", False)),
    )


def _dir_to_dict(node: DirectoryNode) -> Dict[str, Any]:
    return {
        "name": node.name,
        "files": {name: _meta_to_dict(meta) for name, meta in node.files.items()},
        "subdirs": {name: _dir_to_dict(sub) for name, sub in node.subdirs.items()},
    }


def _dir_from_dict(data: Dict[str, Any], parent: DirectoryNode | None = None) -> DirectoryNode:
    node = DirectoryNode(name=data["name"], parent=parent)
    node.files = {name: _meta_from_dict(meta) for name, meta in data.get("files", {}).items()}
    node.subdirs = {
        name: _dir_from_dict(sub_data, parent=node)
        for name, sub_data in data.get("subdirs", {}).items()
    }
    return node


def export_state(fs: FileSystemCore, engine: RecoveryOptimizationEngine) -> Dict[str, Any]:
    return {
        "total_blocks": fs.total_blocks,
        "disk": fs.disk,
        "root": _dir_to_dict(fs.root),
        "deleted_log": [[path, _meta_to_dict(meta)] for path, meta in fs.deleted_log],
        "backup_log": [[path, _meta_to_dict(meta)] for path, meta in engine.backup_log],
    }


def import_state(data: Dict[str, Any]) -> Tuple[FileSystemCore, RecoveryOptimizationEngine]:
    fs = FileSystemCore(total_blocks=int(data["total_blocks"]))
    fs.disk = list(data.get("disk", [None] * fs.total_blocks))
    fs.root = _dir_from_dict(data["root"], parent=None)
    fs.deleted_log = [
        (path, _meta_from_dict(meta)) for path, meta in data.get("deleted_log", [])
    ]
    engine = RecoveryOptimizationEngine(fs)
    engine.backup_log = [
        (path, _meta_from_dict(meta)) for path, meta in data.get("backup_log", [])
    ]
    return fs, engine


def save_json(path: str, fs: FileSystemCore, engine: RecoveryOptimizationEngine) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(export_state(fs, engine), f, indent=2)


def load_json(path: str) -> Tuple[FileSystemCore, RecoveryOptimizationEngine]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return import_state(data)


def save_pickle(path: str, fs: FileSystemCore, engine: RecoveryOptimizationEngine) -> None:
    with open(path, "wb") as f:
        pickle.dump(export_state(fs, engine), f)


def load_pickle(path: str) -> Tuple[FileSystemCore, RecoveryOptimizationEngine]:
    with open(path, "rb") as f:
        data = pickle.load(f)
    return import_state(data)
