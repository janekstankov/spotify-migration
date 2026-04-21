# Spotify Account Migrator

A Python command-line tool that moves the entire contents of one Spotify account to another — owned playlists, followed playlists, liked songs, followed artists and saved albums — while preserving the order in which everything was added.

The migration is **idempotent**: it diffs the source against the destination before writing, adds only what is missing, and can be safely re-run after an interrupted session.

## Features

- Transfers **owned playlists** (tracks in their original playlist order), **followed playlists**, **liked songs**, **followed artists** and **saved albums**.
- Preserves `added_at` order for liked songs and saved albums, so the *Recently Added* view on the new account mirrors the old one.
- Three cleanup modes for the destination account:
  - **WIPE** — remove everything before writing (requires typing `WIPE` to confirm).
  - **ARCHIVE** — rename existing owned playlists with an `[ARCHIVED]` prefix and move liked songs into a dedicated `[ARCHIVED] Liked Songs` playlist. Followed playlists, artists and albums stay untouched.
  - **SKIP** — leave the destination as-is and append the source contents on top.
- **Idempotent**: every write is preceded by a diff against the destination's current state. A crashed run can be resumed simply by re-running the command; nothing is duplicated.
- Automatic retry/back-off on HTTP 429 (honouring `Retry-After`) and transient 5xx failures.
- Full JSON report written to `logs/migration_YYYYMMDD_HHMMSS.json` on every run, including per-item failures.

## Demo

```text
╭──────────────────────────────────────╮
│ Spotify Account Migrator             │
│ OAuth → scan → cleanup → migration   │
╰──────────────────────────────────────╯

[1/6] Signing into the SOURCE account...
      ✓ Signed in as old-account

[2/6] Signing into the DESTINATION account...
      ✓ Signed in as new-account

[3/6] Scanning SOURCE account...
      ✓ 39 playlists (28 owned, 11 followed)
      ✓ 1002 liked tracks
      ✓ 17 followed artists
      ✓ 2 saved albums

[4/6] Scanning DESTINATION account...
      ✓ 0 playlists (0 owned, 0 followed)
      ✓ 0 liked tracks
      ✓ 0 followed artists
      ✓ 0 saved albums

[5/6] Choose a cleanup mode for the DESTINATION account:
  ❯ WIPE     – delete everything
    ARCHIVE  – rename existing owned content with an "[ARCHIVED]" prefix
    SKIP     – leave the destination as-is and append source content on top

[6/6] Running...
  Owned playlists    ━━━━━━━━━━━━━━━━━━━━━━━━ 28/28     0:00:15
  Followed playlists ━━━━━━━━━━━━━━━━━━━━━━━━ 11/11     0:00:02
  Liked tracks       ━━━━━━━━━━━━━━━━━━━━━━━━ 1002/1002 0:05:31
  Followed artists   ━━━━━━━━━━━━━━━━━━━━━━━━ 17/17     0:00:00
  Saved albums       ━━━━━━━━━━━━━━━━━━━━━━━━ 2/2       0:00:00

✓ Done. Report: logs/migration_20260421_142636.json
  Added / updated: 1060   Skipped (already present): 0   Errors: 0
```

## Requirements

