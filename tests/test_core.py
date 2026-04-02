import unittest

from core import FileSystemCore


class TestFileSystemCore(unittest.TestCase):
    def setUp(self) -> None:
        self.fs = FileSystemCore(total_blocks=20)
        self.fs.create_directory('/docs')

    def test_create_file_allocates_blocks(self) -> None:
        meta = self.fs.create_file('/docs', 'a.txt', 3, 'indexed')
        self.assertEqual(meta.size_blocks, 3)
        self.assertEqual(len(meta.block_indices), 3)
        self.assertEqual(self.fs.used_blocks_count(), 3)

    def test_delete_marks_file_and_logs(self) -> None:
        self.fs.create_file('/docs', 'b.txt', 2)
        self.fs.delete_file('/docs', 'b.txt')
        listing = self.fs.list_directory('/docs')
        self.assertIn('b.txt (deleted)', listing['files'])
        self.assertEqual(len(self.fs.deleted_log), 1)


if __name__ == '__main__':
    unittest.main()
