"""Allow running the package with `python -m spotify_migration`."""

import sys

from .migrate import main

if __name__ == "__main__":
    sys.exit(main())
