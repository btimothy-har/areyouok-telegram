# ruff: noqa: PLC0415

import asyncio
import sys
from pathlib import Path

import click

# Add scripts to path for importing
SCRIPTS_PATH = Path(__file__).parent.parent.parent / "scripts"

# Validate scripts directory exists (development environment check)
if not SCRIPTS_PATH.exists():
    click.echo(
        click.style("❌ Error: ", fg="red", bold=True)
        + "Scripts directory not found. CLI commands are only available in development environment.",
        err=True,
    )
    click.echo(click.style("Expected path: ", fg="yellow") + str(SCRIPTS_PATH), err=True)
    sys.exit(1)

sys.path.insert(0, str(SCRIPTS_PATH))


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
def generate_salt():
    """Generate encryption salt for secure data storage."""
    from generate_encryption_salt import main

    return main()


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
def reset_db():
    """Drop and recreate database schema."""
    from reset_database import main

    return main()


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "-c",
    "--character",
    required=True,
    help="Name of the character file (without .md extension) in scripts/sim_characters/",
)
@click.option(
    "-p",
    "--personality",
    default="companionship",
    type=click.Choice(["anchoring", "celebration", "companionship", "exploration", "witnessing"]),
    help="Bot personality to use for the simulation",
)
@click.option("-t", "--turns", default=5, type=int, help="Number of conversation turns to simulate")
@click.option(
    "--no-switch", is_flag=True, default=False, help="Disable the bot from switching personalities during conversation"
)
def simulate(character, personality, turns, no_switch):
    """Run conversation simulation and evaluation."""
    # Set simulation mode environment variable
    import os

    os.environ["SIMULATION_MODE"] = "true"

    # Import simulator components
    from rich.console import Console
    from simulator.simulate import ConversationEvaluator, ConversationSimulator

    console = Console()

    async def run_simulation():
        console.print("\n[bold magenta]🎭 Conversation Simulation Script[/bold magenta]")
        console.print("=" * 50)
        console.print(f"[yellow]Character:[/yellow] {character}")
        console.print(f"[yellow]Personality:[/yellow] {personality}")
        console.print(f"[yellow]Turns:[/yellow] {turns}")
        console.print(f"[yellow]Personality Switching:[/yellow] {'Disabled' if no_switch else 'Enabled'}")

        try:
            # Create simulator with specified parameters
            simulator = ConversationSimulator(
                user_character_file=character,
                personality=personality,
                no_switch=no_switch,
            )

            await simulator.simulate_conversation(num_turns=turns)

            console.print(
                f"\n[bold green]✅ Simulation complete! "
                f"Total turns: {len(simulator.conversation_history)}, "
                f"Total messages: {len(simulator.chronological_messages)}[/bold green]"
                "\n"
            )
            # Print token usage summary
            simulator.print_token_summary()
            console.print("\n")

            evaluator = ConversationEvaluator(simulator)
            evaluation = await evaluator.evaluate_conversation(name="test_evaluation")

            evaluation.print()

            console.print("\n[bold green]🎉 Test complete![/bold green]")

        except FileNotFoundError as e:
            console.print(f"\n[bold red]❌ Error:[/bold red] {e}")
            console.print("[yellow]Available characters in scripts/sim_characters/:[/yellow]")

            # List available character files
            script_dir = SCRIPTS_PATH / "simulator"
            character_dir = script_dir / "sim_characters"
            if character_dir.exists():
                for character_file in character_dir.glob("*.md"):
                    console.print(f"  • {character_file.stem}")
            else:
                console.print("  [red]No sim_characters directory found[/red]")
            return 1

        except Exception as e:
            console.print(f"\n[bold red]❌ Unexpected error:[/bold red] {e}")
            return 1

    return asyncio.run(run_simulation())
