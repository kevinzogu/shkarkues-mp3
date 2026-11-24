"""Pika e hyrjes: `python main.py` ose ShkarkuesMP3.exe."""

import os
import sys

# Në .exe pa konsolë (PyInstaller --windowed) stdout/stderr janë None
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from shkarkues.ui import run  # noqa: E402

if __name__ == "__main__":
    run()
