"""Shared utilities: rate-limit retry, failure log, JSON report writer.

Also provides drop-in replacements for several spotipy 2.26 endpoints that
target the wrong URL (`me/library` instead of the correct Web API paths).
When upstream spotipy is fixed, the `*_tracks`, `*_albums`, `follow_*`,
`unfollow_*` and `follow_playlist` helpers can be removed.
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

PROJECT_DIR = Path(__file__).parent
LOGS_DIR = PROJECT_DIR / "logs"


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


# ---------- Workarounds for spotipy 2.26 ----------
# Several library/follow methods in spotipy 2.26 send requests to a
# non-existent `me/library` endpoint. The wrappers below issue the same calls
# against the correct Web API URLs using sp._put / sp._delete.


def _track_id(uri_or_id: str) -> str:
    """Return a bare track id from either a full URI or a raw id."""
    return uri_or_id.split(":")[-1]


def saved_tracks_add(sp, uris: list[str]):
    ids = [_track_id(u) for u in uris]
    return sp._put("me/tracks?ids=" + ",".join(ids))


def saved_tracks_delete(sp, uris: list[str]):
    ids = [_track_id(u) for u in uris]
    return sp._delete("me/tracks?ids=" + ",".join(ids))


def saved_albums_add(sp, album_ids: list[str]):
    return sp._put("me/albums?ids=" + ",".join(album_ids))


def saved_albums_delete(sp, album_ids: list[str]):
    return sp._delete("me/albums?ids=" + ",".join(album_ids))


def follow_artists(sp, artist_ids: list[str]):
    return sp._put("me/following?type=artist&ids=" + ",".join(artist_ids))


def unfollow_artists(sp, artist_ids: list[str]):
    return sp._delete("me/following?type=artist&ids=" + ",".join(artist_ids))


def follow_playlist(sp, playlist_id: str):
    pid = playlist_id.split(":")[-1]
    return sp._put(f"playlists/{pid}/followers")
