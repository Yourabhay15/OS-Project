import unittest

from core import FileSystemCore
from engine import RecoveryOptimizationEngine


class TestEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.fs = FileSystemCore(total_blocks=40)
        self.fs.create_directory('/docs')
        self.fs.create_file('/docs', 'x.txt', 4)
        self.fs.create_file('/docs', 'y.txt', 3)
        self.engine = RecoveryOptimizationEngine(self.fs)
        self.engine.snapshot_file('/docs', 'x.txt')
        self.engine.snapshot_file('/docs', 'y.txt')

    def test_crash_and_recover_corrupted(self) -> None:
        self.engine.simulate_crash(1.0)
        recovered = self.engine.recover_corrupted_files()
        self.assertGreaterEqual(recovered, 1)

    def test_defragment_reduces_fragmentation(self) -> None:
        before = self.engine.fragmentation_score()
        self.engine.defragment_disk()
        after = self.engine.fragmentation_score()
        self.assertLessEqual(after, before)


if __name__ == '__main__':
    unittest.main()
