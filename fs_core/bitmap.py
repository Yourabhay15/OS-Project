"""Bit operations for inode and block bitmaps stored in disk blocks."""


def _byte_bit(bit_index: int) -> tuple[int, int]:
    return bit_index // 8, 1 << (bit_index % 8)


def bitmap_get(data: bytes, bit_index: int) -> bool:
    bi, mask = _byte_bit(bit_index)
    return bool(data[bi] & mask)


def bitmap_set(data: bytearray, bit_index: int, value: bool) -> None:
    bi, mask = _byte_bit(bit_index)
    if value:
        data[bi] |= mask
    else:
        data[bi] &= ~mask & 0xFF
