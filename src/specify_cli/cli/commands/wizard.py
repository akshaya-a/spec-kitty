"""Interactive wizard for creating and updating documentation features.

This module provides a user-friendly interactive workflow that guides users through
the spec-kitty commands without needing to remember syntax.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.markdown import Markdown

from specify_cli.cli import select_with_arrows
from specify_cli.core import MISSION_CHOICES

app = typer.Typer(help="Interactive wizards for common spec-kitty workflows")
console = Console()


def _get_repo_root() -> Path:
    """Get the git repository root."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        console.print("[red]Error: Not in a git repository[/red]")
        raise typer.Exit(1)


def _get_existing_features(repo_root: Path) -> list[str]:
    """List existing features in kitty-specs/."""
    kitty_specs = repo_root / "kitty-specs"
    if not kitty_specs.exists():
        return []
    return sorted([
        d.name for d in kitty_specs.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    ])


def _slugify(text: str) -> str:
    """Convert text to a valid slug."""
    import re
    slug = text.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug.strip('-')


def _run_command(cmd: list[str], show_output: bool = True) -> subprocess.CompletedProcess:
    """Run a spec-kitty command and optionally show output."""
    console.print(f"[dim]Running: {' '.join(cmd)}[/dim]")
    result = subprocess.run(cmd, capture_output=not show_output, text=True)
    if result.returncode != 0 and not show_output:
        console.print(f"[red]Command failed:[/red]\n{result.stderr}")
    return result


def _prompt_raw_notes() -> str:
    """Prompt user for initial thoughts/raw notes."""
    console.print()
    console.print(Panel(
        "[bold]Initial Thoughts / Raw Notes[/bold]\n\n"
        "Enter any initial thoughts, context, or raw notes for this feature.\n"
        "This will be saved as input for the research phase.\n\n"
        "[dim]Press Enter twice (empty line) when done.[/dim]",
        border_style="cyan"
    ))
    
    lines = []
    console.print("[cyan]> [/cyan]", end="")
    while True:
        try:
            line = input()
            if line == "" and lines and lines[-1] == "":
                lines.pop()  # Remove trailing empty line
                break
            lines.append(line)
            console.print("[cyan]> [/cyan]", end="")
        except EOFError:
            break
    
    return "\n".join(lines)


def _save_raw_notes(repo_root: Path, feature_slug: str, notes: str) -> Path:
    """Save raw notes to the feature's staging area."""
    # Determine the feature directory
    kitty_specs = repo_root / "kitty-specs"
    feature_dirs = [d for d in kitty_specs.iterdir() if d.is_dir() and feature_slug in d.name]
    
    if not feature_dirs:
        console.print(f"[yellow]Warning: Feature directory not found for {feature_slug}[/yellow]")
        return None
    
    feature_dir = feature_dirs[0]
    research_dir = feature_dir / "research"
    research_dir.mkdir(exist_ok=True)
    
    notes_file = research_dir / "initial-notes.md"
    notes_file.write_text(f"# Initial Notes\n\n{notes}\n")
    
    return notes_file


