import os
import tempfile
import unittest

from core import FileSystemCore
from engine import RecoveryOptimizationEngine
from persistence import load_json, load_pickle, save_json, save_pickle


class TestPersistence(unittest.TestCase):
    def setUp(self) -> None:
        self.fs = FileSystemCore(total_blocks=30)
        self.fs.create_directory('/docs')
        self.fs.create_file('/docs', 'persist.txt', 5)
        self.engine = RecoveryOptimizationEngine(self.fs)
        self.engine.snapshot_file('/docs', 'persist.txt')

    def test_json_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, 'state.json')
            save_json(path, self.fs, self.engine)
            fs2, _engine2 = load_json(path)
            self.assertEqual(fs2.total_blocks, self.fs.total_blocks)
            self.assertEqual(fs2.used_blocks_count(), self.fs.used_blocks_count())

    def test_pickle_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, 'state.pkl')
            save_pickle(path, self.fs, self.engine)
            fs2, _engine2 = load_pickle(path)
            self.assertEqual(fs2.total_blocks, self.fs.total_blocks)
            self.assertEqual(fs2.used_blocks_count(), self.fs.used_blocks_count())


if __name__ == '__main__':
    unittest.main()
