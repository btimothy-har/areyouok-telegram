"""Shared tools for chat agents."""

from typing import Protocol

from areyouok_telegram.data import Chats
from areyouok_telegram.data import Context
from areyouok_telegram.data import ContextType
from areyouok_telegram.data import async_database
from areyouok_telegram.llms.context_search import search_chat_context
from areyouok_telegram.llms.exceptions import ContextSearchError
from areyouok_telegram.llms.exceptions import MemoryUpdateError


class ChatDependencies(Protocol):
    """Protocol for chat agent dependencies."""

    tg_chat_id: str
    tg_session_id: str


async def update_memory_impl(
    deps: ChatDependencies,
    information_to_remember: str,
) -> str:
    """
    Update your memory bank with new information about the user that you want to remember.
    """
    async with async_database() as db_conn:
        try:
            chat = await Chats.get_by_id(db_conn, chat_id=deps.tg_chat_id)
            chat_encryption_key = chat.retrieve_key()

            await Context.new(
                db_conn,
                chat_encryption_key=chat_encryption_key,
                chat_id=deps.tg_chat_id,
                session_id=deps.tg_session_id,
                ctype=ContextType.MEMORY.value,
                content=information_to_remember,
            )

        except Exception as e:
            raise MemoryUpdateError(information_to_remember, e) from e

    return f"Information committed to memory: {information_to_remember}."


async def search_history_impl(
    deps: ChatDependencies,
    search_query: str,
) -> str:
    """
    Search history for relevant context using semantic search.

    Use this when you need to recall specific topics, emotions, events, or patterns
    from previous conversations with this user. This helps maintain continuity and
    shows the user you remember important details from your relationship.

    Args:
        search_query: Natural language query describing what to search for. The query should be
        phrased from a 3rd-party perspective and pronoun-neutral.
                    (e.g., "times user felt anxious about work", "user's goals")

    Returns:
        A formatted response with direct answer and context summary, or error message
    """
    try:
        result = await search_chat_context(
            chat_id=deps.tg_chat_id,
            session_id=deps.tg_session_id,
            search_query=search_query,
        )
    except Exception as e:
        raise ContextSearchError(search_query, e) from e
    else:
        return result
