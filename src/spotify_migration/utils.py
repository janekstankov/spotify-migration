"""Shared utilities: rate-limit retry, failure log, JSON report writer.

Also provides playlist follow/unfollow helpers for Spotify's post-February-2026
Web API: `PUT/DELETE /me/library` replace the old per-type endpoints, and
`playlist_add_items`/`playlist_items`/playlist creation are handled by spotipy
>= 2.26 directly.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from spotipy.exceptions import SpotifyException

# Reports are written to the directory the user launches the tool from,
# so relative paths in the terminal output are easy to click.
LOGS_DIR = Path.cwd() / "logs"


def safe_call(fn: Callable, *args: Any, max_retries: int = 3, **kwargs: Any):
    """Invoke a spotipy call with retry on 429 (honouring Retry-After) and 5xx
    with exponential back-off. Non-429 4xx errors (e.g. 404, 403) are raised
    immediately. Returns the call result, or re-raises the last exception on
    exhaustion.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except SpotifyException as exc:
            last_exc = exc
            status = exc.http_status or 0
            if status == 429:
                retry_after = 1
                headers = getattr(exc, "headers", None) or {}
                try:
                    retry_after = int(headers.get("Retry-After", 1))
                except (TypeError, ValueError):
                    retry_after = 1
                # Daily-quota 429s (reason QUOTA_EXCEEDED) carry Retry-After
                # values of hours — the time until the quota reset. Retrying
                # is pointless and sleeping would hang the CLI, so fail fast.
                if retry_after > 3600:
                    raise
                time.sleep(retry_after + 1)
                continue
            if 500 <= status < 600:
                time.sleep(2**attempt)
                continue
            raise
        except Exception as exc:
            last_exc = exc
            time.sleep(2**attempt)
            continue
    if last_exc:
        raise last_exc


@dataclass
class FailureLog:
    entries: list[dict] = field(default_factory=list)

    def add(self, kind: str, **payload: Any) -> None:
        self.entries.append({"type": kind, **payload})

    def __len__(self) -> int:
        return len(self.entries)


@dataclass
class MigrationReport:
    started_at: str
    source_user_id: str
    source_user_name: str
    destination_user_id: str
    destination_user_name: str
    mode: str
    source_counts: dict
    destination_counts: dict
    cleanup: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)
    failures: list[dict] = field(default_factory=list)
    finished_at: str = ""

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=2, ensure_ascii=False)


def save_report(report: MigrationReport) -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOGS_DIR / f"migration_{ts}.json"
    path.write_text(report.to_json(), encoding="utf-8")
    return path


def chunks(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


# ---------- Playlist follow/unfollow helpers ----------
# Spotify's February 2026 Web API changes replaced the playlist follow
# endpoints with `PUT/DELETE /me/library?uris=spotify:playlist:{id}`.
# Unfollowing via DELETE /me/library is confirmed working. Following via
# PUT /me/library currently fails server-side with HTTP 500 for playlist
# URIs (verified 2026-08-25), so follow_playlist tries the new endpoint
# first and falls back to the legacy one.
# `me/library` accepts at most 40 URIs per request.

LIBRARY_BATCH_MAX = 40


def follow_playlist(sp, playlist_id: str):
    """Follow a playlist, trying Spotify's new `/me/library` endpoint first."""
    pid = playlist_id.split(":")[-1]
    try:
        return sp.current_user_follow_playlist(pid)
    except SpotifyException:
        return sp._put(f"playlists/{pid}/followers")


def unfollow_playlist(sp, playlist_id: str):
    """Unfollow a playlist (Spotify treats unfollowing an owned playlist as
    deletion) via DELETE /me/library."""
    pid = playlist_id.split(":")[-1]
    return sp._delete("me/library", uris=f"spotify:playlist:{pid}")