- Python 3.10 or newer
- A Spotify account with **active Premium** to own the Developer Dashboard application (see [Premium requirement](#premium-requirement))
- Two Spotify accounts to migrate between
- macOS, Linux or WSL (anywhere Python runs)

## Installation

```bash
git clone https://github.com/janekstankov/spotify-migration.git
cd spotify-migration

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Spotify Developer setup

1. Sign in to <https://developer.spotify.com/dashboard> using a Spotify account **with active Premium**.
2. Click **Create app** and fill in:
   - *Name* and *Description* — any value.
   - *Redirect URI* — exactly `http://127.0.0.1:8888/callback`.
   - *Which API* — select **Web API**.
3. Open the new app's **Settings**:
   - Copy the **Client ID** and **Client secret**.
   - In the **User Management** tab, add the e-mail addresses of **both** accounts (source and destination). While the app runs in Development mode, Spotify rejects API calls from users that are not explicitly whitelisted.
4. Create a `.env` file from the template:
   ```bash
   cp .env.example .env
   ```
   and fill in the values:
   ```
   SPOTIFY_CLIENT_ID=...
   SPOTIFY_CLIENT_SECRET=...
   SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
   ```

### Premium requirement

Since late 2025, Spotify requires that the **owner of a Developer Dashboard application have an active Premium subscription**. Without it, every Web API call returns HTTP 403 with `Active premium subscription required for the owner of the app`. The accounts being migrated do not have to be Premium — only the account that created the application.

## Usage

```bash
.venv/bin/python migrate.py
```

The tool walks through six steps:

1. **Sign in to the source account.** The console prints a URL of the form `https://accounts.spotify.com/authorize?...`. Open it in a browser signed into the source account and click *Agree*. Spotify redirects to `http://127.0.0.1:8888/callback?code=...` — the browser will very likely display an error page such as *"Safari cannot open the page"* or *"This site can't be reached"*. **That is expected.** Copy the full URL from the address bar and paste it back into the terminal prompt.
2. **Sign in to the destination account.** Same flow. If the browser remembers the previous session, open the authorization URL in a private window or sign out of Spotify first.
3. **Scan the source account** — playlists, liked tracks, followed artists and saved albums.
4. **Scan the destination account** — same.
5. **Pick a cleanup mode** — use the arrow keys to choose WIPE, ARCHIVE or SKIP. WIPE requires you to type `WIPE` literally as a second confirmation.
6. **Execution** — a live progress bar per stage, followed by a JSON report written to `logs/migration_YYYYMMDD_HHMMSS.json`.

OAuth tokens are cached in `.cache-source` and `.cache-destination`, so subsequent runs do not require the browser round-trip unless a token expires.

## Cleanup modes

### WIPE

Unfollows every playlist (Spotify treats unfollowing an owned playlist as deletion), removes every liked track, unfollows every artist and removes every saved album. The destination account is effectively emptied before new content is written. Because this is destructive, the tool requires an explicit second confirmation (you must type `WIPE`).

### ARCHIVE

Preserves the destination's existing content behind an `[ARCHIVED]` prefix instead of deleting it:

- Every owned playlist is renamed from `Name` to `[ARCHIVED] Name` (Spotify's 100-character playlist-name limit is respected).
- All liked tracks are moved into a new private playlist called `[ARCHIVED] Liked Songs` (preserving their original `added_at` order) and the Liked Songs slot is cleared so the imported source tracks land cleanly.
- Followed playlists, followed artists and saved albums are **not** modified; they remain on the account alongside the new ones.

### SKIP

Leaves the destination untouched. New content from the source is appended next to whatever is already there.

## Idempotency

Every write is preceded by a diff against the destination's current state:

- **Owned playlists** are matched by name (destination playlists whose name starts with `[ARCHIVED]` are excluded from matching). If a match exists, only the URIs missing from it are added; otherwise a new playlist is created.
- **Followed playlists** are matched by playlist ID.
- **Liked tracks** are matched by track URI.
- **Followed artists** are matched by artist ID.
- **Saved albums** are matched by album ID.
- `[ARCHIVED] Liked Songs` is **reused** across runs when it already exists; only missing URIs are appended, so repeated archiving does not duplicate content.

As a result, a run that was interrupted by a network failure, a crashed terminal or any other accident can be resumed simply by running `migrate.py` again — the tool recomputes the diff and continues.

## Report

A JSON report is written to `logs/migration_YYYYMMDD_HHMMSS.json` after every run:

```json
{
  "started_at": "2026-04-21T14:20:00",
  "finished_at": "2026-04-21T14:26:36",
  "source_user_id": "...",
  "destination_user_id": "...",
  "mode": "ARCHIVE",
  "source_counts": { "playlists_owned": 28, "liked_tracks": 1002, "...": "..." },
  "destination_counts": { "...": "..." },
  "cleanup": { "playlists_renamed": 5, "liked_slot_cleared": 500, "...": "..." },
  "stats": {
    "playlists_created": 28,
    "tracks_liked_added": 1002,
    "artists_followed": 17,
    "albums_saved": 2,
    "...": "..."
  },
  "failures": []
}
```

Failed items (tracks unavailable in the destination region, tracks removed from the Spotify catalogue, rate-limit exhaustion) are captured in the `failures` array with a reason for each.

## Architecture

```
spotify-migration/
├── migrate.py        # orchestrator: 6-step CLI, progress bars, JSON report
├── auth.py           # dual OAuth, per-account token cache, manual-paste flow
├── source.py         # read-only account scanner (scan_account → AccountSnapshot)
├── destination.py    # cleanup (WIPE/ARCHIVE/SKIP) + idempotent migration
├── prompts.py        # questionary prompts (mode picker, confirmations)
├── utils.py          # retry with Retry-After, JSON report writer,
│                     #   workarounds for broken spotipy endpoints
├── requirements.txt
├── .env.example
└── logs/             # JSON reports (git-ignored)
```

## Known limitations

- **spotipy 2.26 bug workaround.** Several library/follow methods in spotipy 2.26 (`current_user_saved_tracks_*`, `current_user_saved_albums_*`, `user_follow_artists`, `user_unfollow_artists`, `current_user_follow_playlist`) target a non-existent `me/library` endpoint instead of the correct Web API URLs. `utils.py` contains drop-in replacements that call the correct endpoints directly. Once upstream fixes this, the wrappers can be removed.
- **Playlist folders are not migrated.** Spotify's Web API does not expose folders — they exist only in the desktop client.
- **Collaborative playlists are copied as private.** Spotify requires a playlist to be public before a second flip to collaborative.
- **Local files** (`track.is_local == True`) are skipped and logged to `failures`.
- **Tracks removed from the Spotify catalogue** (returned as `null` in playlist responses) are skipped.
- **Playlist name collisions.** Owned-playlist matching uses exact name equality. If the destination account already has an unrelated playlist with the same name as one on the source, the two will be merged (missing URIs from the source will be appended to the existing destination playlist).
- **No `--dry-run` flag yet.** The plan is previewed before each run, but nothing replaces actually running the tool without a destination account.
- **Throughput cap on liked songs and albums.** A 200 ms pause is inserted between individual add requests so that Spotify's *Recently Added* sort preserves the source ordering. Expect roughly 5 minutes per 1 500 liked tracks.

## Roadmap

- `--dry-run` flag to preview the full set of writes without touching the destination
- `--only=playlists,liked,artists,albums` selector to migrate a subset
- Resume via on-disk state (checkpoint every N items)
- Match owned playlists by `snapshot_id` / stored source id rather than by name, to handle deliberate renames

## License

Released under the [MIT License](LICENSE).