@app.command("new")
def new_doc(
    non_interactive: bool = typer.Option(False, "--non-interactive", "-n", help="Skip interactive prompts"),
    feature_name: Optional[str] = typer.Option(None, "--name", help="Feature name"),
    mission: Optional[str] = typer.Option(None, "--mission", "-m", help="Mission type"),
) -> None:
    """Create a new documentation feature with guided setup.
    
    This wizard walks you through:
    1. Naming your feature
    2. Selecting a mission type
    3. Entering initial thoughts/raw notes
    4. Creating the feature structure
    5. Optionally starting research or orchestration
    """
    repo_root = _get_repo_root()
    
    console.print()
    console.print(Panel(
        "[bold cyan]📚 New Documentation Feature Wizard[/bold cyan]\n\n"
        "Let's create a new documentation feature step by step.",
        border_style="cyan"
    ))
    
    # Step 1: Feature name
    if not feature_name:
        console.print()
        console.print("[bold]Step 1: Feature Name[/bold]")
        console.print("[dim]What are you documenting? (e.g., 'Foundry Tools Local Dev Experience')[/dim]")
        feature_name = Prompt.ask("[cyan]Feature name[/cyan]")
    
    feature_slug = _slugify(feature_name)
    console.print(f"[dim]Slug: {feature_slug}[/dim]")
    
    # Step 2: Mission type
    if not mission:
        console.print()
        console.print("[bold]Step 2: Mission Type[/bold]")
        console.print("[dim]What kind of work is this?[/dim]")
        
        mission_descriptions = {
            "research": "Deep research and analysis (evidence-based)",
            "documentation": "Technical documentation (guides, references)",
            "software-dev": "Software development (code + docs)",
        }
        
        # select_with_arrows expects Dict[key, description]
        mission_options = {
            k: mission_descriptions.get(k, v)
            for k, v in MISSION_CHOICES.items()
        }
        
        mission = select_with_arrows(
            mission_options,
            prompt_text="Select mission type",
            console=console
        )
    
    console.print(f"[green]✓[/green] Mission: {mission}")
    
    # Step 3: Initial notes
    console.print()
    console.print("[bold]Step 3: Initial Context[/bold]")
    want_notes = Confirm.ask("Do you have initial thoughts or context to add?", default=True)
    
    raw_notes = ""
    if want_notes:
        raw_notes = _prompt_raw_notes()
    
    # Step 4: Create feature
    console.print()
    console.print("[bold]Step 4: Creating Feature[/bold]")
    
    result = _run_command([
        "spec-kitty", "agent", "feature", "create-feature",
        feature_slug, "--mission", mission
    ])
    
    if result.returncode != 0:
        console.print("[red]Failed to create feature[/red]")
        raise typer.Exit(1)
    
    # Save raw notes if provided
    if raw_notes:
        notes_file = _save_raw_notes(repo_root, feature_slug, raw_notes)
        if notes_file:
            console.print(f"[green]✓[/green] Saved initial notes to {notes_file.relative_to(repo_root)}")
            # Git add the notes
            subprocess.run(["git", "add", str(notes_file)], cwd=repo_root)
    
    # Step 5: Next steps
    console.print()
    console.print(Panel(
        f"[bold green]✅ Feature Created![/bold green]\n\n"
        f"Feature: [cyan]{feature_slug}[/cyan]\n"
        f"Mission: [cyan]{mission}[/cyan]\n"
        f"Location: [dim]kitty-specs/###-{feature_slug}/[/dim]\n\n"
        "[bold]Next Steps:[/bold]\n"
        "1. Edit [cyan]spec.md[/cyan] to refine the feature specification\n"
        "2. Edit [cyan]plan.md[/cyan] to define the implementation plan\n"
        "3. Edit [cyan]tasks.md[/cyan] to define work packages\n"
        "4. Run [cyan]spec-kitty orchestrate[/cyan] to start parallel execution",
        border_style="green"
    ))
    
    # Offer to start orchestration
    console.print()
    start_orchestrate = Confirm.ask("Start orchestration now?", default=False)
    
    if start_orchestrate:
        # Find the actual feature directory
        kitty_specs = repo_root / "kitty-specs"
        feature_dirs = [d for d in kitty_specs.iterdir() if d.is_dir() and feature_slug in d.name]
        
        if feature_dirs:
            feature_dir = feature_dirs[0]
            console.print(f"\n[cyan]Starting orchestration for {feature_dir.name}...[/cyan]")
            _run_command(["spec-kitty", "orchestrate", "--feature", feature_dir.name])
        else:
            console.print("[yellow]Could not find feature directory for orchestration[/yellow]")


