# src/beautyspot/cli.py

import sys
import socket
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

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
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime("%Y-%m-%d %H:%M")


def _get_task_count(db_path: Path) -> int:
    """
    Get task count.
    Note: Ideally we should use Spot to query this, but creating Spot
    for just listing databases might be heavy. Keeping simple sqlite3 check here
    is acceptable for `list_databases` discovery, OR we can instantiate Spot.
    For consistency with removing deps, let's try to instantiate Spot if cheap,
    OR keep this isolated helper.
    Since `list_databases` scans many files, instantiating Spot for each is slow.
    Let's use a minimal sqlite3 connection here, AS AN EXCEPTION for performance,
    OR just show '-' if we strictly want to avoid sqlite3 import in CLI.
    
    Strictly speaking, the user asked to remove direct dependency on `db`, `storage`, `serializer`.
    `sqlite3` is a standard library.
    If we want to be strict, we can remove `_get_task_count` or make it use Spot.
    Let's try to use Spot.from_path but simpler? No, Spot initializes schema etc.
    
    Let's keep `sqlite3` here as it's a file format checker, not a dependency on our internal `SQLiteTaskDB` class.
    """
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM tasks")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return -1


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
    spot = get_service(db)
    # Using spot.db (TaskDB interface) instead of SQLiteTaskDB
    df = spot.db.get_history(limit=limit)

    if df.empty:
        console.print("[yellow]No tasks recorded yet.[/yellow]")
        raise typer.Exit(0)

    if func:
        df = df[df["func_name"].str.contains(func, na=False)]  # type: ignore[union-attr]
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
    table.add_column("Input ID", style="dim", max_width=20)
    table.add_column("Version", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Content", style="blue")
    table.add_column("Updated", style="dim")

    for _, row in df.iterrows():
        input_id = (
            str(row["input_id"])[:20] + "..."
            if len(str(row["input_id"])) > 20
            else str(row["input_id"])
        )
        table.add_row(
            str(row["func_name"]),
            input_id,
            str(row["version"] or "-"),
            str(row["result_type"]),
            str(row["content_type"] or "-"),
            str(row["updated_at"]),
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
    cache_key: str = typer.Argument(..., help="Cache key to inspect"),
):
    """
    🔍 Show details of a specific cached task.
    """
    # 1. サービスを取得 (Spotインスタンスは不要)
    service = get_service(db)
    
    # 2. 詳細を取得
    # get_task_detail は DBレコードに加え、復元に成功すれば 'decoded_data' を含んで返す
    result = service.get_task_detail(cache_key)

    if result is None:
        console.print(f"[red]Error:[/red] Cache key not found: {cache_key}")
        raise typer.Exit(1)

    # 3. メタデータの表示
    detail_text = (
        f"[bold]Cache Key:[/bold] [cyan]{cache_key}[/cyan]\n"
        f"[bold]Result Type:[/bold] [yellow]{result.get('result_type')}[/yellow]\n"
        f"[bold]Result Value:[/bold] {result.get('result_value') or '-'}\n"
        f"[bold]Has Blob Data:[/bold] {'Yes' if result.get('result_data') else 'No'}"
    )

    console.print(
        Panel(
            detail_text,
            title="🔍 Task Details",
            border_style="green",
        )
    )

    # 4. データの中身（デコード済み）の表示
    # Service側ですでにデシリアライズされているので、ここでは表示方法だけを考える
    data = result.get("decoded_data")

    if data is not None:
        try:
            import json
            
            if isinstance(data, (dict, list)):
                # JSONとして綺麗に表示
                json_str = json.dumps(data, indent=2, ensure_ascii=False, default=str)
                syntax = Syntax(json_str, "json", theme="monokai", line_numbers=True)
                console.print(
                    Panel(syntax, title="📦 Data Preview (JSON)", border_style="blue")
                )
            elif isinstance(data, str):
                # 長すぎる文字列は省略して表示
                preview = data[:1000] + "..." if len(data) > 1000 else data
                console.print(
                    Panel(
                        preview, title="📦 Data Preview (String)", border_style="blue"
                    )
                )
            else:
                # その他のオブジェクト
                console.print(
                    Panel(
                        f"[dim]Type: {type(data).__name__}[/dim]\n{str(data)[:1000]}",
                        title="📦 Data Preview (Object)",
                        border_style="blue"
                    )
                )

        except Exception as e:
            console.print(f"[yellow]Error displaying data: {e}[/yellow]")

    # データが存在するはずだが、デコードに失敗している場合 (decoded_data が None)
    elif result.get("result_data") is not None or (
        result.get("result_type") == "FILE" and result.get("result_value")
    ):
        console.print("[yellow]Could not decode blob data (Serialization format mismatch or missing file).[/yellow]")


@app.command("stats")
def stats_cmd(
    db: str = typer.Argument(..., help="Path to SQLite database file"),
):
    """
    📊 Show cache statistics.
    """
    service = get_service(db)
    
    # Check for pandas presence is handled inside TaskDB.get_history or here
    # TaskDB.get_history raises ImportError if pandas is missing, so we can wrap it.
    try:
        import pandas as pd
    except ImportError:
        console.print(
            "[red]Error:[/red] pandas is required. Install with: pip install pandas"
        )
        raise typer.Exit(1)

    try:
        df = service.get_history(limit=10000)
    except ImportError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if df.empty:
        console.print("[yellow]No tasks recorded yet.[/yellow]")
        raise typer.Exit(0)

    total_tasks = len(df)
    unique_functions = df["func_name"].nunique()  # type: ignore[union-attr]
    result_types = df["result_type"].value_counts().to_dict()  # type: ignore[union-attr]
    content_types = df["content_type"].value_counts().to_dict()  # type: ignore[union-attr]

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
            ct_table.add_row(str(ct) if pd.notna(ct) else "-", str(count))
        console.print(ct_table)

    top_funcs = df["func_name"].value_counts().head(10).to_dict()  # type: ignore[union-attr]
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

    service = get_service(db)
    
    # Use the new clear method in MaintenanceService
    # This delegates to prune with a future date, avoiding direct sqlite3 usage here
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

    [bold]Note:[/bold] This command is designed primarily for the standard directory structure.
    If you are using custom storage paths or backends (e.g. S3), please ensure
    you explicitly verify the target with [cyan]--dry-run[/cyan] before deletion.
    """
    service = get_service(db, blob_dir)
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
        count, _ = service.clean_garbage(orphans=orphans)
        progress.update(task, completed=len(orphans))

    console.print(f"[green]✓ Deleted {count} orphaned blob files.[/green]")


# src/beautyspot/cli.py

# ... (既存のimport) ...

@app.command("gc")
def gc_cmd(
    all: bool = typer.Option(
        False, "--all", help="Scan all projects (currently the only mode)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Show what would be deleted without actually deleting"
    ),
    force: bool = typer.Option(False, "--force", "-y", help="Skip confirmation"),
    expired: bool = typer.Option(True, "--expired/--no-expired"),
):
    """
    🗑️  Garbage Collect: Remove 'zombie' blob directories with no matching DB.

    Scans the [bold].beautyspot/blobs/[/bold] directory for folders that do NOT have a 
    corresponding [bold].db[/bold] file in the workspace.
    
    Use this when you have manually deleted a .db file but the blob directory remains.
    
    Checks [bold].beautyspot/blobs/[/bold] for directories that do not have a corresponding
    [bold].db[/bold] file in [bold].beautyspot/[/bold].
    """
    workspace = Path(".beautyspot")
    if not workspace.exists():
         console.print("[yellow]No .beautyspot directory found.[/yellow]")
         raise typer.Exit(0)

    # 1. ゾンビプロジェクトのスキャン
    orphans = MaintenanceService.scan_orphan_projects(workspace)

    if not orphans:
        console.print(
            Panel(
                "[green]✓ No orphan storage directories found.[/green]",
                title="🗑️ Garbage Collection",
                border_style="green",
            )
        )
        raise typer.Exit(0)

    # 2. 結果の表示
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
        console.print("[yellow]Dry run:[/yellow] No changes made.")
        raise typer.Exit(0)

    # 3. 確認と削除
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
                pass # エラーログはService側で出る
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

    service = get_service(db)
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
            c, _ = service.clean_garbage(orphans)
            console.print(f"[green]✓ Deleted {c} orphaned blob files.[/green]")
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

