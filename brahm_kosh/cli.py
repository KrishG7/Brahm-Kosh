"""
Brahm-Kosh CLI — The Interface.

Beautiful terminal output powered by Rich.
"""

from __future__ import annotations

import json
import time

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from brahm_kosh import __version__
from brahm_kosh.adapters.registry import list_adapters
from brahm_kosh.engine import analyze
from brahm_kosh.models import FileModel, Module


console = Console()


BANNER = r"""
 ____            _                    _  __         _
| __ ) _ __ __ _| |__  _ __ ___      | |/ /___  ___| |__
|  _ \| '__/ _` | '_ \| '_ ` _ \ ____| ' // _ \/ __| '_ \
| |_) | | | (_| | | | | | | | | |____|  < (_) \__ \ | | |
|____/|_|  \__,_|_| |_|_| |_| |_|    |_|\_\___/|___/_| |_|
"""


def _complexity_badge(score: float) -> str:
    """Get a colored complexity badge."""
    if score >= 80:
        return f"[bold red]🔴 {score:.0f}[/bold red]"
    elif score >= 60:
        return f"[bold yellow]🟠 {score:.0f}[/bold yellow]"
    elif score >= 40:
        return f"[yellow]🟡 {score:.0f}[/yellow]"
    else:
        return f"[green]🟢 {score:.0f}[/green]"


def _heat_emoji(score: float) -> str:
    """Get a raw emoji indicator for heat mapping."""
    if score >= 80:
        return "🔴"
    elif score >= 60:
        return "🟠"
    elif score >= 40:
        return "🟡"
    else:
        return "🟢"


def _add_module_to_tree(tree_node: Tree, module: Module) -> None:
    """Recursively add a module and its files to a Rich tree."""
    module_label = f"[bold cyan]📁 {module.name}/[/bold cyan]  [dim]({module.total_files} files, {module.total_lines} lines)[/dim]"
    mod_node = tree_node.add(module_label)

    for f in module.files:
        purpose_str = f"  [dim italic]{f.purpose}[/dim italic]" if f.purpose else ""
        file_label = f"[white]📄 {f.name}[/white]  {_complexity_badge(f.complexity)}  [dim]{f.line_count}L / {f.symbol_count} symbols[/dim]{purpose_str}"
        file_node = mod_node.add(file_label)

        for sym in f.symbols:
            kind_icon = "🔷" if sym.kind.value == "class" else "🔹"
            sym_label = f"{kind_icon} [bold]{sym.name}[/bold]  {_complexity_badge(sym.complexity)}  [dim]L{sym.line_start}-{sym.line_end}[/dim]"
            sym_node = file_node.add(sym_label)

            for child in sym.children:
                child_label = f"  ▸ [italic]{child.name}[/italic]  {_complexity_badge(child.complexity)}  [dim]L{child.line_start}-{child.line_end}[/dim]"
                sym_node.add(child_label)

    for sub in module.submodules:
        _add_module_to_tree(mod_node, sub)


def _add_root_files_to_tree(tree_node: Tree, files: list[FileModel]) -> None:
    """Add root-level files to the tree."""
    for f in files:
        purpose_str = f"  [dim italic]{f.purpose}[/dim italic]" if f.purpose else ""
        file_label = f"[white]📄 {f.name}[/white]  {_complexity_badge(f.complexity)}  [dim]{f.line_count}L / {f.symbol_count} symbols[/dim]{purpose_str}"
        file_node = tree_node.add(file_label)

        for sym in f.symbols:
            kind_icon = "🔷" if sym.kind.value == "class" else "🔹"
            sym_label = f"{kind_icon} [bold]{sym.name}[/bold]  {_complexity_badge(sym.complexity)}  [dim]L{sym.line_start}-{sym.line_end}[/dim]"
            sym_node = file_node.add(sym_label)

            for child in sym.children:
                child_label = f"  ▸ [italic]{child.name}[/italic]  {_complexity_badge(child.complexity)}  [dim]L{child.line_start}-{child.line_end}[/dim]"
                sym_node.add(child_label)


@click.group()
@click.version_option(version=__version__, prog_name="brahm-kosh")
def main():
    """Brahm-Kosh — Codebase Intelligence Engine.

    Turns code into structure, structure into insight, and insight into confidence.
    """
    pass


