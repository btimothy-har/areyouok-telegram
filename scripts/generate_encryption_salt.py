"""Generate a secure encryption salt for USER_ENCRYPTION_SALT environment variable."""

import secrets
import string
import sys

from rich.console import Console

console = Console()


def generate_salt(length: int = 32) -> str:
    """Generate a cryptographically secure random salt.
    
    Args:
        length: Length of the salt to generate (default: 32 characters)
    
    Returns:
        A secure random string suitable for use as an encryption salt
    """
    # Use all ASCII letters, digits, and some special characters
    # Avoiding characters that might cause issues in shell environments
    alphabet = string.ascii_letters + string.digits + "-_"
    
    # Generate a secure random salt
    salt = ''.join(secrets.choice(alphabet) for _ in range(length))
    
    return salt


def main():
    """Main function to generate and display the salt."""
    console.print("\n[bold cyan]🔐 Generating secure encryption salt...[/bold cyan]")
    console.print("-" * 50)
    
    # Generate the salt
    salt = generate_salt(32)
    
    console.print("\n[bold green]Add this to your .env file:[/bold green]")
    console.print(f"[yellow]USER_ENCRYPTION_SALT={salt}[/yellow]")
    
    console.print("\n[bold green]Or export it as an environment variable:[/bold green]")
    console.print(f"[yellow]export USER_ENCRYPTION_SALT=\"{salt}\"[/yellow]")
    
    console.print("\n[bold red]⚠️  IMPORTANT:[/bold red]")
    console.print("1. Keep this salt [bold]secret and secure[/bold]")
    console.print("2. Use the [bold]same salt[/bold] across all instances of your application")
    console.print("3. [bold red]Changing the salt will make existing encrypted data unreadable[/bold red]")
    console.print("4. Store this salt securely (e.g., in a secrets manager for production)\n")


if __name__ == "__main__":
    main()