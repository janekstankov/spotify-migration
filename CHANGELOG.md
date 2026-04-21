# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- GitHub Actions CI workflow (ruff lint + format check, import smoke test on Python 3.10 – 3.13).
- Form-based issue templates for bug reports and feature requests.
- Pull request template with behaviour / documentation / changelog checklist.
- Dependabot configuration for weekly pip and GitHub Actions updates.
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`.
- `pyproject.toml` with ruff configuration and a `spotify-migration` console-script entry point.
- `requirements-dev.txt`, `.editorconfig`, `.pre-commit-config.yaml`, `Makefile` for a consistent local workflow.
- README badges (CI, license, Python version, latest release, stars).

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

[Unreleased]: https://github.com/janekstankov/spotify-migration/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/janekstankov/spotify-migration/releases/tag/v1.0.0
