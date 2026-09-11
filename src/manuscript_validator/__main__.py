"""`python -m manuscript_validator` runs the CLI."""

import sys

from manuscript_validator.cli import main

if __name__ == "__main__":
    sys.exit(main())
