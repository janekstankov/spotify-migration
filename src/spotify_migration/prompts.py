"""Interactive prompts (powered by questionary)."""

from __future__ import annotations

import questionary


def confirm_continue(message: str = "Continue?") -> bool:
    return bool(questionary.confirm(message, default=True).ask())


def select_cleanup_mode() -> str | None:
    """Prompt the user to pick a cleanup mode.

    Returns 'WIPE' | 'ARCHIVE' | 'SKIP', or None if the user aborts (Ctrl-C).
    """
    answer = questionary.select(
        "What should happen to the DESTINATION account's existing content?",
        choices=[
            questionary.Choice(
                title="WIPE     – delete everything (owned playlists, liked songs, artists, albums)",
                value="WIPE",
            ),
            questionary.Choice(
                title=(
                    'ARCHIVE  – prefix owned playlists with "[ARCHIVED] "; '
                    'move liked songs into a new playlist "[ARCHIVED] Liked Songs"; '
                    "leave followed artists and saved albums untouched"
                ),
                value="ARCHIVE",
            ),
            questionary.Choice(
                title="SKIP     – leave the destination as-is and append source content on top",
                value="SKIP",
            ),
        ],
        default="SKIP",
    ).ask()
    return answer


def confirm_wipe() -> bool:
    """WIPE is destructive — require the user to type the word literally."""
    answer = questionary.text(
        "WIPE is destructive. Type WIPE literally to proceed (anything else cancels):",
        default="",
    ).ask()
    return answer == "WIPE"
