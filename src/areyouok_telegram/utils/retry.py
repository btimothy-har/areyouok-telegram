import asyncio
from datetime import timedelta

import logfire
import telegram.error
from asyncpg.exceptions import ConnectionDoesNotExistError, InterfaceError
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm.exc import DetachedInstanceError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_chain, wait_fixed, wait_random_exponential


def db_retry():
    return retry(
        retry=retry_if_exception_type((ConnectionDoesNotExistError, DBAPIError, InterfaceError, DetachedInstanceError)),
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


@telegram_retry()
async def telegram_call(func, *args, **kwargs):
    """
    Execute a Telegram API call with retry logic.

    Handles:
    - NetworkError/TimedOut: Retries with exponential backoff (via telegram_retry)
    - RetryAfter: Waits required time then retries (bounded attempts)

    Args:
        func: The telegram bot method to call
        *args: Positional arguments for the method
        **kwargs: Keyword arguments for the method

    Returns:
        The result of the Telegram API call
    """
    # Cap RetryAfter handling to avoid unbounded recursion/reset attempts.
    attempts = 0
    while True:
        try:
            return await func(*args, **kwargs)
        except telegram.error.RetryAfter as e:
            attempts += 1
            if attempts > 10:
                raise

            retry_after_delta = (
                e.retry_after if isinstance(e.retry_after, timedelta) else timedelta(seconds=e.retry_after)
            )
            delay_seconds = float(retry_after_delta.total_seconds()) + 0.5

            logfire.info(
                "Telegram RetryAfter; sleeping before retry",
                delay_seconds=delay_seconds,
                attempts=attempts,
                method=getattr(func, "__name__", repr(func)),
            )
            await asyncio.sleep(delay_seconds)
