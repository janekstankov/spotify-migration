"""Read-only account scanner used for both source and destination snapshots.

Produces an AccountSnapshot with everything the migration logic needs:
owned playlists (with tracks in their playlist order), followed playlists,
liked tracks (sorted by added_at ASC), followed artists, saved albums
(sorted by added_at ASC). Local tracks and tombstoned tracks are skipped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import spotipy


@dataclass
class OwnedPlaylist:
    id: str
    name: str
    description: str
    public: bool
    collaborative: bool
    snapshot_id: str
    track_uris: list[str] = field(default_factory=list)
    skipped_local: int = 0
    skipped_none: int = 0


@dataclass
class FollowedPlaylist:
    id: str
    name: str
    owner_id: str


@dataclass
class LikedTrack:
    uri: str
    name: str
    added_at: str


@dataclass
class FollowedArtist:
    id: str
    name: str


@dataclass
class SavedAlbum:
    id: str
    name: str
    added_at: str


@dataclass
class AccountSnapshot:
    me: dict
    owned_playlists: list[OwnedPlaylist]
    followed_playlists: list[FollowedPlaylist]
    liked_tracks: list[LikedTrack]
    followed_artists: list[FollowedArtist]
    saved_albums: list[SavedAlbum]

    @property
    def counts(self) -> dict[str, int]:
        return {
            "playlists_total": len(self.owned_playlists) + len(self.followed_playlists),
            "playlists_owned": len(self.owned_playlists),
            "playlists_followed": len(self.followed_playlists),
            "liked_tracks": len(self.liked_tracks),
            "followed_artists": len(self.followed_artists),
            "saved_albums": len(self.saved_albums),
        }


def _paginate(sp: spotipy.Spotify, first_page: dict) -> list[dict]:
    items = list(first_page.get("items", []))
    page = first_page
    while page.get("next"):
        page = sp.next(page)
        items.extend(page.get("items", []))
    return items


def _fetch_playlist_tracks(
    sp: spotipy.Spotify, playlist_id: str
) -> tuple[list[str], int, int]:
    """Return (track URIs in playlist order, skipped_local, skipped_none)."""
    uris: list[str] = []
    skipped_local = 0
    skipped_none = 0
    page = sp.playlist_items(
        playlist_id,
        limit=100,
        additional_types=("track",),
        fields="items(track(uri,is_local,type)),next",
    )
    while True:
        for item in page.get("items", []):
            track = item.get("track")
            if track is None:
                skipped_none += 1
                continue
            if track.get("is_local"):
                skipped_local += 1
                continue
            uri = track.get("uri")
            if not uri:
                skipped_none += 1
                continue
            uris.append(uri)
        if not page.get("next"):
            break
        page = sp.next(page)
    return uris, skipped_local, skipped_none


def scan_account(
    sp: spotipy.Spotify,
    *,
    fetch_playlist_items: bool = True,
    progress_callback: Any = None,
) -> AccountSnapshot:
    """Scan the account and return a full snapshot.

    When `fetch_playlist_items` is False, owned playlists will have empty
    `track_uris` – useful for a fast initial summary before cleanup.

    `progress_callback(stage: str, done: int, total: int | None)` is invoked at
    stage boundaries so the caller can render progress if desired.
    """

    def notify(stage: str, done: int, total: int | None = None) -> None:
        if progress_callback:
            progress_callback(stage, done, total)

    me = sp.me()
    my_id = me["id"]

    # Playlists – classify as owned (by the current user) vs followed.
    notify("playlists", 0, None)
    first_playlists = sp.current_user_playlists(limit=50)
    all_playlists = _paginate(sp, first_playlists)

    owned: list[OwnedPlaylist] = []
    followed: list[FollowedPlaylist] = []
    for raw in all_playlists:
        if raw is None:
            continue
        owner_id = (raw.get("owner") or {}).get("id")
        if owner_id == my_id:
            owned.append(OwnedPlaylist(
                id=raw["id"],
                name=raw.get("name") or "",
                description=raw.get("description") or "",
                public=bool(raw.get("public")),
                collaborative=bool(raw.get("collaborative")),
                snapshot_id=raw.get("snapshot_id") or "",
            ))
        else:
            followed.append(FollowedPlaylist(
                id=raw["id"],
                name=raw.get("name") or "",
                owner_id=owner_id or "",
            ))

    if fetch_playlist_items:
        for idx, pl in enumerate(owned, start=1):
            notify("playlist_items", idx, len(owned))
            uris, skipped_local, skipped_none = _fetch_playlist_tracks(sp, pl.id)
            pl.track_uris = uris
            pl.skipped_local = skipped_local
            pl.skipped_none = skipped_none

    # Liked tracks – sort ascending by added_at so the oldest is first.
    notify("liked", 0, None)
    first_liked = sp.current_user_saved_tracks(limit=50)
    raw_liked = _paginate(sp, first_liked)
    liked: list[LikedTrack] = []
    for item in raw_liked:
        track = item.get("track") or {}
        if track.get("is_local"):
            continue
        uri = track.get("uri")
        if not uri:
            continue
        liked.append(LikedTrack(
            uri=uri,
            name=track.get("name") or "",
            added_at=item.get("added_at") or "",
        ))
    liked.sort(key=lambda t: t.added_at)

    # Followed artists – cursor-based pagination via `after`.
    notify("artists", 0, None)
    artists: list[FollowedArtist] = []
    after: str | None = None
    while True:
        resp = sp.current_user_followed_artists(limit=50, after=after)
        payload = resp.get("artists", {})
        for a in payload.get("items", []):
            artists.append(FollowedArtist(id=a["id"], name=a.get("name") or ""))
        cursors = payload.get("cursors") or {}
        after = cursors.get("after")
        if not after or not payload.get("next"):
            break

    # Saved albums – sort ascending by added_at.
    notify("albums", 0, None)
    first_albums = sp.current_user_saved_albums(limit=50)
    raw_albums = _paginate(sp, first_albums)
    albums: list[SavedAlbum] = []
    for item in raw_albums:
        album = item.get("album") or {}
        aid = album.get("id")
        if not aid:
            continue
        albums.append(SavedAlbum(
            id=aid,
            name=album.get("name") or "",
            added_at=item.get("added_at") or "",
        ))
    albums.sort(key=lambda a: a.added_at)

    return AccountSnapshot(
        me=me,
        owned_playlists=owned,
        followed_playlists=followed,
        liked_tracks=liked,
        followed_artists=artists,
        saved_albums=albums,
    )
