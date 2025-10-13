from collections.abc import Callable, Iterable
from typing import Any, TypeVar

import logfire

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
        msg_template: Optional message template for the span (can use {arg} placeholders)
        extract_args: Whether to extract and log function arguments (default: True)
        record_return: Whether to record the function return value (default: False)

    Example:
        @traced("Processing message")
        async def on_new_message(update, context):
            # Will create span with name "handlers.messages.on_new_message"
            ...

        @traced("Handling {event_type} event", extract_args=["event_type"])
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
