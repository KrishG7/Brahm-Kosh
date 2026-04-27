import os
import shutil
import tempfile
import subprocess
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from brahm_kosh.engine import analyze

console = Console()

def run_diff(path: str, ref: str, lang: Optional[str] = None):
    """Compare the current project state against a specific git reference."""
    abs_path = Path(path).resolve()
    
    # Ensure it's a git repository
    if not (abs_path / ".git").exists():
        console.print(f"[bold red]Error:[/bold red] '{path}' is not a git repository. Diff requires git.")
        return

    console.print(f"[bold bright_cyan]Comparing HEAD to {ref}...[/bold bright_cyan]")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        try:
            # Archive the target ref into the temp directory
            with console.status(f"[cyan]Checking out {ref} to temporary directory...[/cyan]"):
                # Use git archive to export the state of the ref without touching the working tree
                archive_cmd = f"git archive {ref} | tar -x -C {temp_dir}"
                result = subprocess.run(archive_cmd, shell=True, cwd=abs_path, capture_output=True, text=True)
                if result.returncode != 0:
                    console.print(f"[bold red]Error checking out {ref}:[/bold red] {result.stderr}")
                    return

            # Analyze the OLD state
            with console.status(f"[cyan]Analyzing codebase at {ref}...[/cyan]", spinner="dots"):
                old_project, _ = analyze(str(temp_path), top_n=10, lang=lang)
                
            # Analyze the NEW state (current)
            with console.status("[cyan]Analyzing current codebase...[/cyan]", spinner="dots"):
                new_project, _ = analyze(str(abs_path), top_n=10, lang=lang)
                
        except Exception as e:
            console.print(f"[bold red]Error during analysis:[/bold red] {str(e)}")
            return

    _print_diff_report(old_project, new_project)

def _print_diff_report(old_project, new_project):
    """Compare two Project objects and print the delta."""
    old_files = {f.relative_path: f for f in old_project.all_files()}
    new_files = {f.relative_path: f for f in new_project.all_files()}
    
    all_paths = set(old_files.keys()).union(new_files.keys())
    
    changes = []
    
    for path in all_paths:
        old_f = old_files.get(path)
        new_f = new_files.get(path)
        
        if not old_f:
            changes.append({
                "path": path,
                "status": "ADDED",
                "complexity_delta": new_f.complexity,
                "new_complexity": new_f.complexity
            })
        elif not new_f:
            changes.append({
                "path": path,
                "status": "DELETED",
                "complexity_delta": -old_f.complexity,
                "new_complexity": 0
            })
        else:
            delta = new_f.complexity - old_f.complexity
            # Only track if there was a meaningful change
            if abs(delta) > 0.5:
                changes.append({
                    "path": path,
                    "status": "MODIFIED",
                    "complexity_delta": delta,
                    "new_complexity": new_f.complexity
                })
                
    # Sort changes by absolute impact (highest first)
    changes.sort(key=lambda x: abs(x["complexity_delta"]), reverse=True)
    
    if not changes:
        console.print(Panel("[green]No meaningful architectural changes detected.[/green]", border_style="green"))
        return
        
    table = Table(
        title="[bold bright_cyan]📈 Architectural Diff[/bold bright_cyan]",
        border_style="bright_cyan",
        show_lines=True,
        title_style="bold bright_cyan"
    )
    
    table.add_column("Status", justify="center", width=10)
    table.add_column("File", style="white", min_width=30)
    table.add_column("Complexity Delta", justify="right", width=18)
    table.add_column("New Score", justify="right", style="dim", width=10)
    
    for change in changes:
        status = change["status"]
        if status == "ADDED":
            status_tag = "[green]+ ADDED[/green]"
        elif status == "DELETED":
            status_tag = "[red]- DELETED[/red]"
        else:
            status_tag = "[yellow]~ MODIFIED[/yellow]"
            
        delta = change["complexity_delta"]
        if delta > 0:
            delta_str = f"[bold red]+{delta:.1f} 🔴[/bold red]"
        else:
            delta_str = f"[bold green]{delta:.1f} 🟢[/bold green]"
            
        table.add_row(
            status_tag,
            change["path"],
            delta_str,
            f"{change['new_complexity']:.1f}" if status != "DELETED" else "-"
        )
        
    console.print()
    console.print(table)
    
    # Summary
    total_added = sum(1 for c in changes if c["status"] == "ADDED")
    total_deleted = sum(1 for c in changes if c["status"] == "DELETED")
    total_worse = sum(1 for c in changes if c["status"] == "MODIFIED" and c["complexity_delta"] > 0)
    total_better = sum(1 for c in changes if c["status"] == "MODIFIED" and c["complexity_delta"] < 0)
    
    summary = (
        f"[bold]Diff Summary:[/bold]\n"
        f"Files Added: [green]{total_added}[/green] | Files Deleted: [red]{total_deleted}[/red]\n"
        f"Got Worse: [red]{total_worse}[/red] files | Got Better: [green]{total_better}[/green] files"
    )
    console.print(Panel(summary, border_style="dim"))