from llama_index.core import VectorStoreIndex
from llama_index.storage.docstore.postgres import PostgresDocumentStore
from llama_index.storage.kvstore.postgres import PostgresKVStore
from llama_index.vector_stores.postgres import PGVectorStore

from areyouok_telegram.config import ENV, RAG_EMBEDDING_DIMENSIONS
from areyouok_telegram.data.database.connection import async_engine, sync_engine

# Initialize PostgreSQL vector store for embeddings
# Pass shared engines to avoid creating separate connection pools
context_vector_store = PGVectorStore(
    table_name="context_embeddings",
    schema_name=ENV,
    embed_dim=RAG_EMBEDDING_DIMENSIONS,
    engine=sync_engine,
    async_engine=async_engine,
    perform_setup=True,
    use_jsonb=True,
    hnsw_kwargs={
        "hnsw_m": 16,
        "hnsw_ef_construction": 64,
        "hnsw_ef_search": 40,
        "hnsw_dist_method": "vector_cosine_ops",
    },
)

# Initialize PostgreSQL KV store with shared engines
# This prevents LlamaIndex from creating its own connection pools
context_kv_store = PostgresKVStore(
    table_name="context_docstore",
    schema_name=ENV,
    engine=sync_engine,
    async_engine=async_engine,
    perform_setup=True,
    use_jsonb=True,
)

# Initialize document store using the shared KV store
context_doc_store = PostgresDocumentStore(
    postgres_kvstore=context_kv_store,
    namespace="context_documents",
)

# Initialize vector index
context_vector_index = VectorStoreIndex.from_vector_store(
    context_vector_store,
    use_async=True,
)

# retriever = index.as_retriever()
# nodes = retriever.retrieve("Who is Paul Graham?")
