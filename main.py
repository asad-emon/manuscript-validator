"""PyInstaller entry point. Kept trivial on purpose -- see packaging/build.spec."""

import sys

from manuscript_validator.app import main

if __name__ == "__main__":
    sys.exit(main())
