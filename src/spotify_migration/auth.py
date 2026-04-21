"""Dual OAuth for two Spotify accounts (source + destination).

Each account gets its own token cache file so both sessions can coexist without
clobbering each other. Tokens are refreshed automatically by spotipy on every
subsequent run.
"""

from __future__ import annotations

import os
from pathlib import Path

import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()

SCOPES = " ".join(
    [
        "playlist-read-private",
        "playlist-read-collaborative",
        "playlist-modify-private",
        "playlist-modify-public",
        "user-library-read",
        "user-library-modify",
        "user-follow-read",
        "user-follow-modify",
    ]
)

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")

# Cache token files live alongside the user's .env file, which is typically the
# project root from which the tool is invoked. Using cwd (instead of the module
# path) keeps the caches in the same place regardless of whether the package is
# executed via `python -m spotify_migration`, the `spotify-migration` console
# script, or an editable install.
PROJECT_DIR = Path.cwd()
CACHE_SOURCE = PROJECT_DIR / ".cache-source"
CACHE_DESTINATION = PROJECT_DIR / ".cache-destination"


class MissingCredentialsError(RuntimeError):
    pass


def _assert_credentials() -> None:
    if not CLIENT_ID or not CLIENT_SECRET:
        raise MissingCredentialsError(
            "SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET are missing from .env. "
            "Copy .env.example to .env and fill in your Developer Dashboard credentials."
        )


def _build_client(cache_path: Path, open_browser: bool = False) -> spotipy.Spotify:
    # open_browser=False forces the manual-paste flow: spotipy prints the
    # authorize URL and waits for the user to paste the redirected URL back.
    # This works around browsers (e.g. Safari) that refuse to open the
    # http://127.0.0.1:8888/callback redirect because of HTTPS-only policies.
    auth_manager = SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPES,
        cache_path=str(cache_path),
        show_dialog=True,
        open_browser=open_browser,
    )
    return spotipy.Spotify(auth_manager=auth_manager, requests_timeout=30)


def get_source_client(open_browser: bool = False) -> spotipy.Spotify:
    _assert_credentials()
    return _build_client(CACHE_SOURCE, open_browser=open_browser)


def get_destination_client(open_browser: bool = False) -> spotipy.Spotify:
    _assert_credentials()
    return _build_client(CACHE_DESTINATION, open_browser=open_browser)


def describe_user(client: spotipy.Spotify) -> dict:
    me = client.me()
    return {
        "id": me.get("id"),
        "display_name": me.get("display_name") or me.get("id"),
        "email": me.get("email"),
        "country": me.get("country"),
        "product": me.get("product"),
    }
