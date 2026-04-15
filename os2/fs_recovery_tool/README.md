# File System Recovery and Optimization Tool

This project simulates a small file system and demonstrates:

- File/directory creation and deletion
- Block-based allocation (`indexed` and `linked`)
- Crash simulation with corruption
- Recovery of deleted and corrupted files
- Defragmentation and free-space optimization
- GUI visualization of directory tree, block map, disk usage, and fragmentation

## Modules

1. `core.py` - File system simulation core
2. `engine.py` - Recovery and optimization engine
3. `ui.py` - Tkinter UI + matplotlib visualization

## Run

```bash
pip install matplotlib
python main.py
```

### CLI mode

```bash
python main.py --mode cli
```

### Useful CLI commands

- `mkd /docs/reports`
- `mkf /docs hello.txt 4 indexed`
- `del /docs hello.txt`
- `crash 0.3`
- `recover`
- `defrag`
- `save_json state.json`
- `load_json state.json`
- `save_pickle state.pkl`
- `load_pickle state.pkl`

## Persistence

- GUI now supports `Save/Load JSON` and `Save/Load Pickle` buttons.
- CLI supports `save_json`, `load_json`, `save_pickle`, and `load_pickle`.

## Tests

Run all tests:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

## Notes

- This works on a simulated disk in memory (safe for your OS files).
- The delete operation is soft-delete so recovery can restore files.
- You can extend it with JSON/pickle persistence and ML failure prediction.
