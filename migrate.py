"""Spotify Account Migrator – command-line entry point.

Orchestrates the full migration pipeline:
  1. OAuth into the source account
  2. OAuth into the destination account
  3. Scan the source
  4. Scan the destination
  5. Pick a cleanup mode (WIPE / ARCHIVE / SKIP) and confirm
  6. Execute cleanup (then re-scan the destination) and migrate source content

A JSON report is written to logs/migration_YYYYMMDD_HHMMSS.json at the end.
"""
from __future__ import annotations

import sys
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from auth import (
    MissingCredentialsError,
    describe_user,
    get_destination_client,
    get_source_client,
)
from destination import CLEANUP_FNS, migrate_content
from prompts import confirm_continue, confirm_wipe, select_cleanup_mode
from source import AccountSnapshot, scan_account
from utils import FailureLog, MigrationReport, save_report

console = Console()


def _login_step(step: str, label: str, getter) -> tuple:
    console.print(f"\n[bold cyan]{step}[/bold cyan] Signing into the [bold]{label}[/bold] account...")
    client = getter()
    user = describe_user(client)
    name = user["display_name"] or user["id"]
    console.print(f"      [green]✓[/green] Signed in as [bold]{name}[/bold] ([dim]id: {user['id']}[/dim])")
    return client, user


def _scan_step(step: str, label: str, client, *, fetch_items: bool) -> AccountSnapshot:
    console.print(f"\n[bold cyan]{step}[/bold cyan] Scanning [bold]{label}[/bold] account...")
    with console.status(f"[dim]fetching {label}...[/dim]", spinner="dots"):
        snapshot = scan_account(client, fetch_playlist_items=fetch_items)
    c = snapshot.counts
    console.print(
        f"      [green]✓[/green] {c['playlists_total']} playlists "
        f"([bold]{c['playlists_owned']}[/bold] owned, "
        f"[bold]{c['playlists_followed']}[/bold] followed)"
    )
    console.print(f"      [green]✓[/green] {c['liked_tracks']} liked tracks")
    console.print(f"      [green]✓[/green] {c['followed_artists']} followed artists")
    console.print(f"      [green]✓[/green] {c['saved_albums']} saved albums")
    return snapshot


def _print_comparison(source: AccountSnapshot, destination: AccountSnapshot) -> None:
    table = Table(title="Account comparison", show_lines=False, border_style="dim")
    table.add_column("", style="dim")
    table.add_column("SOURCE", justify="right", style="cyan")
    table.add_column("DESTINATION", justify="right", style="magenta")
    src = source.counts
    dst = destination.counts
    rows = [
        ("Owned playlists", src["playlists_owned"], dst["playlists_owned"]),
        ("Followed playlists", src["playlists_followed"], dst["playlists_followed"]),
        ("Liked tracks", src["liked_tracks"], dst["liked_tracks"]),
        ("Followed artists", src["followed_artists"], dst["followed_artists"]),
        ("Saved albums", src["saved_albums"], dst["saved_albums"]),
    ]
    for label, s_val, d_val in rows:
        table.add_row(label, str(s_val), str(d_val))
    console.print()
    console.print(table)


