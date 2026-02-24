# src/beautyspot/cli.py

import sys
import socket
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn

from beautyspot.maintenance import MaintenanceService

app = typer.Typer(
    name="beautyspot",
    help="🌑 beautyspot - Intelligent caching for ML pipelines",
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()


# =============================================================================
# Helper Functions
# =============================================================================


def get_service(db_path: str, blob_dir: Optional[str] = None) -> MaintenanceService:
    """
    Initialize MaintenanceService from CLI arguments.
    """
    path = Path(db_path)
    if not path.exists():
        console.print(f"[red]Error:[/red] Database not found: {db_path}")
        raise typer.Exit(1)

    return MaintenanceService.from_path(path, blob_dir)


def _is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


def _find_available_port(start_port: int, max_attempts: int = 10) -> int:
    for i in range(max_attempts):
        port = start_port + i
        if not _is_port_in_use(port):
            return port
    raise RuntimeError(
        f"No available port found in range {start_port}-{start_port + max_attempts - 1}"
    )


def _format_size(size_bytes: int | float) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _format_timestamp(timestamp: float) -> str:
    from datetime import timezone

    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone()
    return dt.strftime("%Y-%m-%d %H:%M")


def _get_task_count(db_path: Path) -> int:
    """
    Get task count using SQLiteTaskDB.count_tasks (no writer thread started).
    """
    from beautyspot.db import SQLiteTaskDB

    return SQLiteTaskDB.count_tasks(db_path)


def _list_databases():
    beautyspot_dir = Path(".beautyspot")

    if not beautyspot_dir.exists():
        console.print(
            Panel(
                "[yellow]No .beautyspot/ directory found in current path.[/yellow]\n\n"
                "[dim]Hint: Run your cached functions first, or specify a database path:[/dim]\n"
                "  beautyspot list ./path/to/tasks.db",
                title="🌑 beautyspot",
                border_style="yellow",
            )
        )
        raise typer.Exit(0)

    db_files = list(beautyspot_dir.glob("**/*.db")) + list(
        beautyspot_dir.glob("**/*.sqlite")
    )

    if not db_files:
        console.print(
            Panel(
                "[yellow]No SQLite databases found in .beautyspot/[/yellow]\n\n"
                "[dim]Hint: Run your cached functions first to create a database.[/dim]",
                title="🌑 beautyspot",
                border_style="yellow",
            )
        )
        raise typer.Exit(0)

    table = Table(
        title="🌑 Available Databases",
        show_header=True,
        header_style="bold magenta",
        border_style="blue",
    )

    table.add_column("Database", style="cyan")
    table.add_column("Size", style="green", justify="right")
    table.add_column("Modified", style="dim")
    table.add_column("Tasks", style="yellow", justify="right")

    for db_path in sorted(db_files):
        stat = db_path.stat()
        size = _format_size(stat.st_size)
        modified = _format_timestamp(stat.st_mtime)
        task_count = _get_task_count(db_path)

        table.add_row(
            str(db_path),
            size,
            modified,
            str(task_count) if task_count >= 0 else "-",
        )

    console.print(table)
    console.print()
    console.print("[dim]Hint: beautyspot list <database> to view tasks[/dim]")


def _list_tasks(db: str, limit: int, func: Optional[str]):
    with get_service(db) as spot:
        _list_tasks_inner(spot, limit, func)


def _list_tasks_inner(spot: MaintenanceService, limit: int, func: Optional[str]):
    df = spot.db.get_history(limit=limit)

    if df.empty:
        console.print("[yellow]No tasks recorded yet.[/yellow]")
        raise typer.Exit(0)

    if func:
        # Note: Filtering DataFrame returns DataFrame, so this is safe from 'if df:' issue
        if "func_identifier" in df.columns:
            func_mask = df["func_name"].str.contains(func, na=False)  # type: ignore
            func_id_mask = df["func_identifier"].fillna("").str.contains(func, na=False)  # type: ignore
            df = df[func_mask | func_id_mask]  # type: ignore
        else:
            df = df[df["func_name"].str.contains(func, na=False)]  # type: ignore
        if df.empty:
            console.print(f"[yellow]No tasks found for function: {func}[/yellow]")
            raise typer.Exit(0)

    table = Table(
        title=f"🌑 beautyspot Tasks ({len(df)} records)",
        show_header=True,
        header_style="bold magenta",
        border_style="blue",
    )

    table.add_column("Function", style="cyan", no_wrap=True)
    table.add_column("Cache Key", style="magenta", no_wrap=True)
    table.add_column("Input ID", style="dim", max_width=20)
    table.add_column("Version", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Content", style="blue")
    table.add_column("Updated", style="dim")
    table.add_column("Expires", style="red")

    # iterrows yields (index, Series)
    for _, row in df.iterrows():
        input_id = (
            str(row["input_id"])[:20] + "..."
            if len(str(row["input_id"])) > 20
            else str(row["input_id"])
        )

        # [FIX] Avoid pd.notna() in conditional to satisfy strict type checkers
        # row.get returns Any, which might be scalar or None here.
        expires_at: Any = row.get("expires_at")
        expires_str = str(expires_at) if expires_at is not None else "-"

        cache_key_short = str(row["cache_key"])[:8]

        func_identifier = (
            row.get("func_identifier") if "func_identifier" in row else None
        )
        if isinstance(func_identifier, str) and func_identifier:
            func_display = func_identifier
        else:
            func_display = str(row["func_name"])

        table.add_row(
            func_display,
            cache_key_short,
            input_id,
            str(row["version"] or "-"),
            str(row["result_type"]),
            str(row["content_type"] or "-"),
            str(row["updated_at"]),
            expires_str,
        )

    console.print(table)


# =============================================================================
# Commands
# =============================================================================


@app.command("ui")
def ui_cmd(
    db: str = typer.Argument(..., help="Path to SQLite database file"),
    port: int = typer.Option(8501, "--port", "-p", help="Streamlit server port"),
    auto_port: bool = typer.Option(
        True, "--auto-port/--no-auto-port", help="Auto-find available port"
    ),
):
    """
    🚀 Launch the interactive dashboard.
    """
    db_path = Path(db)
    if not db_path.exists():
        console.print(f"[red]Error:[/red] Database not found: {db}")
        raise typer.Exit(1)

    actual_port = port
    if _is_port_in_use(port):
        if auto_port:
            try:
                actual_port = _find_available_port(port + 1)
                console.print(
                    f"[yellow]Port {port} is in use. Using port {actual_port} instead.[/yellow]"
                )
            except RuntimeError as e:
                console.print(f"[red]Error:[/red] {e}")
                raise typer.Exit(1)
        else:
            console.print(f"[red]Error:[/red] Port {port} is already in use.")
            raise typer.Exit(1)

    console.print(
        Panel.fit(
            f"[bold green]Starting beautyspot Dashboard[/bold green]\n\n"
            f"📁 Database: [cyan]{db}[/cyan]\n"
            f"🌐 Port: [cyan]{actual_port}[/cyan]\n"
            f"🔗 URL: [cyan]http://localhost:{actual_port}[/cyan]\n\n"
            f"[dim]Press Ctrl+C to stop[/dim]",
            title="🌑 beautyspot",
            border_style="blue",
        )
    )

    dashboard_path = Path(__file__).parent / "dashboard.py"

    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(dashboard_path),
                "--server.port",
                str(actual_port),
                "--server.headless",
                "true",
                "--",
                "--db",
                str(db_path.absolute()),
            ],
            check=True,
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Dashboard stopped.[/yellow]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error:[/red] Failed to start dashboard: {e}")
        raise typer.Exit(1)


@app.command("list")
def list_cmd(
    db: Optional[str] = typer.Argument(None, help="Path to SQLite database file"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of records to show"),
    func: Optional[str] = typer.Option(
        None, "--func", "-f", help="Filter by function name"
    ),
):
    """
    📋 List cached tasks or available databases.
    """
    if db is None:
        _list_databases()
        return

    _list_tasks(db, limit, func)


@app.command("show")
def show_cmd(
    db: str = typer.Argument(..., help="Path to SQLite database file"),
    cache_key: str = typer.Argument(..., help="Cache key (full or prefix) to inspect"),
):
    """
    🔍 Show details of a specific cached task.
    """
    with get_service(db) as service:
        _show_cmd_inner(service, cache_key)


def _show_cmd_inner(service: MaintenanceService, cache_key: str):
    # Prefix-based key resolution
    resolved = service.resolve_key_prefix(cache_key)

    if resolved is None:
        console.print(f"[red]Error:[/red] Cache key not found: {cache_key}")
        raise typer.Exit(1)

    if isinstance(resolved, list):
        console.print(
            f"[yellow]Ambiguous key prefix '{cache_key}'. Candidates:[/yellow]"
        )
        for cand in resolved[:10]:
            console.print(f"  - {cand}")
        if len(resolved) > 10:
            console.print(f"  [dim]... and {len(resolved) - 10} more[/dim]")
        raise typer.Exit(1)

    real_key = resolved

    result = service.get_task_detail(real_key, include_expired=True)
    if result is None:
        console.print(f"[red]Error:[/red] Failed to retrieve details for: {real_key}")
        raise typer.Exit(1)

    expires_at = result.get("expires_at")

    detail_text = (
        f"[bold]Cache Key:[/bold] [cyan]{real_key}[/cyan]\n"
        f"[bold]Result Type:[/bold] [yellow]{result.get('result_type')}[/yellow]\n"
        f"[bold]Result Value:[/bold] {result.get('result_value') or '-'}\n"
        f"[bold]Has Blob Data:[/bold] {'Yes' if result.get('result_data') else 'No'}\n"
        f"[bold]Expires At:[/bold] [red]{expires_at if expires_at else '-'}[/red]"
    )

    console.print(
        Panel(
            detail_text,
            title="🔍 Task Details",
            border_style="green",
        )
    )

    data = result.get("decoded_data")

    if data is not None:
        try:
            import json

            if isinstance(data, (dict, list)):
                json_str = json.dumps(data, indent=2, ensure_ascii=False, default=str)
                syntax = Syntax(json_str, "json", theme="monokai", line_numbers=True)
                console.print(
                    Panel(syntax, title="📦 Data Preview (JSON)", border_style="blue")
                )
            elif isinstance(data, str):
                preview = data[:1000] + "..." if len(data) > 1000 else data
                console.print(
                    Panel(
                        preview, title="📦 Data Preview (String)", border_style="blue"
                    )
                )
            else:
                console.print(
                    Panel(
                        f"[dim]Type: {type(data).__name__}[/dim]\n{str(data)[:1000]}",
                        title="📦 Data Preview (Object)",
                        border_style="blue",
                    )
                )

        except Exception as e:
            console.print(f"[yellow]Error displaying data: {e}[/yellow]")

    elif result.get("result_data") is not None or (
        result.get("result_type") == "FILE" and result.get("result_value")
    ):
        console.print(
            "[yellow]Could not decode blob data (Serialization format mismatch or missing file).[/yellow]"
        )


@app.command("stats")
def stats_cmd(
    db: str = typer.Argument(..., help="Path to SQLite database file"),
):
    """
    📊 Show cache statistics.
    """
    with get_service(db) as service:
        _stats_cmd_inner(service)


def _stats_cmd_inner(service: MaintenanceService):
    try:
        df = service.get_history(limit=10000)
    except ImportError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if df.empty:
        console.print("[yellow]No tasks recorded yet.[/yellow]")
        raise typer.Exit(0)

    total_tasks = len(df)
    if "func_identifier" in df.columns and df["func_identifier"].notna().any():  # type: ignore
        func_col = "func_identifier"
    else:
        func_col = "func_name"
    unique_functions = df[func_col].nunique()  # type: ignore
    result_types = df["result_type"].value_counts().to_dict()  # type: ignore
    content_types = df["content_type"].value_counts().to_dict()  # type: ignore

    summary = (
        f"[bold]Total Tasks:[/bold] [cyan]{total_tasks:,}[/cyan]\n"
        f"[bold]Unique Functions:[/bold] [cyan]{unique_functions}[/cyan]"
    )
    console.print(Panel(summary, title="📊 Overview", border_style="green"))

    if result_types:
        rt_table = Table(title="Result Types", border_style="blue")
        rt_table.add_column("Type", style="yellow")
        rt_table.add_column("Count", style="cyan", justify="right")
        for rt, count in result_types.items():
            rt_table.add_row(str(rt), str(count))
        console.print(rt_table)

    if content_types:
        ct_table = Table(title="Content Types", border_style="blue")
        ct_table.add_column("Type", style="blue")
        ct_table.add_column("Count", style="cyan", justify="right")
        for ct, count in content_types.items():
            # [FIX] Avoid pd.notna(ct) in conditional
            ct_str = str(ct) if ct else "-"
            ct_table.add_row(ct_str, str(count))
        console.print(ct_table)

    top_funcs = df[func_col].value_counts().head(10).to_dict()  # type: ignore
    if top_funcs:
        func_table = Table(title="Top Functions", border_style="blue")
        func_table.add_column("Function", style="cyan")
        func_table.add_column("Count", style="green", justify="right")
        for func_name, count in top_funcs.items():
            func_table.add_row(str(func_name), str(count))
        console.print(func_table)


@app.command("clear")
def clear_cmd(
    db: str = typer.Argument(..., help="Path to SQLite database file"),
    func: Optional[str] = typer.Option(
        None, "--func", "-f", help="Clear only specific function"
    ),
    force: bool = typer.Option(False, "--force", "-y", help="Skip confirmation"),
):
    """
    🗑️  Clear cached tasks.
    """
    if func:
        msg = f"Clear all cached tasks for function [cyan]{func}[/cyan]?"
    else:
        msg = "[bold red]Clear ALL cached tasks?[/bold red]"

    if not force:
        confirm = typer.confirm(msg)
        if not confirm:
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    with get_service(db) as service:
        deleted = service.clear(func)
    console.print(f"[green]✓ Deleted {deleted} tasks.[/green]")


@app.command("clean")
def clean_cmd(
    db: str = typer.Argument(..., help="Path to SQLite database file"),
    blob_dir: Optional[str] = typer.Option(
        None,
        "--blob-dir",
        "-b",
        help="Path to blob directory (auto-detected if not specified)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Show what would be deleted without actually deleting",
    ),
    force: bool = typer.Option(False, "--force", "-y", help="Skip confirmation"),
):
    """
    🧹 Clean orphaned blob files (garbage collection).

    Removes files in the storage directory that are NOT referenced by any task in the database.
    Use this to clean up leftover files after manual DB operations or errors.
    """
    with get_service(db, blob_dir) as service:
        _clean_cmd_inner(service, dry_run, force)


def _clean_cmd_inner(service: MaintenanceService, dry_run: bool, force: bool):
    orphans = service.scan_garbage()

    if not orphans:
        console.print(
            Panel(
                "[green]✓ No orphaned files found.[/green]",
                title="🧹 Clean",
                border_style="green",
            )
        )
        raise typer.Exit(0)

    table = Table(
        title=f"🧹 Orphaned Files ({len(orphans)} files)",
        show_header=True,
        header_style="bold magenta",
        border_style="yellow",
    )
    table.add_column("File", style="cyan")

    for orphan in orphans[:20]:
        table.add_row(Path(orphan).name)

    if len(orphans) > 20:
        table.add_row(f"... and {len(orphans) - 20} more files")

    console.print(table)

    if dry_run:
        console.print(
            f"\n[yellow]Dry run:[/yellow] Found {len(orphans)} orphaned files."
        )
        raise typer.Exit(0)

    if not force:
        confirm = typer.confirm(f"Delete {len(orphans)} orphaned files?")
        if not confirm:
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Cleaning garbage...", total=len(orphans))
        _, deleted_orphans = service.clean_garbage(orphans=orphans)
        progress.update(task, completed=len(orphans))

    console.print(f"[green]✓ Deleted {deleted_orphans} orphaned blob files.[/green]")


@app.command("gc")
def gc_cmd(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Show what would be deleted without actually deleting",
    ),
    force: bool = typer.Option(False, "--force", "-y", help="Skip confirmation"),
    expired: bool = typer.Option(
        True, "--expired/--no-expired", help="Remove expired tasks from DBs"
    ),
):
    """
    🗑️  Garbage Collect: Clean up expired tasks and orphan storage.

    Performs two types of cleanup:
    1. [bold]Expired Tasks[/bold]: Removes tasks where `expires_at < NOW` from all databases.
    2. [bold]Zombie Projects[/bold]: Removes blob directories that have no corresponding .db file.
    """
    workspace = Path(".beautyspot")
    if not workspace.exists():
        console.print("[yellow]No .beautyspot directory found.[/yellow]")
        raise typer.Exit(0)

    # --- 1. Expired Tasks Cleanup ---
    if expired:
        db_files = list(workspace.glob("**/*.db")) + list(workspace.glob("**/*.sqlite"))

        if db_files:
            console.print(
                f"[bold]Checking {len(db_files)} databases for expired tasks...[/bold]"
            )

            if dry_run:
                console.print(
                    "[yellow]Dry run:[/yellow] Would scan and remove expired tasks."
                )
            else:
                total_expired = 0
                for db_path in db_files:
                    try:
                        with get_service(str(db_path)) as service:
                            count = service.delete_expired_tasks()
                            if count > 0:
                                console.print(
                                    f"  [green]✓ {db_path.stem}: Removed {count} expired tasks[/green]"
                                )
                                total_expired += count
                    except Exception as e:
                        console.print(f"  [red]x {db_path.stem}: Error ({e})[/red]")

                if total_expired == 0:
                    console.print("  [dim]No expired tasks found.[/dim]")

            # --- 1.5. Per-project orphan blob cleanup ---
            console.print()
            console.print("[bold]Cleaning orphan blobs per project...[/bold]")

            total_orphan_blobs = 0
            for db_path in db_files:
                try:
                    with get_service(str(db_path)) as service:
                        # タスクが存在しないDBはスキップ
                        # (空DBに対して scan_garbage を走らせると、
                        #  全blobが孤立と誤判定される)
                        try:
                            df = service.get_history(limit=1)
                            if df.empty:
                                continue
                        except Exception:
                            continue

                        if dry_run:
                            orphan_blobs = service.scan_garbage()
                            if orphan_blobs:
                                console.print(
                                    f"  [yellow]{db_path.stem}: {len(orphan_blobs)} orphan blobs (dry run)[/yellow]"
                                )
                                total_orphan_blobs += len(orphan_blobs)
                        else:
                            _, deleted_blobs = service.clean_garbage()
                            if deleted_blobs > 0:
                                console.print(
                                    f"  [green]✓ {db_path.stem}: Removed {deleted_blobs} orphan blobs[/green]"
                                )
                                total_orphan_blobs += deleted_blobs
                except Exception as e:
                    console.print(f"  [red]x {db_path.stem}: Error ({e})[/red]")

            if total_orphan_blobs == 0:
                console.print("  [dim]No orphan blobs found.[/dim]")

    console.print()

    # --- 2. Zombie Projects Cleanup ---
    orphans = MaintenanceService.scan_orphan_projects(workspace)

    if not orphans:
        console.print(
            Panel(
                "[green]✓ No orphan storage directories found.[/green]",
                title="🗑️ Garbage Collection (Zombies)",
                border_style="green",
            )
        )
        raise typer.Exit(0)

    table = Table(
        title=f"Found {len(orphans)} orphan storage directories",
        show_header=False,
        box=None,
    )
    table.add_column("Path", style="red")

    for path in orphans:
        table.add_row(f"- {path}")

    console.print(table)
    console.print()

    if dry_run:
        console.print("[yellow]Dry run:[/yellow] No changes made to zombie projects.")
        raise typer.Exit(0)

    if not force:
        confirm = typer.confirm(f"Delete these {len(orphans)} directories?")
        if not confirm:
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    deleted_count = 0
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Cleaning up...", total=len(orphans))

        for path in orphans:
            try:
                MaintenanceService.delete_project_storage(path)
                deleted_count += 1
            except Exception:
                pass
            progress.advance(task)

    console.print(f"[green]✓ Cleaned up {deleted_count} orphan projects.[/green]")


@app.command("prune")
def prune_cmd(
    db: str = typer.Argument(..., help="Path to SQLite database file"),
    days: int = typer.Option(
        ..., "--days", "-d", help="Delete tasks older than N days"
    ),
    func: Optional[str] = typer.Option(
        None, "--func", "-f", help="Prune only specific function"
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Show what would be deleted without actually deleting",
    ),
    force: bool = typer.Option(False, "--force", "-y", help="Skip confirmation"),
    clean_blobs: bool = typer.Option(
        True,
        "--clean-blobs/--no-clean-blobs",
        help="Also remove orphaned blob files after pruning",
    ),
):
    """
    🗓️  Prune old cached tasks (time-based expiration).

    Deletes task records older than the specified number of days.
    By default, it also removes the associated blob files (implied --clean-blobs).
    """
    if days < 1:
        console.print("[red]Error:[/red] --days must be at least 1")
        raise typer.Exit(1)

    with get_service(db) as service:
        _prune_cmd_inner(service, days, func, dry_run, force, clean_blobs)


def _prune_cmd_inner(
    service: MaintenanceService,
    days: int,
    func: Optional[str],
    dry_run: bool,
    force: bool,
    clean_blobs: bool,
):
    tasks_to_delete = service.get_prunable_tasks(days, func)

    if not tasks_to_delete:
        target_msg = f" for function '{func}'" if func else ""
        console.print(
            Panel(
                f"[green]✓ No tasks older than {days} days{target_msg}.[/green]",
                title="🗓️ Prune",
                border_style="green",
            )
        )
        raise typer.Exit(0)

    table = Table(
        title=f"🗓️ Tasks to Prune ({len(tasks_to_delete)} tasks)",
        show_header=True,
        header_style="bold magenta",
        border_style="yellow",
    )
    table.add_column("Function", style="cyan")
    table.add_column("Cache Key", style="dim", max_width=20)
    table.add_column("Updated", style="yellow")

    for cache_key, func_name, updated_at in tasks_to_delete[:15]:
        table.add_row(
            str(func_name),
            str(cache_key)[:20] + "..." if len(str(cache_key)) > 20 else str(cache_key),
            str(updated_at),
        )

    if len(tasks_to_delete) > 15:
        table.add_row(
            f"[dim]... and {len(tasks_to_delete) - 15} more tasks[/dim]",
            "",
            "",
        )

    console.print(table)

    if dry_run:
        console.print(
            f"\n[yellow]Dry run:[/yellow] Would delete {len(tasks_to_delete)} tasks"
        )
        raise typer.Exit(0)

    if not force:
        confirm = typer.confirm(f"Delete {len(tasks_to_delete)} tasks?")
        if not confirm:
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    deleted = service.prune(days, func)
    console.print(f"[green]✓ Deleted {deleted} tasks.[/green]")

    if clean_blobs:
        console.print("\n[dim]Running blob cleanup...[/dim]")

        orphans = service.scan_garbage()
        if orphans:
            _, deleted_orphans = service.clean_garbage(orphans)
            console.print(
                f"[green]✓ Deleted {deleted_orphans} orphaned blob files.[/green]"
            )
        else:
            console.print("[green]✓ No orphaned blob files found.[/green]")


@app.command("version")
def version_cmd():
    """
    ℹ️  Show version information.
    """
    try:
        from beautyspot import __version__
    except ImportError:
        __version__ = "unknown"

    console.print(
        Panel.fit(
            f"[bold]beautyspot[/bold] version [cyan]{__version__}[/cyan]\n\n"
            "[dim]Intelligent caching for ML pipelines[/dim]",
            title="🌑",
            border_style="blue",
        )
    )


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
