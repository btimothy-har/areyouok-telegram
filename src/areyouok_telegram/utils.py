from collections.abc import Callable
from collections.abc import Iterable
from typing import Any
from typing import TypeVar

import logfire
from asyncpg.exceptions import ConnectionDoesNotExistError
from asyncpg.exceptions import InterfaceError
from sqlalchemy.exc import DBAPIError
from tenacity import retry
from tenacity import retry_if_exception_type
from tenacity import stop_after_attempt
from tenacity import wait_chain
from tenacity import wait_fixed
from tenacity import wait_random_exponential

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


def db_retry():
    return retry(
        retry=retry_if_exception_type((ConnectionDoesNotExistError, DBAPIError, InterfaceError)),
        wait=wait_chain(*[wait_fixed(0.5) for _ in range(2)] + [wait_random_exponential(multiplier=0.5, max=5)]),
        stop=stop_after_attempt(5),
        reraise=True,
    )
