"""Background job for indexing Context records into LlamaIndex vector store."""

import logfire
from aiolimiter import AsyncLimiter
from llama_index.core import Document
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.schema import TransformComponent
from llama_index.embeddings.openai import OpenAIEmbedding

from areyouok_telegram.config import RAG_ENABLE_SEMANTIC_SEARCH
from areyouok_telegram.data import Context
from areyouok_telegram.data import async_database
from areyouok_telegram.data import context_vector_store
from areyouok_telegram.jobs.base import BaseJob
from areyouok_telegram.logging import traced
from areyouok_telegram.utils import db_retry


class RedactNodeContent(TransformComponent):
    def __call__(self, nodes, **kwargs):  # noqa:ARG002
        for node in nodes:
            node.text = "content_redacted"
        return nodes


pipeline = IngestionPipeline(
    transformations=[
        OpenAIEmbedding(),
        RedactNodeContent(),
    ],
    vector_store=context_vector_store,
)


class ContextEmbeddingJob(BaseJob):
    """Embed a single Context record into LlamaIndex vector store.

    This job is triggered automatically when a Context is created.
    The class-level rate limiter ensures we don't overwhelm the OpenAI API.
    """

    # Shared rate limiter across all job instances
    openai_limiter: AsyncLimiter = AsyncLimiter(max_rate=500, time_period=60)

    def __init__(self, context_id: int, encryption_key: str):
        """
        Initialize the context indexing job.

        Args:
            context_id: The Context ID to index
        """
        super().__init__()
        self.context_id = context_id
        self.encryption_key = encryption_key

    @property
    def name(self) -> str:
        """Generate a consistent job name."""
        return f"context_indexing:{self.context_id}"

    @traced(extract_args=["context_id"])
    async def run_job(self) -> None:
        """Index the context into LlamaIndex vector store."""
        if not RAG_ENABLE_SEMANTIC_SEARCH:
            logfire.debug(f"RAG disabled, skipping indexing for context {self.context_id}")
            return

        try:
            # Fetch context and chat
            context = await self._fetch_context()

            if not context:
                logfire.warning(f"Context {self.context_id} not found, skipping indexing")
                return

            if not context.content:
                logfire.warning(f"Context {self.context_id} has no content, skipping indexing")
                return

            # Create Document
            ctx_document = Document(
                text=str(context.content),
                id_=str(context.id),
                metadata={
                    "chat_id": context.chat_id,
                    "type": context.type,
                    "created_at": context.created_at.isoformat(),
                },
            )

            async with self.openai_limiter:
                await pipeline.arun(documents=[ctx_document])

            logfire.info(
                f"Successfully embedded context {self.context_id}",
                context_id=self.context_id,
            )

        except Exception:
            logfire.exception(f"Failed to index context {self.context_id}")
            raise

    @db_retry()
    async def _fetch_context(self) -> tuple[Context | None, str | None]:
        """Fetch the context and its associated chat encryption key."""
        async with async_database() as db_conn:
            # Fetch context by ID
            contexts = await Context.get_by_ids(db_conn, ids=[self.context_id])

            if not contexts:
                return None

            context = contexts[0]
            context.decrypt_content(chat_encryption_key=self.encryption_key)

            return context
