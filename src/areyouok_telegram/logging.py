import asyncio
from collections.abc import Callable
from collections.abc import Iterable
from functools import wraps
from typing import Any
from typing import TypeVar

import logfire

from areyouok_telegram.config import ENV

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
