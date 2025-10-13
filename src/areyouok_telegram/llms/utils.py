# ruff: noqa: TRY003

import asyncio
import time

import anthropic
import google
import httpx
import openai
import pydantic_ai
from tenacity import retry
from tenacity import retry_if_exception
from tenacity import stop_after_attempt
from tenacity import wait_chain
from tenacity import wait_fixed
from tenacity import wait_random_exponential

from areyouok_telegram.data import Chats
from areyouok_telegram.data import Context
from areyouok_telegram.data import ContextType
from areyouok_telegram.data import async_database
from areyouok_telegram.data import operations as data_operations


def should_retry_llm_error(e: Exception) -> bool:
    """
    Determine if an exception should trigger a retry for LLM operations.

    Args:
        e: The exception to check

    Returns:
        True if the exception is retryable, False otherwise
    """
    # Network-level transient errors (DNS, connection, timeouts)
    if isinstance(e, httpx.TimeoutException | httpx.NetworkError):
        return True

    # Provider-specific errors
    if isinstance(e, anthropic.APITimeoutError):
        return True
    if isinstance(e, anthropic.APIStatusError):
        # Retry on 5xx errors
        return 500 <= e.status_code < 600
    if isinstance(e, openai.APITimeoutError):
        return True
    if isinstance(e, openai.APIStatusError):
        return 500 <= e.status_code < 600
    if isinstance(e, google.genai.errors.ServerError):
        return True

    return False


@retry(
    retry=retry_if_exception(should_retry_llm_error),
    wait=wait_chain(*[wait_fixed(0.5) for _ in range(2)] + [wait_random_exponential(multiplier=0.5, max=5)]),
    stop=stop_after_attempt(5),
    reraise=True,
)
async def run_agent_with_tracking(
    agent: pydantic_ai.Agent,
    *,
    chat_id: str,
    session_id: str | None = None,
    run_kwargs: dict | None = None,
) -> pydantic_ai.agent.AgentRunResult:
    """
    Run a Pydantic AI agent and automatically track its usage.

    Args:
        agent: The Pydantic AI agent to run
        chat_id: The chat ID for tracking
        session_id: The session ID for tracking
        run_kwargs: Arguments to pass to agent.run()

    Returns:
        The agent run result
    """

    run_kwargs = run_kwargs or {}

    # Ensure required kwargs are present
    if "user_prompt" not in run_kwargs and "message_history" not in run_kwargs:
        raise ValueError("Either 'user_prompt' or 'message_history' must be provided in run_kwargs")

    # Track generation duration using high-resolution timer
    start_time = time.perf_counter()
    result = await agent.run(**run_kwargs)
    end_time = time.perf_counter()

    generation_duration = end_time - start_time

    # Track usage and generation in background - don't await
    asyncio.create_task(
        data_operations.track_llm_usage(
            chat_id=chat_id,
            session_id=session_id or "no_session",
            agent=agent,
            result=result,
            runtime=generation_duration,
            run_kwargs=run_kwargs,
        )
    )
    return result


async def log_metadata_update_context(
    *,
    chat_id: str,
    session_id: str,
    content: str,
) -> None:
    """Log a metadata update to the context table.

    Args:
        chat_id: The chat ID where the update occurred
        session_id: The session ID where the update occurred
        field: The metadata field that was updated
        new_value: The new value that was set
    """
    async with async_database() as db_conn:
        chat_obj = await Chats.get_by_id(db_conn, chat_id=chat_id)
        chat_encryption_key = chat_obj.retrieve_key()

        await Context.new(
            db_conn,
            chat_encryption_key=chat_encryption_key,
            chat_id=chat_id,
            session_id=session_id,
            ctype=ContextType.METADATA.value,
            content=content,
        )
