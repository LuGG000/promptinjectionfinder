"""Entry point for the standalone (PyInstaller) build."""
import sys

from pif.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