def _describe_plan(mode: str, source: AccountSnapshot, destination: AccountSnapshot) -> None:
    console.print()
    console.print(f"[bold]Plan for {mode} mode:[/bold]")
    src = source.counts
    dst = destination.counts

    if mode == "WIPE":
        console.print(
            f"  [red]✗[/red] remove from destination: "
            f"{dst['playlists_owned']} owned playlists, "
            f"{dst['playlists_followed']} followed, "
            f"{dst['liked_tracks']} liked, "
            f"{dst['followed_artists']} artists, "
            f"{dst['saved_albums']} albums"
        )
    elif mode == "ARCHIVE":
        console.print(
            f"  [yellow]●[/yellow] rename: up to {dst['playlists_owned']} owned playlists "
            f"→ prefix [bold]\"[ARCHIVED] \"[/bold]"
        )
        if dst["liked_tracks"]:
            console.print(
                f"  [yellow]●[/yellow] destination's liked tracks ({dst['liked_tracks']}) "
                f"→ new playlist [bold]\"[ARCHIVED] Liked Songs\"[/bold]; Liked Songs slot cleared"
            )
        else:
            console.print("  [dim]●[/dim] destination has no liked tracks – nothing to archive")
        console.print(
            f"  [dim]●[/dim] {dst['playlists_followed']} followed playlists, "
            f"{dst['followed_artists']} artists, {dst['saved_albums']} albums — "
            f"[bold]kept untouched[/bold]"
        )
    else:
        console.print("  [dim]●[/dim] destination is left unchanged")

    console.print()
    console.print("  [green]+[/green] migrate from source to destination:")
    console.print(
        f"      {src['playlists_owned']} owned playlists (tracks in original order)"
    )
    console.print(f"      {src['playlists_followed']} followed playlists")
    console.print(
        f"      {src['liked_tracks']} liked tracks "
        f"[dim](one at a time, 0.2 s delay ≈ {src['liked_tracks'] * 0.2 / 60:.1f} min)[/dim]"
    )
    console.print(f"      {src['followed_artists']} artists")
    console.print(
        f"      {src['saved_albums']} albums "
        f"[dim](one at a time, 0.2 s delay)[/dim]"
    )


STAGE_LABELS = {
    "wipe_playlists": "WIPE playlists",
    "wipe_liked": "WIPE liked tracks",
    "wipe_artists": "WIPE followed artists",
    "wipe_albums": "WIPE saved albums",
    "archive_rename": "ARCHIVE rename playlists",
    "archive_liked_add": "ARCHIVE liked → playlist",
    "archive_liked_clear": "ARCHIVE clear Liked Songs",
    "mig_playlists": "Owned playlists",
    "mig_followed": "Followed playlists",
    "mig_liked": "Liked tracks",
    "mig_artists": "Followed artists",
    "mig_albums": "Saved albums",
}


class ProgressTracker:
    """Wrapper around rich.Progress that lazily creates a task per stage.

    Stages with no work to do (total == 0) are skipped to keep the UI tidy.
    """

    def __init__(self, progress: Progress) -> None:
        self._progress = progress
        self._tasks: dict[str, int] = {}

    def __call__(self, stage: str, done: int, total: int) -> None:
        if total <= 0:
            return
        label = STAGE_LABELS.get(stage, stage)
        if stage not in self._tasks:
            self._tasks[stage] = self._progress.add_task(label, total=total)
        task_id = self._tasks[stage]
        self._progress.update(task_id, completed=done, total=total)


