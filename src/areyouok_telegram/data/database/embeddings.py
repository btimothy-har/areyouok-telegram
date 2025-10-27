from llama_index.core import VectorStoreIndex
from llama_index.storage.docstore.postgres import PostgresDocumentStore
from llama_index.vector_stores.postgres import PGVectorStore
from sqlalchemy import make_url
from sqlalchemy.orm import declarative_base

from areyouok_telegram.config import ENV, PG_CONNECTION_STRING, RAG_EMBEDDING_DIMENSIONS

Base = declarative_base()

url = make_url(f"postgresql+asyncpg://{PG_CONNECTION_STRING}")


# Initialize PostgreSQL vector store for embeddings
context_vector_store = PGVectorStore.from_params(
    database=url.database,
    host=url.host,
    password=url.password,
    port=url.port,
    user=url.username,
    table_name="context_embeddings",
    schema_name=ENV,
    embed_dim=RAG_EMBEDDING_DIMENSIONS,
    hnsw_kwargs={
        "hnsw_m": 16,
        "hnsw_ef_construction": 64,
        "hnsw_ef_search": 40,
        "hnsw_dist_method": "vector_cosine_ops",
    },
)

# Initialize PostgreSQL document store for duplicate detection
# Tracks document IDs to avoid re-indexing duplicates
context_doc_store = PostgresDocumentStore.from_params(
    host=url.host,
    port=url.port,
    database=url.database,
    user=url.username,
    password=url.password,
    table_name="context_docstore",
    schema_name=ENV,
    namespace="context_documents",
)

# Initialize vector index
context_vector_index = VectorStoreIndex.from_vector_store(
    context_vector_store,
    use_async=True,
)

# retriever = index.as_retriever()
# nodes = retriever.retrieve("Who is Paul Graham?")
