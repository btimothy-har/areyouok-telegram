from datetime import UTC, datetime
from importlib.metadata import version

import httpx

from areyouok_telegram.config import TINYURL_API_KEY
from areyouok_telegram.logging import traced


def package_version():
    """Get the package version."""
    return version("areyouok-telegram")


def format_relative_time(created_at: datetime, reference_time: datetime | None = None) -> str:
    """Format a datetime as relative time from a reference point.

    Args:
        created_at: The datetime to format
        reference_time: The reference point to calculate relative time from (defaults to now)

    Returns:
        Human-readable relative time string (e.g., "2 days ago", "3 hours ago")
    """
    if reference_time is None:
        reference_time = datetime.now(UTC)

    delta = reference_time - created_at

    # Handle future dates (shouldn't happen but let's be safe)
    if delta.total_seconds() < 0:
        return "just now"

    seconds = int(delta.total_seconds())

    # Less than a minute
    if seconds < 60:
        return "just now"

    # Less than an hour
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"

    # Less than a day
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"

    # Less than a week
    days = hours // 24
    if days < 7:
        return f"{days} day{'s' if days != 1 else ''} ago"

    # Less than a month (30 days)
    if days < 30:
        weeks = days // 7
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"

    # Less than a year
    if days < 365:
        months = days // 30
        return f"{months} month{'s' if months != 1 else ''} ago"

    # Years
    years = days // 365
    return f"{years} year{'s' if years != 1 else ''} ago"


def escape_markdown_v2(text: str) -> str:
    """Escape special characters for MarkdownV2."""
    # Characters that need to be escaped in MarkdownV2
    special_chars = ["_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"]
    for char in special_chars:
        text = text.replace(char, rf"\{char}")
    return text


def split_long_message(message: str, max_length: int = 4000) -> list[str]:
    """Split a long message into chunks that fit within Telegram's limits."""
    if len(message) <= max_length:
        return [message]

    lines = message.split("\n")
    chunks: list[str] = []
    current = ""

    for line in lines:
        # Break overly long single lines
        if len(line) > max_length:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(line[i : i + max_length] for i in range(0, len(line), max_length))
            continue
        test = f"{current}\n{line}" if current else line
        if len(test) > max_length:
            chunks.append(current)
            current = line
        else:
            current = test

    if current:
        chunks.append(current)
    return chunks


@traced(extract_args=False, record_return=True)
async def shorten_url(url: str) -> str:
    """
    Shorten a URL using the TinyURL API.

    Args:
        url (str): The URL to shorten.

    Returns:
        str: The shortened URL.
    """
    if not TINYURL_API_KEY:
        return url

    api_url = "https://api.tinyurl.com/create"
    headers = {
        "Authorization": f"Bearer {TINYURL_API_KEY}",
    }

    payload = {"url": url}

    async with httpx.AsyncClient() as client:
        response = await client.post(api_url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json().get("data", {}).get("tiny_url", url)
