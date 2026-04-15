"""Layout constants for the simulated on-disk format."""

import struct

BLOCK_SIZE = 512
NUM_INODES = 64
INODE_SIZE = 64
MAX_DIRECT_BLOCKS = 8
DIR_ENTRY_SIZE = 64
MAX_NAME_LEN = 59

SUPERBLOCK_MAGIC = 0x46534F53  # "FSOS" little-endian-ish
FORMAT_VERSION = 1

# Superblock: magic, version, total_blocks, block_size, inode_bitmap_start, inode_bitmap_blocks,
# block_bitmap_start, block_bitmap_blocks, inode_table_start, inode_table_blocks,
# data_region_start, data_block_count, journal_start, journal_block_count, root_inode, journal_seq
SUPERBLOCK_STRUCT = struct.Struct("<IIIIIIIIIIIIIIII")

INODE_STRUCT = struct.Struct("<B3xI B7x 8I")  # type, size, used_count, 8 block ids — pad to 64

INODE_FILE = 1
INODE_DIR = 2