@main.command(name="analyze")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--json-output", "--json", "json_out", is_flag=True, help="Output as JSON instead of visual tree.")
@click.option("--top", "top_n", default=10, help="Number of hotspots to show.", show_default=True)
@click.option("--lang", "lang", default=None, help="Analyze only a specific language (e.g. python, javascript, c).")
def analyze_cmd(path: str, json_out: bool, top_n: int, lang: str | None):
    """Analyze a codebase and reveal its structure.

    PATH is the root directory to analyze (default: current directory).
    Use --lang to target a specific language adapter.
    """
    if json_out:
        _run_json(path, top_n, lang)
    else:
        _run_visual(path, top_n, lang)


@main.command(name="serve")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--port", default=8080, help="Port to run the 3D server on.")
@click.option("--lang", default=None, help="Analyze only a specific language.")
@click.option("--watch", is_flag=True, help="Re-analyze on file changes and live-update the open browser tab.")
@click.option("--no-browser", is_flag=True, help="Don't auto-open the system browser.")
def serve_cmd(path: str, port: int, lang: str | None, watch: bool, no_browser: bool):
    """Serve the 3D interactive codebase graph locally.

    Spins up a local web server (default port 8080) hosting the 3D viewer.
    With --watch, file changes inside PATH trigger a live re-analysis and
    the open browser tab repaints automatically — no reload, no Ctrl-R.
    """
    from brahm_kosh.server import serve_project

    with console.status("[bold cyan]Analyzing codebase for 3D generation...[/bold cyan]", spinner="dots"):
        project, _ = analyze(path, top_n=100, lang=lang)

    serve_project(project, port=port, watch=watch, open_browser=not no_browser)


@main.command(name="diff")
@click.argument("ref", type=str)
@click.option("--path", default=".", type=click.Path(exists=True), help="Path to the git repository.")
@click.option("--lang", default=None, help="Analyze only a specific language.")
def diff_cmd(ref: str, path: str, lang: str | None):
    """Compare architecture against a specific git reference.

    REF can be a branch, tag, or commit hash (e.g., main, HEAD~1).
    Evaluates how complexity and coupling have changed.
    """
    from brahm_kosh.cli_diff import run_diff
    run_diff(path, ref, lang)


