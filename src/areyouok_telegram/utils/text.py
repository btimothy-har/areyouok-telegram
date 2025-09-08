import httpx

from areyouok_telegram.config import TINYURL_API_KEY
from areyouok_telegram.logging import traced


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
            for i in range(0, len(line), max_length):
                chunks.append(line[i : i + max_length])
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
