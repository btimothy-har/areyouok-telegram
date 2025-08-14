# ruff: noqa: TRY003


import anthropic
import logfire
import openai
import pydantic_ai
from tenacity import retry
from tenacity import retry_if_exception
from tenacity import stop_after_attempt
from tenacity import wait_chain
from tenacity import wait_fixed
from tenacity import wait_random_exponential

from areyouok_telegram.data import LLMUsage
from areyouok_telegram.data import async_database


def should_retry_llm_error(e: Exception) -> bool:
    """
    Determine if an exception should trigger a retry for LLM operations.

    Args:
        e: The exception to check

    Returns:
        True if the exception is retryable, False otherwise
    """
    if isinstance(e, anthropic.APITimeoutError):
        return True
    if isinstance(e, anthropic.APIStatusError):
        # Retry on 5xx errors
        return 500 <= e.status_code < 600
    if isinstance(e, openai.APITimeoutError):
        return True
    if isinstance(e, openai.APIStatusError):
        return 500 <= e.http_status < 600


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
    session_id: str,
    run_kwargs: dict,
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

    # Ensure required kwargs are present
    if "user_prompt" not in run_kwargs and "message_history" not in run_kwargs:
        raise ValueError("Either 'user_prompt' or 'message_history' must be provided in run_kwargs")

    result = await agent.run(**run_kwargs)

    try:
        # Always track llm usage in a separate async context
        async with async_database() as db_conn:
            await LLMUsage.track_pydantic_usage(
                db_conn=db_conn,
                chat_id=chat_id,
                session_id=session_id,
                agent=agent,
                data=result.usage(),
            )
    except Exception as e:
        # Log the error but don't raise it, as we want to return the result regardless
        logfire.exception(
            f"Failed to log LLM usage: {e}",
            agent=agent.name,
            chat_id=chat_id,
            session_id=session_id,
        )

    return result
