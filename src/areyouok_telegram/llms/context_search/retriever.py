"""Utility functions for context search and retrieval."""

import asyncio

from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters

from areyouok_telegram.config import RAG_TOP_K
from areyouok_telegram.data.database.embeddings import context_vector_index
from areyouok_telegram.data.models import Chat, Context
from areyouok_telegram.logging import traced


@traced(extract_args=["chat"])
async def retrieve_relevant_contexts(
    *,
    chat: Chat,
    search_query: str,
) -> list[Context]:
    """Retrieve relevant contexts using semantic search.

    Args:
        chat: The chat to search within (ensures user isolation)
        search_query: Natural language query describing what to search for

    Returns:
        List of auto-decrypted Context objects, or empty list if none found

    Raises:
        Exception: If retrieval fails
    """
    # Create retriever with metadata filtering for user isolation
    retriever = context_vector_index.as_retriever(
        similarity_top_k=RAG_TOP_K,
        filters=MetadataFilters(filters=[ExactMatchFilter(key="chat_id", value=str(chat.telegram_chat_id))]),
    )

    # Retrieve nodes (contains metadata only, not encrypted content)
    nodes = await retriever.aretrieve(search_query)

    if not nodes:
        return []

    # Extract context IDs from node metadata
    context_ids = [int(node.metadata["context_id"]) for node in nodes]

    # Fetch full Context objects in parallel (auto-decrypted)
    contexts = await asyncio.gather(*[Context.get_by_id(chat=chat, context_id=ctx_id) for ctx_id in context_ids])

    # Filter out None values
    return [ctx for ctx in contexts if ctx is not None]
