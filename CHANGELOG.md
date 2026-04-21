# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.1] — 2026-04-21

### Changed
- **Repository layout.** The Python modules now live in `src/spotify_migration/` as a proper installable package, and the community health docs (`CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`) have moved to `.github/`. The root directory is noticeably smaller, with code and metadata clearly separated.
- **Invocation.** The recommended entry points are now `spotify-migration` (after `pip install -e .`) or `python -m spotify_migration`. The old `python migrate.py` no longer applies because `migrate.py` is inside a package. Token caches and JSON reports continue to be written next to the user's working directory, so existing installations keep their `.cache-source` and `.cache-destination` files.

### Added
- GitHub Actions CI workflow (ruff lint + format check, install-and-import smoke test on Python 3.10 – 3.13).
- Form-based issue templates for bug reports and feature requests.
- Pull request template with behaviour / documentation / changelog checklist.
- Dependabot configuration for weekly pip and GitHub Actions updates.
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md` under `.github/`.
- `pyproject.toml` with a `spotify-migration` console-script entry point, ruff configuration and PyPI classifiers.
- `requirements-dev.txt`, `.editorconfig`, `.pre-commit-config.yaml`, `Makefile` for a consistent local workflow.
- README badges (CI, release, Python version, license, Ruff, PRs welcome, stars).
- Branch protection on `main` requiring the full CI matrix to pass before merging.

### Updated
- `actions/checkout` bumped to v6 and `actions/setup-python` bumped to v6 (resolves the Node 20 deprecation warning).
- `ruff` bumped to 0.15.11 (in `requirements-dev.txt` and `.pre-commit-config.yaml`).

## [1.0.0] — 2026-04-21

### Added
- First stable release.
- OAuth flow for a pair of Spotify accounts (manual-paste friendly, survives browsers that block `http://127.0.0.1` redirects).
- Read-only scanner producing an `AccountSnapshot` of owned playlists (with tracks in playlist order), followed playlists, liked tracks (ASC by `added_at`), followed artists and saved albums (ASC by `added_at`).
- Three cleanup modes for the destination account: `WIPE`, `ARCHIVE`, `SKIP`.
- Idempotent migration: diffs source against destination and only writes what is missing; safely re-runs after interruptions.
- Rate-limit-aware retries honouring Spotify's `Retry-After` header; exponential back-off on 5xx errors.
- Per-run JSON report in `logs/migration_YYYYMMDD_HHMMSS.json` with failure details.
- Drop-in replacements for the `me/library`-based spotipy 2.26 endpoints that are broken upstream (saved tracks, saved albums, followed artists, followed playlists).

[Unreleased]: https://github.com/janekstankov/spotify-migration/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/janekstankov/spotify-migration/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/janekstankov/spotify-migration/releases/tag/v1.0.0
