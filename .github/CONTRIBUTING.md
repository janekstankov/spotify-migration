# Contributing

Thanks for considering a contribution to Spotify Account Migrator. The guide below covers the typical workflow. If anything is unclear, please open a [discussion](https://github.com/janekstankov/spotify-migration/discussions) before filing an issue — it is the fastest way to get feedback.

## Quick start

```bash
git clone https://github.com/janekstankov/spotify-migration.git
cd spotify-migration

python3 -m venv .venv
source .venv/bin/activate
pip install -e . -r requirements-dev.txt

# (optional) install the pre-commit hook
pre-commit install
```

Run the CLI against a test pair of Spotify accounts the same way an end user would:

```bash
spotify-migration
```

A successful end-to-end test run before sending a PR is strongly preferred when the change touches the cleanup or migration paths.

## Code style

- **Formatter / linter**: [ruff](https://docs.astral.sh/ruff/). Run `make lint` (or `ruff check . && ruff format --check .`) before pushing. `make format` applies formatting.
- **Python**: 3.10+ syntax is acceptable (`|` unions, `match` statements, `TypeVar` defaults, etc.).
- **Type hints**: include them where practical, especially on public functions. Dataclasses are preferred over dicts for structured data.
- **Comments**: explain *why*, not *what*. Skip them when a well-named identifier already carries the meaning.

## Commit messages

Short, imperative, ideally prefixed with a scope:

```
feat: add --dry-run flag
fix: honour Retry-After seconds header on 429
docs: document the Premium-owner requirement
ci: pin ruff to 0.6.9
```

## Pull requests

1. Fork the repo and create a topic branch (`git checkout -b feat/my-change`).
2. Keep the change focused. Separate unrelated refactors into their own PRs.
3. Update `CHANGELOG.md` under the *Unreleased* section.
4. Update the README if user-visible behaviour changes.
5. Make sure `ruff check .` and `ruff format --check .` pass.
6. Push and open a PR against `main`. The PR template will walk you through the rest.

## Reporting bugs

Use the [bug report template](https://github.com/janekstankov/spotify-migration/issues/new?template=bug_report.yml). Before posting terminal output, scrub any Client ID, Client Secret or OAuth `code=` values.

## Security

If you believe you have found a security-relevant issue, **do not** open a public issue — see [SECURITY.md](SECURITY.md) for the disclosure process.
