"""Utility functions for context search and retrieval."""

from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters

from areyouok_telegram.config import RAG_TOP_K
from areyouok_telegram.data import Chats, Context, async_database, context_vector_index
from areyouok_telegram.logging import traced
from areyouok_telegram.utils.retry import db_retry


@traced(extract_args=["chat_id"])
@db_retry()
async def retrieve_relevant_contexts(
    *,
    chat_id: str,
    search_query: str,
) -> list[Context]:
    """Retrieve relevant contexts using semantic search.

    Args:
        chat_id: The chat ID to search within (ensures user isolation)
        search_query: Natural language query describing what to search for

    Returns:
        List of decrypted Context objects, or empty list if none found

    Raises:
        Exception: If retrieval or decryption fails
    """
    # Create retriever with metadata filtering for user isolation
    retriever = context_vector_index.as_retriever(
        similarity_top_k=RAG_TOP_K,
        filters=MetadataFilters(filters=[ExactMatchFilter(key="chat_id", value=chat_id)]),
    )

    # Retrieve nodes (contains metadata only, not encrypted content)
    nodes = await retriever.aretrieve(search_query)

    if not nodes:
        return []

    # Extract context IDs from node metadata
    context_ids = [int(node.metadata["context_id"]) for node in nodes]

    # Fetch full Context objects from database
    async with async_database() as db_conn:
        # Get chat encryption key
        chat = await Chats.get_by_id(db_conn, chat_id=chat_id)
        chat_key = chat.retrieve_key()

        contexts = await Context.get_by_ids(db_conn, ids=context_ids)
        if not contexts:
            return []

    # Decrypt all contexts
    for context in contexts:
        context.decrypt_content(chat_encryption_key=chat_key)

    return contexts
