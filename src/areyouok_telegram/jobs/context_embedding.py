"""Background job for indexing Context records into LlamaIndex vector store."""

from datetime import UTC
from datetime import datetime

import logfire
from llama_index.core import Document
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.schema import TransformComponent
from llama_index.embeddings.openai import OpenAIEmbedding

from areyouok_telegram.config import OPENAI_API_KEY
from areyouok_telegram.config import RAG_BATCH_SIZE
from areyouok_telegram.config import RAG_EMBEDDING_DIMENSIONS
from areyouok_telegram.config import RAG_EMBEDDING_MODEL
from areyouok_telegram.data import Chats
from areyouok_telegram.data import Context
from areyouok_telegram.data import ContextType
from areyouok_telegram.data import async_database
from areyouok_telegram.data import context_doc_store
from areyouok_telegram.data import context_vector_store
from areyouok_telegram.jobs.base import BaseJob
from areyouok_telegram.logging import traced
from areyouok_telegram.utils import db_retry

CONTEXT_TYPES_TO_EMBED = [
    ContextType.SESSION.value,
]


class RedactNodeContent(TransformComponent):
    """Remove text content from nodes after embedding, keeping only metadata.

    This transformer runs after embedding generation to remove the actual text content,
    ensuring privacy while preserving embeddings and metadata for semantic search.
    """

    def __call__(self, nodes, **kwargs):  # noqa:ARG002
        """Redact text content while preserving embeddings and metadata."""
        for node in nodes:
            node.set_content("content_redacted")
        return nodes


embedding_model = OpenAIEmbedding(
    model=RAG_EMBEDDING_MODEL,
    embed_batch_size=RAG_BATCH_SIZE,
    dimensions=RAG_EMBEDDING_DIMENSIONS,
    api_key=OPENAI_API_KEY,
)

# Initialize IngestionPipeline with docstore for duplicate detection
pipeline = IngestionPipeline(
    transformations=[
        embedding_model,
        RedactNodeContent(),
    ],
    vector_store=context_vector_store,
    docstore=context_doc_store,  # Track doc IDs for duplicate detection
    docstore_strategy="upserts",  # Update existing documents if re-indexed
)


class ContextEmbeddingJob(BaseJob):
    """Batch job to embed Context records into LlamaIndex vector store.

    This job runs on a schedule (every 30 seconds by default) and processes
    all contexts created since the last run. Job state (last_run_time) is
    persisted to the database to survive bot restarts.
    """

    @property
    def name(self) -> str:
        """Generate job name."""
        return "context_embedding"

    @traced(extract_args=False)
    async def run_job(self) -> None:
        """Batch process contexts created since last run."""

        try:
            # Load persisted state
            state = await self.load_state()
            last_run_time_str = state.get("last_run_time")

            # Determine cutoff time (use epoch if first run)
            if last_run_time_str:
                cutoff_time = datetime.fromisoformat(last_run_time_str)
            else:
                cutoff_time = datetime(1970, 1, 1, tzinfo=UTC)

            # Fetch contexts created since last run
            new_contexts = await self._fetch_new_contexts(
                from_timestamp=cutoff_time,
                to_timestamp=self._run_timestamp,
            )
            documents: list[Document] = []

            if new_contexts:
                # Create documents batch
                for context in new_contexts:
                    if context.type not in CONTEXT_TYPES_TO_EMBED:
                        continue

                    encryption_key = await self._get_encryption_key(chat_id=context.chat_id)

                    # Decrypt content
                    context.decrypt_content(chat_encryption_key=encryption_key)

                    if not context.content:
                        continue

                    # Create Document
                    doc = Document(
                        text=str(context.content),
                        id_=str(context.id),
                        metadata={
                            "context_id": context.id,
                            "chat_id": context.chat_id,
                            "session_id": context.session_id,
                            "type": context.type,
                            "created_at": context.created_at.isoformat(),
                        },
                    )
                    documents.append(doc)

                await pipeline.arun(documents=documents)

            await self.save_state(
                last_run_time=self._run_timestamp.isoformat(),
                last_processed_count=len(documents),
            )

            logfire.info(
                f"Embedded {len(documents)} contexts.",
                count=len(documents),
                run_timestamp=self._run_timestamp.isoformat(),
            )

        except Exception:
            logfire.exception("Failed to run context embedding batch job")
            raise

    @db_retry()
    async def _fetch_new_contexts(
        self,
        *,
        from_timestamp: datetime,
        to_timestamp: datetime,
    ) -> list[Context]:
        """Fetch contexts created since given time with their encryption keys.

        Args:
            since: Datetime cutoff (get contexts created after this)

        Returns:
            List of [Context]
        """
        async with async_database() as db_conn:
            # Get contexts created since cutoff
            contexts = await Context.get_by_created_timestamp(
                db_conn,
                from_timestamp=from_timestamp,
                to_timestamp=to_timestamp,
            )

            if not contexts:
                return []

            return contexts

    @db_retry()
    async def _get_encryption_key(self, *, chat_id: str) -> str:
        """Get the encryption key for a chat."""
        async with async_database() as db_conn:
            chat = await Chats.get_by_id(db_conn, chat_id=chat_id)
            return chat.retrieve_key()
