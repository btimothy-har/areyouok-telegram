import asyncio
from collections.abc import Callable
from collections.abc import Iterable
from functools import wraps
from typing import Any
from typing import TypeVar

import httpx
import logfire
import telegram.error
from asyncpg.exceptions import ConnectionDoesNotExistError
from asyncpg.exceptions import InterfaceError
from sqlalchemy.exc import DBAPIError
from tenacity import retry
from tenacity import retry_if_exception_type
from tenacity import stop_after_attempt
from tenacity import wait_chain
from tenacity import wait_fixed
from tenacity import wait_random_exponential

from areyouok_telegram.config import ENV
from areyouok_telegram.config import TINYURL_API_KEY

F = TypeVar("F", bound=Callable[..., Any])


def traced(
    msg_template: str | None = None,
    *,
    extract_args: bool | Iterable[str] = True,
    record_return: bool = False,
) -> Callable[[F], F]:
    """
    Decorator that wraps a function with logfire.instrument, automatically setting
    the span name to the function's module path.

    Args:
        message: Optional message template for the span (can use {arg} placeholders)
        extract_args: Whether to extract and log function arguments (default: True)
        **attributes: Additional attributes to include in the span

    Example:
        @traced("Processing message")
        async def on_new_message(update, context):
            # Will create span with name "handlers.messages.on_new_message"
            ...

        @traced("Handling {event_type} event", user_id=123)
        async def handle_event(event_type: str):
            # Will create span with name "handlers.events.handle_event"
            ...
    """

    def decorator(func: F) -> F:
        # Build the span name from module and function name
        module = func.__module__
        if module.startswith("areyouok_telegram."):
            # Strip the package prefix for cleaner names
            module = module[len("areyouok_telegram.") :]

        span_name = f"{module}.{func.__name__}"

        # Apply logfire's instrument decorator
        return logfire.instrument(
            msg_template=msg_template or span_name,
            span_name=span_name,
            extract_args=extract_args,
            record_return=record_return,
        )(func)

    return decorator


def environment_override(func_map: dict[str, Callable]) -> Callable:
    """
    Decorator that switches function implementations based on the ENV environment variable.

    This decorator allows you to define different implementations of a function for different
    environments (production, staging, development, etc.) and automatically selects the
    appropriate one at runtime. Works with both synchronous and asynchronous functions.
    """

    def decorator(default_func: Callable) -> Callable:
        is_async = asyncio.iscoroutinefunction(default_func)

        if is_async:

            @wraps(default_func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                func = func_map.get(ENV, default_func)
                return await func(*args, **kwargs)

            return async_wrapper
        else:

            @wraps(default_func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                func = func_map.get(ENV, default_func)
                return func(*args, **kwargs)

            return sync_wrapper

    return decorator


def db_retry():
    return retry(
        retry=retry_if_exception_type((ConnectionDoesNotExistError, DBAPIError, InterfaceError)),
        wait=wait_chain(*[wait_fixed(0.5) for _ in range(2)] + [wait_random_exponential(multiplier=0.5, max=5)]),
        stop=stop_after_attempt(5),
        reraise=True,
    )


def telegram_retry():
    """
    Retry decorator for Telegram API calls.

    Handles:
    - NetworkError: Network connectivity issues
    - TimedOut: Request timeout errors

    Uses exponential backoff with jitter for retries.
    """
    return retry(
        retry=retry_if_exception_type((telegram.error.NetworkError, telegram.error.TimedOut)),
        wait=wait_random_exponential(multiplier=0.25, max=5),
        stop=stop_after_attempt(5),
        reraise=True,
    )


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


@traced(record_return=True)
async def shorten_url(url: str) -> str:
    """
    Shorten a URL using the TinyURL API.

    Args:
        url (str): The URL to shorten.

    Returns:
        str: The shortened URL.
    """
    api_url = "https://api.tinyurl.com/create"
    headers = {
        "Authorization": f"Bearer {TINYURL_API_KEY}",
    }

    payload = {"url": url}

    async with httpx.AsyncClient() as client:
        response = await client.post(api_url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json().get("data", {}).get("tiny_url", url)
