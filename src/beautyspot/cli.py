# src/beautyspot/cli.py

import sqlite3
import subprocess
import sys
import socket
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn

from beautyspot.db import SQLiteTaskDB

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

def get_db(db_path: str) -> SQLiteTaskDB:
    """Validate and return a database instance."""
    path = Path(db_path)
    if not path.exists():
        console.print(f"[red]Error:[/red] Database not found: {db_path}")
        raise typer.Exit(1)
    return SQLiteTaskDB(db_path)


def _is_port_in_use(port: int) -> bool:
    """Check if a port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


def _find_available_port(start_port: int, max_attempts: int = 10) -> int:
    """Find an available port starting from start_port."""
    for i in range(max_attempts):
        port = start_port + i
        if not _is_port_in_use(port):
            return port
    raise RuntimeError(f"No available port found in range {start_port}-{start_port + max_attempts - 1}")


def _format_size(size_bytes: int | float) -> str:
    """Format file size in human-readable format."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _format_timestamp(timestamp: float) -> str:
    """Format timestamp in human-readable format."""
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime("%Y-%m-%d %H:%M")


def _get_task_count(db_path: Path) -> int:
    """Get the number of tasks in a database."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM tasks")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return -1


def _infer_blob_dir(db_path: Path) -> Path | None:
    """Infer blob directory from database path."""
    # 一般的なパターン: .beautyspot/project.db -> .beautyspot/project/blobs/
    # または: .beautyspot/tasks.db -> .beautyspot/blobs/
    parent = db_path.parent
    stem = db_path.stem
    
    # パターン1: .beautyspot/<name>/blobs/
    candidate1 = parent / stem / "blobs"
    if candidate1.exists():
        return candidate1
    
    # パターン2: .beautyspot/blobs/
    candidate2 = parent / "blobs"
    if candidate2.exists():
        return candidate2
    
    return None


# =============================================================================
# Commands
# =============================================================================

@app.command("ui")
def ui_cmd(
    db: str = typer.Argument(..., help="Path to SQLite database file"),
    port: int = typer.Option(8501, "--port", "-p", help="Streamlit server port"),
    auto_port: bool = typer.Option(True, "--auto-port/--no-auto-port", help="Auto-find available port"),
):
    """
    🚀 Launch the interactive dashboard.
    
    Example:
        beautyspot ui ./cache/tasks.db
        beautyspot ui ./cache/tasks.db --port 8080
        beautyspot ui ./cache/tasks.db --no-auto-port
    """
    db_path = Path(db)
    if not db_path.exists():
        console.print(f"[red]Error:[/red] Database not found: {db}")
        raise typer.Exit(1)

    # ポートの確認と自動選択
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
                console.print(
                    "\n[dim]Hint: Kill existing process or specify a different port:[/dim]\n"
                    f"  lsof -i :{port}          # Find process using port\n"
                    f"  kill <PID>               # Kill the process\n"
                    f"  beautyspot ui {db} -p 8080  # Use different port"
                )
                raise typer.Exit(1)
        else:
            console.print(
                f"[red]Error:[/red] Port {port} is already in use.\n\n"
                "[dim]Hint: Kill existing process or specify a different port:[/dim]\n"
                f"  lsof -i :{port}          # Find process using port\n"
                f"  kill <PID>               # Kill the process\n"
                f"  beautyspot ui {db} -p 8080  # Use different port\n"
                f"  beautyspot ui {db}          # Auto-find available port"
            )
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

    # Streamlit の dashboard.py へのパスを取得
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
    func: Optional[str] = typer.Option(None, "--func", "-f", help="Filter by function name"),
):
    """
    📋 List cached tasks or available databases.
    
    If no database is specified, lists SQLite files in .beautyspot/ directory.
    
    Example:
        beautyspot list                           # List available databases
        beautyspot list ./cache/tasks.db          # List tasks in database
        beautyspot list ./cache/tasks.db -n 50    # Limit to 50 records
        beautyspot list ./cache/tasks.db -f func  # Filter by function name
    """
    # 引数なしの場合: .beautyspot/ 内のDBファイルをリスト
    if db is None:
        _list_databases()
        return

    # DB指定ありの場合: 既存の挙動
    _list_tasks(db, limit, func)


def _list_databases():
    """List available SQLite database files in .beautyspot/ directory."""
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

    # SQLite ファイルを検索
    db_files = list(beautyspot_dir.glob("**/*.db")) + list(beautyspot_dir.glob("**/*.sqlite"))

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

    # テーブル作成
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
        # ファイル情報
        stat = db_path.stat()
        size = _format_size(stat.st_size)
        modified = _format_timestamp(stat.st_mtime)

        # タスク数を取得
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
    """List tasks in a specific database."""
    task_db = get_db(db)

    try:
        import pandas as pd
    except ImportError:
        console.print("[red]Error:[/red] pandas is required. Install with: pip install pandas")
        raise typer.Exit(1)

    df = task_db.get_history(limit=limit)

    if df.empty:
        console.print("[yellow]No tasks recorded yet.[/yellow]")
        raise typer.Exit(0)

    # Filter by function name if specified
    if func:
        df = df[df["func_name"].str.contains(func, na=False)]  # type: ignore[union-attr]
        if df.empty:
            console.print(f"[yellow]No tasks found for function: {func}[/yellow]")
            raise typer.Exit(0)

    # Create rich table
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
        input_id = str(row["input_id"])[:20] + "..." if len(str(row["input_id"])) > 20 else str(row["input_id"])
        table.add_row(
            str(row["func_name"]),
            input_id,
            str(row["version"] or "-"),
            str(row["result_type"]),
            str(row["content_type"] or "-"),
            str(row["updated_at"]),
        )

    console.print(table)


@app.command("show")
def show_cmd(
    db: str = typer.Argument(..., help="Path to SQLite database file"),
    cache_key: str = typer.Argument(..., help="Cache key to inspect"),
):
    """
    🔍 Show details of a specific cached task.
    
    Example:
        beautyspot show ./cache/tasks.db abc123def456
    """
    task_db = get_db(db)
    result = task_db.get(cache_key)

    if result is None:
        console.print(f"[red]Error:[/red] Cache key not found: {cache_key}")
        raise typer.Exit(1)

    # Create detail panel
    detail_text = (
        f"[bold]Cache Key:[/bold] [cyan]{cache_key}[/cyan]\n"
        f"[bold]Result Type:[/bold] [yellow]{result['result_type']}[/yellow]\n"
        f"[bold]Result Value:[/bold] {result['result_value'] or '-'}\n"
        f"[bold]Has Blob Data:[/bold] {'Yes' if result['result_data'] else 'No'}"
    )

    console.print(
        Panel(
            detail_text,
            title="🔍 Task Details",
            border_style="green",
        )
    )

    # Show preview of blob data if available
    if result["result_data"]:
        try:
            import msgpack

            data = msgpack.unpackb(result["result_data"], raw=False)

            if isinstance(data, dict):
                import json

                json_str = json.dumps(data, indent=2, ensure_ascii=False, default=str)
                syntax = Syntax(json_str, "json", theme="monokai", line_numbers=True)
                console.print(Panel(syntax, title="📦 Data Preview (JSON)", border_style="blue"))
            elif isinstance(data, str):
                # Truncate long strings
                preview = data[:1000] + "..." if len(data) > 1000 else data
                console.print(Panel(preview, title="📦 Data Preview (String)", border_style="blue"))
            else:
                console.print(f"[dim]Data type: {type(data).__name__}[/dim]")
        except Exception as e:
            console.print(f"[yellow]Could not decode blob data: {e}[/yellow]")


@app.command("stats")
def stats_cmd(
    db: str = typer.Argument(..., help="Path to SQLite database file"),
):
    """
    📊 Show cache statistics.
    
    Example:
        beautyspot stats ./cache/tasks.db
    """
    task_db = get_db(db)

    try:
        import pandas as pd
    except ImportError:
        console.print("[red]Error:[/red] pandas is required. Install with: pip install pandas")
        raise typer.Exit(1)

    df = task_db.get_history(limit=10000)

    if df.empty:
        console.print("[yellow]No tasks recorded yet.[/yellow]")
        raise typer.Exit(0)

    # Statistics
    total_tasks = len(df)
    unique_functions = df["func_name"].nunique()  # type: ignore[union-attr]
    result_types = df["result_type"].value_counts().to_dict()  # type: ignore[union-attr]
    content_types = df["content_type"].value_counts().to_dict()  # type: ignore[union-attr]

    # Summary panel
    summary = (
        f"[bold]Total Tasks:[/bold] [cyan]{total_tasks:,}[/cyan]\n"
        f"[bold]Unique Functions:[/bold] [cyan]{unique_functions}[/cyan]"
    )
    console.print(Panel(summary, title="📊 Overview", border_style="green"))

    # Result types table
    if result_types:
        rt_table = Table(title="Result Types", border_style="blue")
        rt_table.add_column("Type", style="yellow")
        rt_table.add_column("Count", style="cyan", justify="right")
        for rt, count in result_types.items():
            rt_table.add_row(str(rt), str(count))
        console.print(rt_table)

    # Content types table
    if content_types:
        ct_table = Table(title="Content Types", border_style="blue")
        ct_table.add_column("Type", style="blue")
        ct_table.add_column("Count", style="cyan", justify="right")
        for ct, count in content_types.items():
            ct_table.add_row(str(ct) if pd.notna(ct) else "-", str(count))
        console.print(ct_table)

    # Top functions
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
    func: Optional[str] = typer.Option(None, "--func", "-f", help="Clear only specific function"),
    force: bool = typer.Option(False, "--force", "-y", help="Skip confirmation"),
):
    """
    🗑️  Clear cached tasks.
    
    Example:
        beautyspot clear ./cache/tasks.db
        beautyspot clear ./cache/tasks.db --func my_function
        beautyspot clear ./cache/tasks.db --force
    """
    db_path = Path(db)
    if not db_path.exists():
        console.print(f"[red]Error:[/red] Database not found: {db}")
        raise typer.Exit(1)

    # Confirmation
    if func:
        msg = f"Clear all cached tasks for function [cyan]{func}[/cyan]?"
    else:
        msg = "[bold red]Clear ALL cached tasks?[/bold red]"

    if not force:
        confirm = typer.confirm(msg)
        if not confirm:
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    # Execute deletion
    conn = sqlite3.connect(db)
    try:
        if func:
            cursor = conn.execute("DELETE FROM tasks WHERE func_name = ?", (func,))
        else:
            cursor = conn.execute("DELETE FROM tasks")
        deleted = cursor.rowcount
        conn.commit()
        console.print(f"[green]✓ Deleted {deleted} tasks.[/green]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        conn.close()


@app.command("clean")
def clean_cmd(
    db: str = typer.Argument(..., help="Path to SQLite database file"),
    blob_dir: Optional[str] = typer.Option(None, "--blob-dir", "-b", help="Path to blob directory (auto-detected if not specified)"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be deleted without actually deleting"),
    force: bool = typer.Option(False, "--force", "-y", help="Skip confirmation"),
):
    """
    🧹 Clean orphaned blob files (garbage collection).
    
    Removes blob files that are not referenced in the database.
    This can happen when tasks are deleted but their blob files remain.
    
    Example:
        beautyspot clean ./cache/tasks.db                    # Auto-detect blob dir
        beautyspot clean ./cache/tasks.db -b ./cache/blobs   # Specify blob dir
        beautyspot clean ./cache/tasks.db --dry-run          # Preview only
        beautyspot clean ./cache/tasks.db --force            # Skip confirmation
    """
    db_path = Path(db)
    if not db_path.exists():
        console.print(f"[red]Error:[/red] Database not found: {db}")
        raise typer.Exit(1)

    # Blob ディレクトリの決定
    if blob_dir:
        blobs_path = Path(blob_dir)
    else:
        blobs_path = _infer_blob_dir(db_path)
    
    if blobs_path is None or not blobs_path.exists():
        console.print(
            Panel(
                "[yellow]No blob directory found.[/yellow]\n\n"
                "[dim]Hint: Specify the blob directory manually:[/dim]\n"
                f"  beautyspot clean {db} --blob-dir ./path/to/blobs",
                title="🧹 Clean",
                border_style="yellow",
            )
        )
        raise typer.Exit(0)

    console.print(f"[dim]Blob directory: {blobs_path}[/dim]\n")

    # DB から参照されている blob ファイルのリストを取得
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            "SELECT result_value FROM tasks WHERE result_type = 'FILE' AND result_value IS NOT NULL"
        )
        referenced_files = {Path(row[0]).name for row in cursor.fetchall() if row[0]}
    finally:
        conn.close()

    # Blob ディレクトリ内のファイルをスキャン
    all_blob_files = list(blobs_path.glob("*.bin"))
    
    # 孤立ファイルを特定
    orphaned_files: list[Path] = []
    for blob_file in all_blob_files:
        if blob_file.name not in referenced_files:
            orphaned_files.append(blob_file)

    if not orphaned_files:
        console.print(
            Panel(
                "[green]✓ No orphaned files found.[/green]\n\n"
                f"[dim]Scanned {len(all_blob_files)} blob files.[/dim]",
                title="🧹 Clean",
                border_style="green",
            )
        )
        raise typer.Exit(0)

    # 孤立ファイルの情報を表示
    total_size = sum(f.stat().st_size for f in orphaned_files)
    
    table = Table(
        title=f"🧹 Orphaned Files ({len(orphaned_files)} files, {_format_size(total_size)})",
        show_header=True,
        header_style="bold magenta",
        border_style="yellow",
    )
    table.add_column("File", style="cyan")
    table.add_column("Size", style="green", justify="right")
    table.add_column("Modified", style="dim")

    for f in orphaned_files[:20]:  # 最大20件表示
        stat = f.stat()
        table.add_row(
            f.name,
            _format_size(stat.st_size),
            _format_timestamp(stat.st_mtime),
        )
    
    if len(orphaned_files) > 20:
        table.add_row(
            f"[dim]... and {len(orphaned_files) - 20} more files[/dim]",
            "",
            "",
        )

    console.print(table)

    if dry_run:
        console.print(
            f"\n[yellow]Dry run:[/yellow] Would delete {len(orphaned_files)} files "
            f"({_format_size(total_size)})"
        )
        raise typer.Exit(0)

    # 確認
    if not force:
        confirm = typer.confirm(
            f"Delete {len(orphaned_files)} orphaned files ({_format_size(total_size)})?"
        )
        if not confirm:
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    # 削除実行
    deleted_count = 0
    deleted_size = 0
    errors: list[str] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Deleting orphaned files...", total=len(orphaned_files))
        
        for f in orphaned_files:
            try:
                size = f.stat().st_size
                f.unlink()
                deleted_count += 1
                deleted_size += size
            except Exception as e:
                errors.append(f"{f.name}: {e}")
            progress.advance(task)

    # 結果表示
    console.print(
        f"\n[green]✓ Deleted {deleted_count} files ({_format_size(deleted_size)})[/green]"
    )
    
    if errors:
        console.print(f"\n[yellow]Warnings ({len(errors)} errors):[/yellow]")
        for err in errors[:5]:
            console.print(f"  [dim]{err}[/dim]")
        if len(errors) > 5:
            console.print(f"  [dim]... and {len(errors) - 5} more errors[/dim]")


@app.command("prune")
def prune_cmd(
    db: str = typer.Argument(..., help="Path to SQLite database file"),
    days: int = typer.Option(..., "--days", "-d", help="Delete tasks older than N days"),
    func: Optional[str] = typer.Option(None, "--func", "-f", help="Prune only specific function"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be deleted without actually deleting"),
    force: bool = typer.Option(False, "--force", "-y", help="Skip confirmation"),
    clean_blobs: bool = typer.Option(True, "--clean-blobs/--no-clean-blobs", help="Also remove orphaned blob files after pruning"),
):
    """
    🗓️  Prune old cached tasks.
    
    Deletes tasks that haven't been updated for more than N days.
    Optionally cleans up orphaned blob files after pruning.
    
    Example:
        beautyspot prune ./cache/tasks.db --days 30           # Delete tasks older than 30 days
        beautyspot prune ./cache/tasks.db -d 7 -f my_func     # Prune specific function
        beautyspot prune ./cache/tasks.db -d 90 --dry-run     # Preview only
        beautyspot prune ./cache/tasks.db -d 30 --force       # Skip confirmation
        beautyspot prune ./cache/tasks.db -d 30 --no-clean-blobs  # Don't clean blob files
    """
    db_path = Path(db)
    if not db_path.exists():
        console.print(f"[red]Error:[/red] Database not found: {db}")
        raise typer.Exit(1)

    if days < 1:
        console.print("[red]Error:[/red] --days must be at least 1")
        raise typer.Exit(1)

    # カットオフ日時を計算
    cutoff_date = datetime.now() - timedelta(days=days)
    cutoff_str = cutoff_date.strftime("%Y-%m-%d %H:%M:%S")

    console.print(f"[dim]Cutoff date: {cutoff_date.strftime('%Y-%m-%d %H:%M')} ({days} days ago)[/dim]\n")

    # 削除対象のタスクを取得
    conn = sqlite3.connect(db_path)
    try:
        if func:
            cursor = conn.execute(
                "SELECT cache_key, func_name, updated_at FROM tasks "
                "WHERE updated_at < ? AND func_name = ? ORDER BY updated_at",
                (cutoff_str, func),
            )
        else:
            cursor = conn.execute(
                "SELECT cache_key, func_name, updated_at FROM tasks "
                "WHERE updated_at < ? ORDER BY updated_at",
                (cutoff_str,),
            )
        
        tasks_to_delete = cursor.fetchall()
    finally:
        conn.close()

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

    # 削除対象のサマリを表示
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
        console.print(f"\n[yellow]Dry run:[/yellow] Would delete {len(tasks_to_delete)} tasks")
        raise typer.Exit(0)

    # 確認
    if not force:
        confirm = typer.confirm(f"Delete {len(tasks_to_delete)} tasks?")
        if not confirm:
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    # 削除実行
    conn = sqlite3.connect(db_path)
    try:
        if func:
            cursor = conn.execute(
                "DELETE FROM tasks WHERE updated_at < ? AND func_name = ?",
                (cutoff_str, func),
            )
        else:
            cursor = conn.execute(
                "DELETE FROM tasks WHERE updated_at < ?",
                (cutoff_str,),
            )
        deleted = cursor.rowcount
        conn.commit()
    finally:
        conn.close()

    console.print(f"\n[green]✓ Deleted {deleted} tasks.[/green]")

    # Blob ファイルのクリーンアップ
    if clean_blobs:
        console.print("\n[dim]Running blob cleanup...[/dim]")
        blob_dir = _infer_blob_dir(db_path)
        if blob_dir and blob_dir.exists():
            # clean コマンドの内部ロジックを再利用（force=True, dry_run=False）
            _clean_orphaned_blobs(db_path, blob_dir, verbose=False)
        else:
            console.print("[dim]No blob directory found, skipping blob cleanup.[/dim]")


def _clean_orphaned_blobs(db_path: Path, blobs_path: Path, verbose: bool = True) -> int:
    """Internal helper to clean orphaned blob files."""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            "SELECT result_value FROM tasks WHERE result_type = 'FILE' AND result_value IS NOT NULL"
        )
        referenced_files = {Path(row[0]).name for row in cursor.fetchall() if row[0]}
    finally:
        conn.close()

    all_blob_files = list(blobs_path.glob("*.bin"))
    orphaned_files = [f for f in all_blob_files if f.name not in referenced_files]

    if not orphaned_files:
        if verbose:
            console.print("[green]✓ No orphaned blob files found.[/green]")
        return 0

    deleted_count = 0
    deleted_size = 0

    for f in orphaned_files:
        try:
            size = f.stat().st_size
            f.unlink()
            deleted_count += 1
            deleted_size += size
        except Exception:
            pass

    console.print(
        f"[green]✓ Cleaned {deleted_count} orphaned blob files ({_format_size(deleted_size)})[/green]"
    )
    return deleted_count


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

