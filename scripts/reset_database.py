"""Reset the database by dropping all tables and recreating the schema."""

import sys

from rich.console import Console
from rich.prompt import Confirm
from sqlalchemy import create_engine
from sqlalchemy import inspect
from sqlalchemy.schema import CreateSchema
from sqlalchemy.schema import DropSchema

from areyouok_telegram.config import ENV
from areyouok_telegram.config import PG_CONNECTION_STRING
from areyouok_telegram.data import Base

console = Console()


def main():
    """Drop all tables in the schema and recreate them."""

    # Show current environment
    console.print(f"\n[bold yellow]Current environment:[/bold yellow] [cyan]{ENV}[/cyan]")
    console.print(
        f"[bold yellow]Database:[/bold yellow] [cyan]{PG_CONNECTION_STRING.split('@')[1] if '@' in PG_CONNECTION_STRING else 'local'}[/cyan]\n"
    )

    # Create engine
    engine = create_engine(f"postgresql://{PG_CONNECTION_STRING}")

    # Check if schema exists and list tables
    inspector = inspect(engine)
    schema_exists = ENV in inspector.get_schema_names()

    if schema_exists:
        tables = inspector.get_table_names(schema=ENV)
        if tables:
            console.print(f"[bold red]WARNING:[/bold red] The following tables will be dropped from schema '{ENV}':")
            for table in tables:
                console.print(f"  • {table}")
        else:
            console.print(f"[yellow]Schema '{ENV}' exists but contains no tables.[/yellow]")
    else:
        console.print(f"[yellow]Schema '{ENV}' does not exist yet.[/yellow]")

    console.print()

    # Get confirmation
    if not Confirm.ask(
        f"[bold red]Are you sure you want to reset the database?[/bold red]\n"
        f"This will [bold]permanently delete ALL data[/bold] in schema '{ENV}'",
        default=False,
    ):
        console.print("[green]Database reset cancelled.[/green]")
        return

    # Double confirmation for production environments
    if ENV in ["production", "staging"]:
        console.print(f"\n[bold red]⚠️  CRITICAL: You are about to reset the {ENV.upper()} database![/bold red]")
        if not Confirm.ask(
            f"[bold red]Type 'yes' to confirm you want to DELETE ALL DATA in {ENV.upper()}[/bold red]", default=False
        ):
            console.print("[green]Database reset cancelled.[/green]")
            return

    try:
        with engine.begin() as conn:
            # Drop the schema cascade (drops all tables and objects in the schema)
            if schema_exists:
                console.print(f"[yellow]Dropping schema '{ENV}' and all its contents...[/yellow]")
                conn.execute(DropSchema(ENV, cascade=True))

            # Recreate the schema
            console.print(f"[yellow]Creating schema '{ENV}'...[/yellow]")
            conn.execute(CreateSchema(ENV))

            # Create all tables
            console.print(f"[yellow]Creating tables in schema '{ENV}'...[/yellow]")
            Base.metadata.create_all(conn)

        # Verify the reset
        inspector = inspect(engine)
        new_tables = inspector.get_table_names(schema=ENV)

        console.print("\n[bold green]✓ Database reset complete![/bold green]")
        console.print(f"[green]Created {len(new_tables)} tables in schema '{ENV}':[/green]")
        for table in new_tables:
            console.print(f"  • {table}")

    except Exception as e:
        console.print(f"\n[bold red]Error resetting database:[/bold red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