def main() -> int:
    console.print(Panel.fit(
        "[bold]Spotify Account Migrator[/bold]\n"
        "[dim]OAuth → scan → cleanup → migration[/dim]",
        border_style="cyan",
    ))

    try:
        source_sp, source_user = _login_step("[1/6]", "SOURCE", get_source_client)
        destination_sp, destination_user = _login_step("[2/6]", "DESTINATION", get_destination_client)
    except MissingCredentialsError as exc:
        console.print(f"\n[red]✗[/red] {exc}")
        return 2
    except Exception as exc:  # noqa: BLE001
        console.print(f"\n[red]✗[/red] Sign-in failed: {exc}")
        return 1

    if source_user["id"] == destination_user["id"]:
        console.print(
            "\n[yellow]⚠[/yellow] Both accounts share the same ID. "
            "Sign out and make sure each cache file is tied to a different Spotify account."
        )
        return 3

    try:
        source_snapshot = _scan_step("[3/6]", "SOURCE", source_sp, fetch_items=True)
        destination_snapshot = _scan_step("[4/6]", "DESTINATION", destination_sp, fetch_items=True)
    except Exception as exc:  # noqa: BLE001
        console.print(f"\n[red]✗[/red] Scan failed: {exc}")
        return 1

    _print_comparison(source_snapshot, destination_snapshot)

    console.print("\n[bold cyan][5/6][/bold cyan] Choose a cleanup mode for the DESTINATION account:")
    mode = select_cleanup_mode()
    if not mode:
        console.print("[yellow]Cancelled.[/yellow]")
        return 0

    _describe_plan(mode, source_snapshot, destination_snapshot)

    if mode == "WIPE":
        if not confirm_wipe():
            console.print("[yellow]WIPE not confirmed. Cancelled.[/yellow]")
            return 0
    else:
        if not confirm_continue(f"Run {mode} mode?"):
            console.print("[yellow]Cancelled.[/yellow]")
            return 0

    failures = FailureLog()
    report = MigrationReport(
        started_at=datetime.now().isoformat(),
        source_user_id=source_user["id"],
        source_user_name=source_user["display_name"] or source_user["id"],
        destination_user_id=destination_user["id"],
        destination_user_name=destination_user["display_name"] or destination_user["id"],
        mode=mode,
        source_counts=source_snapshot.counts,
        destination_counts=destination_snapshot.counts,
    )

    console.print("\n[bold cyan][6/6][/bold cyan] Running...\n")

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    )
    tracker = ProgressTracker(progress)

    with progress:
        cleanup_fn = CLEANUP_FNS[mode]
        cleanup_kwargs: dict = {"failures": failures, "progress": tracker}
        if mode == "ARCHIVE":
            # Do not archive destination playlists whose name matches one of the
            # source's owned playlists – those are either imports from a previous
            # run or a name collision that the idempotent migration will merge.
            cleanup_kwargs["protect_names"] = {
                pl.name for pl in source_snapshot.owned_playlists
            }
        cleanup_result = cleanup_fn(
            destination_sp, destination_snapshot, **cleanup_kwargs
        )
        report.cleanup = cleanup_result

        if mode != "SKIP":
            # Cleanup changed destination state; re-scan so the migration step
            # sees the fresh snapshot and can diff correctly (idempotency).
            console.print("[dim]  re-scanning destination after cleanup...[/dim]")
            destination_snapshot = scan_account(destination_sp, fetch_playlist_items=True)

        stats = migrate_content(
            destination_sp,
            source_snapshot,
            destination_snapshot,
            destination_user_id=destination_user["id"],
            failures=failures,
            progress=tracker,
        )
        report.stats = stats

    report.failures = failures.entries
    report.finished_at = datetime.now().isoformat()
    report_path = save_report(report)

    console.print()
    added = (
        stats.get("playlists_created", 0)
        + stats.get("playlists_updated", 0)
        + stats.get("playlists_followed", 0)
        + stats.get("tracks_liked_added", 0)
        + stats.get("artists_followed", 0)
        + stats.get("albums_saved", 0)
    )
    skipped = (
        stats.get("playlists_skipped", 0)
        + stats.get("playlists_follow_skipped", 0)
        + stats.get("tracks_liked_skipped", 0)
        + stats.get("artists_follow_skipped", 0)
        + stats.get("albums_save_skipped", 0)
    )
    console.print(f"[green]✓[/green] Done. Report: [bold]{report_path}[/bold]")
    console.print(
        f"  Added / updated: [green]{added}[/green]   "
        f"Skipped (already present): [dim]{skipped}[/dim]   "
        f"Errors: [{'red' if failures else 'green'}]{len(failures)}[/]"
    )
    console.print(
        f"  [dim]Playlists: created={stats.get('playlists_created', 0)} "
        f"updated={stats.get('playlists_updated', 0)} "
        f"skipped={stats.get('playlists_skipped', 0)}; "
        f"tracks added={stats.get('playlist_tracks_added', 0)}[/dim]"
    )
    console.print(
        f"  [dim]Liked: +{stats.get('tracks_liked_added', 0)} "
        f"(already present: {stats.get('tracks_liked_skipped', 0)})[/dim]"
    )
    console.print(
        f"  [dim]Followed: +{stats.get('playlists_followed', 0)} playlists / "
        f"+{stats.get('artists_followed', 0)} artists / "
        f"+{stats.get('albums_saved', 0)} albums[/dim]"
    )
    if mode != "SKIP":
        console.print(f"  [dim]Cleanup: {cleanup_result}[/dim]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
