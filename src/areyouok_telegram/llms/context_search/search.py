"""Utility functions for context search and retrieval."""

from areyouok_telegram.llms.context_search.agent import ContextSearchResponse
from areyouok_telegram.llms.context_search.agent import context_search_agent
from areyouok_telegram.llms.context_search.retriever import retrieve_relevant_contexts
from areyouok_telegram.llms.utils import run_agent_with_tracking
from areyouok_telegram.logging import traced
from areyouok_telegram.utils.text import format_relative_time


@traced(extract_args=["chat_id", "session_id"])
async def search_chat_context(
    *,
    chat_id: str,
    session_id: str,
    search_query: str,
) -> str:
    """Search past conversations using semantic search and return formatted results.

    This is the main entry point that orchestrates the full search flow:
    1. Retrieves relevant contexts from vector store
    2. Formats contexts with timestamps
    3. Runs secondary LLM to answer query and summarize contexts
    4. Returns formatted response

    Args:
        chat_id: The chat ID to search within
        session_id: Current session ID for tracking
        search_query: Natural language query describing what to search for

    Returns:
        Formatted string with answer and summary, or error message
    """
    try:
        # Retrieve relevant contexts
        contexts = await retrieve_relevant_contexts(
            chat_id=chat_id,
            search_query=search_query,
        )

        if not contexts:
            return f"No relevant past conversations found for: {search_query}"

        # Format contexts with relative timestamps for the agent
        formatted_contexts = []
        for i, context in enumerate(contexts, 1):
            content = str(context.content) if context.content else ""
            timestamp = format_relative_time(context.created_at)
            formatted_contexts.append(f"Context {i} [{timestamp}]:\n{content}")

        contexts_text = "\n\n".join(formatted_contexts)

        # Prepare prompt for the agent
        prompt = f"""Search Query: {search_query}

Retrieved Conversation Contexts:

{contexts_text}

Please analyze these contexts and provide:
1. A direct answer to the search query
2. A summary of the key themes and patterns in these contexts"""

        # Run the context search agent
        agent_result = await run_agent_with_tracking(
            context_search_agent,
            chat_id=chat_id,
            session_id=session_id,
            run_kwargs={
                "user_prompt": prompt,
            },
        )

        response: ContextSearchResponse = agent_result.output

        # Format the final response
        formatted_response = f"""**Answer:**
{response.answer}

**Summary of Retrieved Contexts:**
{response.summary}

_Retrieved {len(contexts)} relevant conversation(s)_"""

    except Exception as e:
        return f"Error searching past conversations: {str(e)}"
    else:
        return formatted_response
