# ruff: noqa: TRY003

import asyncio
import time

import anthropic
import google
import httpx
import logfire
import openai
import pydantic_ai
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_chain, wait_fixed, wait_random_exponential

from areyouok_telegram.data.models import Chat, LLMGeneration, LLMUsage, Session


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
    session: Session | None = None,
    run_kwargs: dict,
) -> pydantic_ai.agent.AgentRunResult:
    """
    Run a Pydantic AI agent and automatically track its usage.

    Args:
        agent: The Pydantic AI agent to run
        chat: Chat object for tracking (required)
        session: Session object for tracking (optional, can be None for background jobs)
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
    # Session is optional (can be None for background jobs)
    async def _track_usage():
        try:
            # Use session.id if available, otherwise None (for background jobs)
            session_id = session.id if session else None

            # Create and save LLM usage record
            llm_usage = LLMUsage.from_pydantic_usage(
                chat_id=chat.id,
                session_id=session_id,
                agent=agent,
                data=result.usage(),
                runtime=generation_duration,
            )
            await llm_usage.save()

            # Create and save LLM generation record
            llm_generation = LLMGeneration.from_agent_run(
                chat_id=chat.id,
                session_id=session_id,
                agent=agent,
                run_result=result,
                run_deps=run_kwargs.get("deps"),
            )
            await llm_generation.save()

        except Exception as e:
            # Log the error but don't raise it
            logfire.exception(
                f"Failed to log LLM usage: {e}",
                agent=agent.name,
                chat_id=chat.id,
                session_id=session_id if session else None,
            )

    asyncio.create_task(_track_usage())

    return result
