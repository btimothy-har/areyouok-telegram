# ruff: noqa: TRY003

import asyncio
import time

import anthropic
import google
import httpx
import openai
import pydantic_ai
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_chain, wait_fixed, wait_random_exponential

from areyouok_telegram.data import operations as data_operations
from areyouok_telegram.data.models import Chat, Context, ContextType, Session


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
    chat: Chat,
    session: Session,
    run_kwargs: dict,
) -> pydantic_ai.agent.AgentRunResult:
    """
    Run a Pydantic AI agent and automatically track its usage.

    Args:
        agent: The Pydantic AI agent to run
        chat: Chat object for tracking
        session: Session object for tracking
        run_kwargs: Arguments to pass to agent.run()

    Returns:
        The agent run result
    """

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
            chat_id=chat.telegram_chat_id,  # Use Telegram ID for tracking
            session_id=session.session_id,  # Use session key for tracking
            agent=agent,
            result=result,
            runtime=generation_duration,
            run_kwargs=run_kwargs,
        )
    )
    return result


async def log_metadata_update_context(
    *,
    chat: Chat,
    session: Session,
    content: str,
) -> None:
    """Log a metadata update to the context table.

    Args:
        chat: The chat where the update occurred
        session: The session where the update occurred
        content: The content to log
    """
    context = Context(
        chat=chat,
        session_id=session.id,
        type=ContextType.METADATA.value,
        content=content,
    )
    await context.save()
