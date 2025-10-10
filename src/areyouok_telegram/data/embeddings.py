from llama_index.core import VectorStoreIndex
from llama_index.vector_stores.postgres import PGVectorStore
from sqlalchemy import make_url
from sqlalchemy.orm import declarative_base

from areyouok_telegram.config import ENV
from areyouok_telegram.config import PG_CONNECTION_STRING

Base = declarative_base()

url = make_url(f"postgresql+asyncpg://{PG_CONNECTION_STRING}")


context_vector_store = PGVectorStore.from_params(
    database=url.database,
    host=url.host,
    password=url.password,
    port=url.port,
    user=url.username,
    table_name=f"{ENV}_context_embeddings",
    embed_dim=1536,
    hnsw_kwargs={
        "hnsw_m": 16,
        "hnsw_ef_construction": 64,
        "hnsw_ef_search": 40,
        "hnsw_dist_method": "vector_cosine_ops",
    },
)

context_vector_index = VectorStoreIndex.from_vector_store(
    context_vector_store,
    use_async=True,
)

# retriever = index.as_retriever()
# nodes = retriever.retrieve("Who is Paul Graham?")