@app.command("update")
def update_doc(
    feature: Optional[str] = typer.Option(None, "--feature", "-f", help="Feature to update"),
) -> None:
    """Update an existing documentation feature.
    
    This wizard helps you:
    1. Select an existing feature
    2. View current status
    3. Add new notes or context
    4. Re-run orchestration or specific tasks
    """
    repo_root = _get_repo_root()
    
    console.print()
    console.print(Panel(
        "[bold cyan]📝 Update Documentation Feature[/bold cyan]\n\n"
        "Select a feature to update or continue working on.",
        border_style="cyan"
    ))
    
    # Step 1: Select feature
    existing = _get_existing_features(repo_root)
    
    if not existing:
        console.print("[yellow]No existing features found in kitty-specs/[/yellow]")
        console.print("Run [cyan]spec-kitty wizard new[/cyan] to create one.")
        raise typer.Exit(0)
    
    if not feature:
        console.print()
        console.print("[bold]Step 1: Select Feature[/bold]")
        # select_with_arrows expects Dict[key, description]
        feature_options = {f: "" for f in existing}
        feature = select_with_arrows(
            feature_options,
            prompt_text="Select feature to update",
            console=console
        )
    
    feature_dir = repo_root / "kitty-specs" / feature
    
    if not feature_dir.exists():
        console.print(f"[red]Feature not found: {feature}[/red]")
        raise typer.Exit(1)
    
    # Step 2: Show current status
    console.print()
    console.print("[bold]Step 2: Current Status[/bold]")
    
    # Check meta.json for status
    meta_file = feature_dir / "meta.json"
    if meta_file.exists():
        meta = json.loads(meta_file.read_text())
        console.print(f"  Mission: [cyan]{meta.get('mission', 'unknown')}[/cyan]")
        console.print(f"  Status: [cyan]{meta.get('status', 'unknown')}[/cyan]")
    
    # List tasks
    tasks_dir = feature_dir / "tasks"
    if tasks_dir.exists():
        task_files = list(tasks_dir.glob("WP*.md"))
        console.print(f"  Tasks: [cyan]{len(task_files)} work packages[/cyan]")
    
    # Step 3: Actions
    console.print()
    console.print("[bold]Step 3: What would you like to do?[/bold]")
    
    actions = {
        "Add more notes/context": "Append to initial-notes.md",
        "View/edit spec.md": "Display spec content",
        "View/edit tasks": "List work packages",
        "Run orchestration": "Start parallel agent execution",
        "Check task status": "Show WP status",
        "Exit": "Done",
    }
    
    action = select_with_arrows(actions, prompt_text="Select action", console=console)
    
    if action == "Add more notes/context":
        raw_notes = _prompt_raw_notes()
        if raw_notes:
            notes_file = _save_raw_notes(repo_root, feature, raw_notes)
            if notes_file:
                console.print(f"[green]✓[/green] Appended notes to {notes_file.relative_to(repo_root)}")
                subprocess.run(["git", "add", str(notes_file)], cwd=repo_root)
    
    elif action == "View/edit spec.md":
        spec_file = feature_dir / "spec.md"
        if spec_file.exists():
            console.print(Markdown(spec_file.read_text()))
        else:
            console.print("[yellow]spec.md not found[/yellow]")
    
    elif action == "View/edit tasks":
        _run_command(["spec-kitty", "agent", "tasks", "list", "--feature", feature])
    
    elif action == "Run orchestration":
        _run_command(["spec-kitty", "orchestrate", "--feature", feature])
    
    elif action == "Check task status":
        _run_command(["spec-kitty", "agent", "tasks", "list", "--feature", feature])
    
    elif action == "Exit":
        console.print("[dim]Goodbye![/dim]")


@app.command("status")
def status() -> None:
    """Show status of all features and quick actions."""
    repo_root = _get_repo_root()
    
    console.print()
    console.print(Panel(
        "[bold cyan]📊 Spec Kitty Status[/bold cyan]",
        border_style="cyan"
    ))
    
    existing = _get_existing_features(repo_root)
    
    if not existing:
        console.print("[yellow]No features found.[/yellow]")
        console.print("\nRun [cyan]spec-kitty wizard new[/cyan] to create your first feature.")
        return
    
    console.print(f"\n[bold]Features ({len(existing)}):[/bold]\n")
    
    for feature in existing:
        feature_dir = repo_root / "kitty-specs" / feature
        meta_file = feature_dir / "meta.json"
        
        status_str = "[dim]unknown[/dim]"
        mission_str = ""
        
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text())
                status_str = f"[cyan]{meta.get('status', 'unknown')}[/cyan]"
                mission_str = f" ({meta.get('mission', '')})"
            except json.JSONDecodeError:
                pass
        
        # Count tasks
        tasks_dir = feature_dir / "tasks"
        task_count = len(list(tasks_dir.glob("WP*.md"))) if tasks_dir.exists() else 0
        
        console.print(f"  • [bold]{feature}[/bold]{mission_str}")
        console.print(f"    Status: {status_str} | Tasks: {task_count}")
    
    console.print()
    console.print("[dim]Commands:[/dim]")
    console.print("  [cyan]spec-kitty wizard new[/cyan]     - Create new feature")
    console.print("  [cyan]spec-kitty wizard update[/cyan]  - Update existing feature")
    console.print("  [cyan]spec-kitty orchestrate[/cyan]    - Run parallel execution")
    console.print("  [cyan]spec-kitty dashboard[/cyan]      - Open visual dashboard")
