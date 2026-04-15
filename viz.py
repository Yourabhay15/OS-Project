"""ASCII and color-role visualization of on-disk layout."""

from __future__ import annotations

from fs_core.bitmap import bitmap_get
from fs_core.block_device import BlockDevice
from fs_core.filesystem import FileSystem

# Role keys for GUI / theming (WCAG-friendly dark palette)
ROLE_COLORS: dict[str, str] = {
    "superblock": "#2c5282",
    "inode_bitmap": "#805ad5",
    "block_bitmap": "#c05621",
    "inode_table": "#2f855a",
    "data_free": "#4a5568",
    "data_used": "#63b3ed",
    "journal": "#b83280",
    "other": "#1a202c",
}


def block_map_legend() -> str:
    return (
        "Block Map Legend: S=superblock I=inode bitmap B=block bitmap "
        "T=inode table d=free data D=used data J=journal .=other/unknown"
    )


def block_roles(fs: FileSystem, disk: BlockDevice) -> list[str]:
    """
    One role string per block index for coloring.
    Data blocks split into data_free / data_used using the block bitmap.
    """
    sb = fs._sb  # noqa: SLF001 — visualization
    n = disk.num_blocks
    roles = ["other"] * n
    roles[0] = "superblock"
    for i in range(sb["inode_bitmap_blocks"]):
        roles[sb["inode_bitmap_start"] + i] = "inode_bitmap"
    for i in range(sb["block_bitmap_blocks"]):
        roles[sb["block_bitmap_start"] + i] = "block_bitmap"
    for i in range(sb["inode_table_blocks"]):
        roles[sb["inode_table_start"] + i] = "inode_table"
    bbm = fs._block_bitmap_block()
    for i in range(sb["data_block_count"]):
        idx = sb["data_start"] + i
        roles[idx] = "data_used" if bitmap_get(bytes(bbm), i) else "data_free"
    for i in range(sb["journal_block_count"]):
        roles[sb["journal_start"] + i] = "journal"
    return roles


def block_map(fs: FileSystem, disk: BlockDevice, width: int = 64) -> str:
    sb = fs._sb  # noqa: SLF001 — visualization
    n = disk.num_blocks
    roles = block_roles(fs, disk)
    ch_map = {
        "superblock": "S",
        "inode_bitmap": "I",
        "block_bitmap": "B",
        "inode_table": "T",
        "data_free": "d",
        "data_used": "D",
        "journal": "J",
        "other": ".",
    }
    labels = [ch_map.get(r, ".") for r in roles]
    lines = [block_map_legend(), f"Blocks 0..{n-1} ({width}/row): d=free data D=used | Run 'python main.py map' after ops to see changes!"]
    row: list[str] = []
    for ch in labels:
        row.append(ch)
        if len(row) >= width:
            lines.append("".join(row))
            row = []
    if row:
        lines.append("".join(row))
    return "\n".join(lines)