def _run_visual(path: str, top_n: int, lang: str | None = None):
    """Run the visual (Rich) output mode."""
    console.print()
    console.print(Panel(
        Text(BANNER, style="bold bright_cyan", justify="center"),
        subtitle="[dim]Codebase Intelligence Engine v1.0[/dim]",
        border_style="bright_cyan",
        padding=(0, 2),
    ))
    console.print()

    # Analyze with a spinner
    spinner_msg = (
        f"[bold cyan]Analyzing {lang} files...[/bold cyan]"
        if lang else "[bold cyan]Analyzing codebase...[/bold cyan]"
    )
    with console.status(spinner_msg, spinner="dots"):
        start = time.time()
        project, hotspots = analyze(path, top_n=top_n, lang=lang)
        elapsed = time.time() - start

    meta = project.metadata

    lang_str = ", ".join(f"{lang} ({count})" for lang, count in meta.language_file_counts.items())
    if not lang_str:
        lang_str = ", ".join(meta.languages)

    # Stats panel
    stats_text = (
        f"[bold white]Project:[/bold white]  {project.name}\n"
        f"[bold white]Files:[/bold white]    {meta.total_files}\n"
        f"[bold white]Lines:[/bold white]    {meta.total_lines:,}\n"
        f"[bold white]Symbols:[/bold white]  {meta.total_symbols}\n"
        f"[bold white]Modules:[/bold white]  {meta.total_modules}\n"
        f"[bold white]Language:[/bold white] {lang_str}\n"
        f"[bold white]Avg Complexity:[/bold white] {_complexity_badge(meta.avg_complexity)}\n"
        f"[dim]Analyzed in {elapsed:.2f}s[/dim]"
    )
    console.print(Panel(
        stats_text,
        title="[bold bright_cyan]📊 Project Overview[/bold bright_cyan]",
        border_style="bright_cyan",
        padding=(1, 2),
    ))
    console.print()

    # Structure tree
    tree = Tree(
        f"[bold bright_cyan]🌳 {project.name}[/bold bright_cyan]",
        guide_style="bright_cyan",
    )
    _add_root_files_to_tree(tree, project.root_files)
    for mod in project.modules:
        _add_module_to_tree(tree, mod)

    console.print(Panel(
        tree,
        title="[bold bright_cyan]📁 Structure[/bold bright_cyan]",
        border_style="bright_cyan",
        padding=(1, 2),
    ))
    console.print()

    # Hotspots table
    if hotspots:
        table = Table(
            title="[bold bright_cyan]🔥 Hotspots — Top Complexity[/bold bright_cyan]",
            border_style="bright_cyan",
            show_lines=True,
            title_style="bold bright_cyan",
            padding=(0, 1),
        )
        table.add_column("#", style="dim", width=3, justify="right")
        table.add_column("Heat", width=4, justify="center")
        table.add_column("File", style="white", min_width=20)
        table.add_column("Language", style="cyan", min_width=10)
        table.add_column("Symbol", style="bold white", min_width=15)
        table.add_column("Kind", style="dim", width=8)
        table.add_column("Score", justify="right", width=6)
        table.add_column("Lines", style="dim", justify="right", width=10)

        for hs in hotspots:
            score_style = (
                "bold red" if hs.complexity >= 80
                else "bold yellow" if hs.complexity >= 60
                else "yellow" if hs.complexity >= 40
                else "green"
            )
            table.add_row(
                str(hs.rank),
                _heat_emoji(hs.complexity),
                hs.file_path,
                hs.language,
                hs.symbol_name,
                hs.symbol_kind,
                f"[{score_style}]{hs.complexity:.0f}[/{score_style}]",
                f"L{hs.line_start}-{hs.line_end}",
            )

        console.print(table)
        console.print()

    # Purpose summary
    files_with_purpose = [f for f in project.all_files() if f.purpose]
    if files_with_purpose:
        purpose_table = Table(
            title="[bold bright_cyan]🎯 File Purposes[/bold bright_cyan]",
            border_style="bright_cyan",
            title_style="bold bright_cyan",
            padding=(0, 1),
        )
        purpose_table.add_column("File", style="white", min_width=25)
        purpose_table.add_column("Purpose", min_width=20)
        purpose_table.add_column("Complexity", justify="right", width=12)

        for f in sorted(files_with_purpose, key=lambda x: x.complexity, reverse=True):
            purpose_table.add_row(
                f.relative_path,
                f.purpose,
                _complexity_badge(f.complexity),
            )

        console.print(purpose_table)
        console.print()

    # Footer
    console.print(
        Panel(
            "[dim italic]\"Brahm-Kosh turns code into structure, structure into insight, and insight into confidence.\"[/dim italic]",
            border_style="dim",
            padding=(0, 2),
        )
    )
    console.print()


def _run_json(path: str, top_n: int, lang: str | None = None):
    """Run the JSON output mode."""
    project, hotspots = analyze(path, top_n=top_n, lang=lang)

    output = project.to_dict()
    output["hotspots"] = [hs.to_dict() for hs in hotspots]

    click.echo(json.dumps(output, indent=2, ensure_ascii=False))


@main.command(name="list-adapters")
def list_adapters_cmd():
    """List all registered language adapters and their supported file extensions."""
    adapters = list_adapters()
    if not adapters:
        console.print("[yellow]No adapters registered.[/yellow]")
        return

    table = Table(
        title="[bold bright_cyan]🔌 Registered Language Adapters[/bold bright_cyan]",
        border_style="bright_cyan",
        title_style="bold bright_cyan",
        padding=(0, 1),
    )
    table.add_column("Language", style="bold white", min_width=15)
    table.add_column("Extensions", style="cyan", min_width=20)
    table.add_column("--lang flag", style="dim", min_width=12)

    for name, exts in sorted(adapters.items()):
        ext_str = "  ".join(sorted(exts)) if exts else "(auto)"
        table.add_row(name.capitalize(), ext_str, name)

    console.print()
    console.print(table)
    console.print()


if __name__ == "__main__":
    main()
