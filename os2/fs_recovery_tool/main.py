import argparse

from cli import run_cli
from ui import FileSystemApp


def main() -> None:
    parser = argparse.ArgumentParser(
        description="File System Recovery and Optimization Tool"
    )
    parser.add_argument(
        "--mode",
        choices=["gui", "cli"],
        default="gui",
        help="Run in GUI mode (default) or CLI mode",
    )
    args = parser.parse_args()

    if args.mode == "cli":
        run_cli()
        return

    app = FileSystemApp()
    app.mainloop()


if __name__ == "__main__":
    main()
