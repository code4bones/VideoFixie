from __future__ import annotations

import sys
from argparse import ArgumentParser
from pathlib import Path

from PySide6.QtWidgets import QApplication

from videofixie.ui.main_window import MainWindow


def main() -> int:
    parser = ArgumentParser(prog="videofixie-gui")
    parser.add_argument("--source", help="Open a source video on startup.")
    args = parser.parse_args()

    app = QApplication(sys.argv[:1])
    window = MainWindow()
    window.show()
    if args.source:
        window.load_source(Path(args.source).expanduser().resolve())
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
