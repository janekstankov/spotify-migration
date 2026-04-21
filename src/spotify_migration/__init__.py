"""Spotify Account Migrator — migrate the entire contents of one Spotify
account to another while preserving added_at ordering.
"""

from .migrate import main

__all__ = ["main"]
__version__ = "1.0.1"
