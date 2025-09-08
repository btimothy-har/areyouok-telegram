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

    # Split by lines to keep traceback readable
    lines = message.split("\n")
    chunks = []
    current_chunk = ""

    for line in lines:
        test_chunk = current_chunk + "\n" + line if current_chunk else line
        if len(test_chunk) > max_length and current_chunk:
            chunks.append(current_chunk)
            current_chunk = line
        else:
            current_chunk = test_chunk

    if current_chunk:
        chunks.append(current_chunk)

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
