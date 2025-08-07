from datetime import UTC
from datetime import datetime

import logfire
import pydantic_ai
from sqlalchemy import Column
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from areyouok_telegram.config import ENV
from areyouok_telegram.data import Base
from areyouok_telegram.utils import traced


class LLMUsage(Base):
    __tablename__ = "llm_usage"
    __table_args__ = (
        Index("idx_llm_usage_chat_id", "chat_id"),
        Index("idx_llm_usage_session_id", "session_id"),
        Index("idx_llm_usage_timestamp", "timestamp"),
        Index("idx_llm_usage_chat_timestamp", "chat_id", "timestamp"),
        {"schema": ENV},
    )

    chat_id = Column(String, nullable=False)
    session_id = Column(String, nullable=False)
    timestamp = Column(TIMESTAMP(timezone=True), nullable=False)
    usage_type = Column(String, nullable=False)

    model = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)

    id = Column(Integer, primary_key=True, autoincrement=True)

    @classmethod
    @traced(extract_args=["chat_id", "session_id", "agent", "data"])
    async def track_pydantic_usage(
        cls,
        db_conn: AsyncSession,
        chat_id: str,
        session_id: str,
        agent: pydantic_ai.Agent,
        data: pydantic_ai.usage.Usage,
    ) -> int:
        """Log usage data from pydantic in the database."""

        if agent.model.model_name.startswith("fallback:"):
            model = agent.model.models[0]
        else:
            model = agent.model

        if model.model_name.count("/") == 0:
            # If the model name does not contain a provider prefix, prefix the system
            model_name = f"{model.system}/{model.model_name}"
        else:
            model_name = model.model_name

        try:
            now = datetime.now(UTC)

            stmt = pg_insert(cls).values(
                chat_id=str(chat_id),
                session_id=session_id,
                timestamp=now,
                usage_type=f"pydantic.{agent.name}",
                model=model_name,
                provider=model_name.split("/", 1)[0],
                input_tokens=data.request_tokens,
                output_tokens=data.response_tokens,
            )

            result = await db_conn.execute(stmt)

        # Catch exceptions here to avoid breaking application flow
        # This is a best-effort logging, so we log the exception but don't raise it
        except Exception as e:
            logfire.exception(f"Failed to insert pydantic usage record: {e}")
            return 0

        return result.rowcount
