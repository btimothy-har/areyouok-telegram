"""LLM-related schemas for usage tracking and generation history."""

from sqlalchemy import Column, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP

from areyouok_telegram.config import ENV
from areyouok_telegram.data.database import Base


class LLMUsageTable(Base):
    """Track LLM token usage and costs."""

    __tablename__ = "llm_usage"
    __table_args__ = (
        Index("idx_llm_usage_chat_id", "chat_id"),
        Index("idx_llm_usage_session_id", "session_id"),
        Index("idx_llm_usage_timestamp", "timestamp"),
        Index("idx_llm_usage_chat_timestamp", "chat_id", "timestamp"),
        {"schema": ENV},
    )

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign keys
    chat_id = Column(Integer, ForeignKey(f"{ENV}.chats.id"), nullable=False)
    session_id = Column(Integer, ForeignKey(f"{ENV}.sessions.id"), nullable=False)

    # Usage metadata
    timestamp = Column(TIMESTAMP(timezone=True), nullable=False)
    usage_type = Column(String, nullable=False)

    # Model information
    model = Column(String, nullable=False)
    provider = Column(String, nullable=False)

    # Token counts
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)

    # Performance
    runtime = Column(Float, nullable=False)
    details = Column(JSONB, nullable=True)

    # Cost tracking (in USD)
    input_cost = Column(Float, nullable=True)
    output_cost = Column(Float, nullable=True)
    total_cost = Column(Float, nullable=True)


class LLMGenerationsTable(Base):
    """Track LLM generation outputs."""

    __tablename__ = "llm_generations"
    __table_args__ = {"schema": ENV}

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Unique identifier
    object_key = Column(String, unique=True, nullable=False, index=True)

    # Foreign keys
    chat_id = Column(Integer, ForeignKey(f"{ENV}.chats.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey(f"{ENV}.sessions.id"), nullable=False, index=True)

    # Generation metadata
    agent = Column(String, nullable=False)
    model = Column(String, nullable=False)
    timestamp = Column(TIMESTAMP(timezone=True), nullable=False)

    # Response data (unencrypted)
    response_type = Column(String, nullable=False)
    output = Column(JSONB, nullable=False)
    messages = Column(JSONB, nullable=False)
    deps = Column(JSONB, nullable=True)
