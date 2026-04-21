# Security Policy

## Supported versions

Only the latest `v1.x` release receives security fixes.

| Version | Supported |
| ------- | --------- |
| 1.x     | ✅        |
| < 1.0   | ❌        |

## Reporting a vulnerability

**Please do not open a public GitHub issue for security problems.**

Instead, use GitHub's private vulnerability reporting:

1. Go to <https://github.com/janekstankov/spotify-migration/security/advisories>.
2. Click **Report a vulnerability** and describe the issue in detail.

Alternatively, open a confidential discussion with the maintainer via GitHub.

You can expect an initial acknowledgement within **72 hours** and a more substantive response within **7 days**. If a fix is required, we will coordinate a private patch, publish a release, and then publicly disclose the issue with credit.

## Scope

In scope:

- Anything that allows an attacker to read, modify or delete Spotify account content without authorisation.
- Accidental disclosure of Client ID / Client Secret / OAuth tokens through the tool itself (logs, reports, commits).
- Dependency vulnerabilities that are actually reachable from the codepaths the tool executes.

Out of scope:

- Issues in user-supplied Spotify Developer applications (Client ID / Secret management is the user's responsibility).
- Bugs in Spotify's Web API itself — those should be reported to Spotify.
- Theoretical concerns about the Spotify OAuth scopes requested by the tool (they are the minimum required for the advertised functionality and are listed explicitly in the README).
