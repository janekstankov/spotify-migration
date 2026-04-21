"""Cleanup modes (WIPE / ARCHIVE / SKIP) and idempotent migration of content
from the source snapshot to the destination account.

Every operation first checks the destination state and only writes what is
missing (owned playlists are matched by name, everything else by URI/ID), so
a crashed run can be safely resumed by re-invoking the tool.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import spotipy

from .source import AccountSnapshot, OwnedPlaylist
from .utils import (
    FailureLog,
    chunks,
    follow_artists,
    follow_playlist,
    safe_call,
    saved_albums_add,
    saved_albums_delete,
    saved_tracks_add,
    saved_tracks_delete,
    unfollow_artists,
)

ARCHIVE_PREFIX = "[ARCHIVED] "
ARCHIVE_LIKED_NAME = "[ARCHIVED] Liked Songs"

# Any prefix listed here identifies an already-archived playlist. The first
# entry is the current default; the rest are kept for backwards compatibility
# with snapshots produced by older versions of the tool.
ARCHIVE_PREFIXES: tuple[str, ...] = (ARCHIVE_PREFIX, "[ARCHIWUM] ")
ARCHIVE_LIKED_PREFIXES: tuple[str, ...] = (
    ARCHIVE_LIKED_NAME,
    "[ARCHIWUM] Polubione",
)

SPOTIFY_NAME_MAX = 100
LIKED_DELAY_S = 0.2
ALBUM_DELAY_S = 0.2

Progress = Callable[[str, int, int], None]


def _noop_progress(stage: str, done: int, total: int) -> None:
    pass


def _archive_name(original: str) -> str:
    return (ARCHIVE_PREFIX + original)[:SPOTIFY_NAME_MAX]


def _is_archived(name: str) -> bool:
    return any(name.startswith(p) for p in ARCHIVE_PREFIXES)


def _find_existing_archive_liked(snapshot: AccountSnapshot) -> OwnedPlaylist | None:
    for pl in snapshot.owned_playlists:
        if any(pl.name.startswith(p) for p in ARCHIVE_LIKED_PREFIXES):
            return pl
    return None


# ---------- Cleanup modes ----------


def cleanup_wipe(
    sp: spotipy.Spotify,
    snapshot: AccountSnapshot,
    *,
    failures: FailureLog,
    progress: Progress = _noop_progress,
) -> dict:
    """Remove every playlist, like, followed artist and saved album from the
    destination account. Idempotent – running WIPE on an empty account is a
    no-op.
    """
    report = {
        "playlists_removed": 0,
        "liked_removed": 0,
        "artists_unfollowed": 0,
        "albums_removed": 0,
    }

    all_playlists = snapshot.owned_playlists + snapshot.followed_playlists
    progress("wipe_playlists", 0, len(all_playlists))
    for idx, pl in enumerate(all_playlists, start=1):
        try:
            safe_call(sp.current_user_unfollow_playlist, pl.id)
            report["playlists_removed"] += 1
        except Exception as exc:  # noqa: BLE001
            failures.add("wipe_playlist", id=pl.id, name=pl.name, reason=str(exc))
        progress("wipe_playlists", idx, len(all_playlists))

    liked_uris = [t.uri for t in snapshot.liked_tracks]
    total = len(liked_uris)
    done = 0
    progress("wipe_liked", done, total)
    for batch in chunks(liked_uris, 50):
        try:
            safe_call(saved_tracks_delete, sp, batch)
            report["liked_removed"] += len(batch)
        except Exception as exc:  # noqa: BLE001
            failures.add("wipe_liked_batch", count=len(batch), reason=str(exc))
        done += len(batch)
        progress("wipe_liked", done, total)

    artist_ids = [a.id for a in snapshot.followed_artists]
    total = len(artist_ids)
    done = 0
    progress("wipe_artists", done, total)
    for batch in chunks(artist_ids, 50):
        try:
            safe_call(unfollow_artists, sp, batch)
            report["artists_unfollowed"] += len(batch)
        except Exception as exc:  # noqa: BLE001
            failures.add("wipe_artists_batch", count=len(batch), reason=str(exc))
        done += len(batch)
        progress("wipe_artists", done, total)

    album_ids = [a.id for a in snapshot.saved_albums]
    total = len(album_ids)
    done = 0
    progress("wipe_albums", done, total)
    for batch in chunks(album_ids, 50):
        try:
            safe_call(saved_albums_delete, sp, batch)
            report["albums_removed"] += len(batch)
        except Exception as exc:  # noqa: BLE001
            failures.add("wipe_albums_batch", count=len(batch), reason=str(exc))
        done += len(batch)
        progress("wipe_albums", done, total)

    return report


def cleanup_archive(
    sp: spotipy.Spotify,
    snapshot: AccountSnapshot,
    *,
    failures: FailureLog,
    progress: Progress = _noop_progress,
    protect_names: set[str] | None = None,
) -> dict:
    """Rename owned playlists with an [ARCHIVED] prefix, move liked tracks into
    a dedicated archive playlist, and clear the Liked Songs slot. Followed
    playlists, artists and saved albums are left untouched.

    Idempotent:
      * playlists already prefixed with [ARCHIVED] (or the legacy prefix) are
        skipped
      * playlists whose name matches an entry in `protect_names` (typically the
        names of the source's owned playlists) are skipped as well – the
        idempotent migration step will fill in any missing tracks instead
      * an existing [ARCHIVED] Liked Songs playlist is reused; only missing
        URIs are appended
      * clearing the Liked Songs slot ignores tracks that are already gone
    """
    protect_names = protect_names or set()
    report = {
        "playlists_renamed": 0,
        "playlists_skipped_already_archived": 0,
        "playlists_skipped_matches_source": 0,
        "liked_archived_added": 0,
        "liked_archived_already_there": 0,
        "liked_slot_cleared": 0,
        "archive_playlist_id": None,
        "archive_playlist_name": None,
        "archive_playlist_reused": False,
    }

    # 1. Rename owned playlists (skip already-archived and source-matching).
    to_rename: list[OwnedPlaylist] = []
    for pl in snapshot.owned_playlists:
        if _is_archived(pl.name):
            report["playlists_skipped_already_archived"] += 1
            continue
        if pl.name in protect_names:
            report["playlists_skipped_matches_source"] += 1
            continue
        to_rename.append(pl)

    total = len(to_rename)
    progress("archive_rename", 0, total)
    for idx, pl in enumerate(to_rename, start=1):
        progress("archive_rename", idx, total)
        new_name = _archive_name(pl.name)
        try:
            safe_call(sp.playlist_change_details, pl.id, name=new_name)
            report["playlists_renamed"] += 1
        except Exception as exc:  # noqa: BLE001
            failures.add("archive_rename", id=pl.id, name=pl.name, reason=str(exc))

    # 2. Archive liked tracks and clear the slot.
    if not snapshot.liked_tracks:
        return report

    existing_archive = _find_existing_archive_liked(snapshot)
    if existing_archive is not None:
        archive_id = existing_archive.id
        archive_name = existing_archive.name
        existing_uris = set(existing_archive.track_uris)
        report["archive_playlist_reused"] = True
    else:
        me_id = snapshot.me["id"]
        archive_name = ARCHIVE_LIKED_NAME
        try:
            new_pl = safe_call(
                sp.user_playlist_create,
                me_id,
                archive_name,
                public=False,
                description="Liked songs archived before migration.",
            )
            archive_id = new_pl["id"]
            existing_uris = set()
        except Exception as exc:  # noqa: BLE001
            failures.add("archive_playlist_create", name=archive_name, reason=str(exc))
            return report

    report["archive_playlist_id"] = archive_id
    report["archive_playlist_name"] = archive_name

    # Append only the URIs missing from the archive playlist, preserving ASC
    # order by added_at (the snapshot already returns liked tracks sorted).
    missing = [t.uri for t in snapshot.liked_tracks if t.uri not in existing_uris]
    report["liked_archived_already_there"] = len(snapshot.liked_tracks) - len(missing)
    total = len(missing)
    done = 0
    progress("archive_liked_add", done, total)
    for batch in chunks(missing, 100):
        try:
            safe_call(sp.playlist_add_items, archive_id, batch)
            report["liked_archived_added"] += len(batch)
        except Exception as exc:  # noqa: BLE001
            failures.add("archive_liked_add", count=len(batch), reason=str(exc))
        done += len(batch)
        progress("archive_liked_add", done, total)

    # Clear the Liked Songs slot – idempotent, already-missing tracks are OK.
    uris = [t.uri for t in snapshot.liked_tracks]
    total = len(uris)
    done = 0
    progress("archive_liked_clear", done, total)
    for batch in chunks(uris, 50):
        try:
            safe_call(saved_tracks_delete, sp, batch)
            report["liked_slot_cleared"] += len(batch)
        except Exception as exc:  # noqa: BLE001
            failures.add("archive_liked_clear", count=len(batch), reason=str(exc))
        done += len(batch)
        progress("archive_liked_clear", done, total)

    return report


def cleanup_skip(
    sp: spotipy.Spotify,
    snapshot: AccountSnapshot,
    *,
    failures: FailureLog,
    progress: Progress = _noop_progress,
) -> dict:
    return {"mode": "SKIP"}


CLEANUP_FNS = {
    "WIPE": cleanup_wipe,
    "ARCHIVE": cleanup_archive,
    "SKIP": cleanup_skip,
}


# ---------- Migration (source -> destination, idempotent) ----------


def migrate_content(
    sp: spotipy.Spotify,
    source: AccountSnapshot,
    destination: AccountSnapshot,
    *,
    destination_user_id: str,
    failures: FailureLog,
    progress: Progress = _noop_progress,
) -> dict:
    """Copy source content onto the destination, skipping what already exists.

    Matching rules:
      * Owned playlists: matched by name (destination playlists prefixed with
        [ARCHIVED] are excluded from matching). If a name match is found, only
        the missing URIs are appended; otherwise a new playlist is created.
      * Followed playlists, liked tracks, followed artists, saved albums: all
        matched against the destination snapshot by ID or URI.
    """
    stats = {
        "playlists_created": 0,
        "playlists_updated": 0,
        "playlists_skipped": 0,
        "playlist_tracks_added": 0,
        "playlists_followed": 0,
        "playlists_follow_skipped": 0,
        "tracks_liked_added": 0,
        "tracks_liked_skipped": 0,
        "artists_followed": 0,
        "artists_follow_skipped": 0,
        "albums_saved": 0,
        "albums_save_skipped": 0,
    }

    dest_owned_by_name: dict[str, OwnedPlaylist] = {
        pl.name: pl for pl in destination.owned_playlists if not _is_archived(pl.name)
    }
    dest_followed_ids = {pl.id for pl in destination.followed_playlists}
    dest_liked_uris = {t.uri for t in destination.liked_tracks}
    dest_artist_ids = {a.id for a in destination.followed_artists}
    dest_album_ids = {a.id for a in destination.saved_albums}

    # 1. Owned playlists.
    total = len(source.owned_playlists)
    progress("mig_playlists", 0, total)
    for idx, pl in enumerate(source.owned_playlists, start=1):
        existing = dest_owned_by_name.get(pl.name)
        if existing is not None:
            existing_set = set(existing.track_uris)
            missing = [u for u in pl.track_uris if u not in existing_set]
            if missing:
                for batch in chunks(missing, 100):
                    try:
                        safe_call(sp.playlist_add_items, existing.id, batch)
                        stats["playlist_tracks_added"] += len(batch)
                    except Exception as exc:  # noqa: BLE001
                        failures.add(
                            "mig_playlist_items_update",
                            playlist=pl.name,
                            count=len(batch),
                            reason=str(exc),
                        )
                stats["playlists_updated"] += 1
            else:
                stats["playlists_skipped"] += 1
        else:
            try:
                new_pl = safe_call(
                    sp.user_playlist_create,
                    destination_user_id,
                    pl.name,
                    public=pl.public,
                    description=pl.description or "",
                )
                new_id = new_pl["id"]
                stats["playlists_created"] += 1
            except Exception as exc:  # noqa: BLE001
                failures.add("mig_playlist_create", name=pl.name, reason=str(exc))
                progress("mig_playlists", idx, total)
                continue

            for batch in chunks(pl.track_uris, 100):
                try:
                    safe_call(sp.playlist_add_items, new_id, batch)
                    stats["playlist_tracks_added"] += len(batch)
                except Exception as exc:  # noqa: BLE001
                    failures.add(
                        "mig_playlist_items_create",
                        playlist=pl.name,
                        count=len(batch),
                        reason=str(exc),
                    )
        progress("mig_playlists", idx, total)

    # 2. Followed playlists.
    total = len(source.followed_playlists)
    progress("mig_followed", 0, total)
    for idx, pl in enumerate(source.followed_playlists, start=1):
        if pl.id in dest_followed_ids:
            stats["playlists_follow_skipped"] += 1
        else:
            try:
                safe_call(follow_playlist, sp, pl.id)
                stats["playlists_followed"] += 1
            except Exception as exc:  # noqa: BLE001
                failures.add("mig_follow_playlist", id=pl.id, name=pl.name, reason=str(exc))
        progress("mig_followed", idx, total)

    # 3. Liked tracks – one at a time in ASC order; sleep only around new adds.
    liked = source.liked_tracks
    total = len(liked)
    progress("mig_liked", 0, total)
    for idx, t in enumerate(liked, start=1):
        if t.uri in dest_liked_uris:
            stats["tracks_liked_skipped"] += 1
        else:
            try:
                safe_call(saved_tracks_add, sp, [t.uri])
                stats["tracks_liked_added"] += 1
            except Exception as exc:  # noqa: BLE001
                failures.add("mig_like_track", uri=t.uri, name=t.name, reason=str(exc))
            time.sleep(LIKED_DELAY_S)
        progress("mig_liked", idx, total)

    # 4. Followed artists – batches of 50, only the missing ones.
    missing_artists = [a.id for a in source.followed_artists if a.id not in dest_artist_ids]
    stats["artists_follow_skipped"] = len(source.followed_artists) - len(missing_artists)
    total = len(missing_artists)
    done = 0
    progress("mig_artists", done, total)
    for batch in chunks(missing_artists, 50):
        try:
            safe_call(follow_artists, sp, batch)
            stats["artists_followed"] += len(batch)
        except Exception as exc:  # noqa: BLE001
            failures.add("mig_follow_artists_batch", count=len(batch), reason=str(exc))
        done += len(batch)
        progress("mig_artists", done, total)

    # 5. Saved albums – one at a time in ASC order, only the missing ones.
    albums = source.saved_albums
    total = len(albums)
    progress("mig_albums", 0, total)
    for idx, a in enumerate(albums, start=1):
        if a.id in dest_album_ids:
            stats["albums_save_skipped"] += 1
        else:
            try:
                safe_call(saved_albums_add, sp, [a.id])
                stats["albums_saved"] += 1
            except Exception as exc:  # noqa: BLE001
                failures.add("mig_save_album", id=a.id, name=a.name, reason=str(exc))
            time.sleep(ALBUM_DELAY_S)
        progress("mig_albums", idx, total)

    return stats
