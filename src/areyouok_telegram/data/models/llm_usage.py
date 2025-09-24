from datetime import UTC
from datetime import datetime

import logfire
import pydantic_ai
from genai_prices import Usage
from genai_prices import calc_price
from sqlalchemy import Column
from sqlalchemy import Float
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from areyouok_telegram.config import ENV
from areyouok_telegram.data import Base
from areyouok_telegram.logging import traced


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
    runtime = Column(Float, nullable=False)
    details = Column(JSONB, nullable=True)

    # Cost tracking columns (in USD)
    input_cost = Column(Float, nullable=True)
    output_cost = Column(Float, nullable=True)
    total_cost = Column(Float, nullable=True)

    id = Column(Integer, primary_key=True, autoincrement=True)

    @classmethod
    @traced(extract_args=["chat_id", "session_id", "agent", "data"])
    async def track_pydantic_usage(
        cls,
        db_conn: AsyncSession,
        *,
        chat_id: str,
        session_id: str,
        agent: pydantic_ai.Agent,
        data: pydantic_ai.usage.RunUsage,
        runtime: float,
    ) -> int:
        """Log usage data from pydantic in the database."""

        if agent.model.model_name.startswith("fallback:"):
            model = agent.model.models[0]
        else:
            model = agent.model

        model_name = model.model_name.split("/", 1)[-1]

        now = datetime.now(UTC)

        # Calculate costs using genai-prices
        input_cost, output_cost, total_cost = cls._calculate_costs(
            model_name=model_name,
            provider=model.system,
            input_tokens=data.request_tokens,
            output_tokens=data.response_tokens,
        )

        stmt = pg_insert(cls).values(
            chat_id=str(chat_id),
            session_id=session_id,
            timestamp=now,
            usage_type=f"pydantic.{agent.name}",
            model=model_name,
            provider=model.system,
            input_tokens=data.request_tokens,
            output_tokens=data.response_tokens,
            runtime=runtime,
            details=data.details if data.details else None,
            input_cost=input_cost,
            output_cost=output_cost,
            total_cost=total_cost,
        )

        result = await db_conn.execute(stmt)
        return result.rowcount

    @classmethod
    @traced(extract_args=["chat_id", "session_id", "usage_type", "model", "provider", "input_tokens", "output_tokens"])
    async def track_generic_usage(
        cls,
        db_conn: AsyncSession,
        *,
        chat_id: str = None,
        session_id: str = None,
        usage_type: str = None,
        model: str = None,
        provider: str = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        runtime: float = 0.0,
    ) -> int:
        """Log generic usage data in the database."""

        now = datetime.now(UTC)

        stmt = pg_insert(cls).values(
            chat_id=str(chat_id),
            session_id=session_id,
            timestamp=now,
            usage_type=usage_type,
            model=model,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            runtime=runtime,
            details=None,
            input_cost=None,
            output_cost=None,
            total_cost=None,
        )

        result = await db_conn.execute(stmt)
        return result.rowcount

    @classmethod
    def _calculate_costs(
        cls,
        *,
        model_name: str,
        provider: str,
        input_tokens: int,
        output_tokens: int,
    ) -> tuple[float | None, float | None, float | None]:
        """Calculate input, output, and total costs using genai-prices.

        Returns:
            Tuple of (input_cost, output_cost, total_cost) in USD, or (None, None, None) if calculation fails.
        """
        try:
            # Create Usage object for genai-prices
            usage = Usage(input_tokens=input_tokens, output_tokens=output_tokens)

            # Calculate price using genai-prices
            price_data = calc_price(usage, model_ref=model_name, provider_id=provider)

            # Store costs directly from genai-prices, converting Decimals to floats
            return float(price_data.input_price), float(price_data.output_price), float(price_data.total_price)

        except Exception as e:
            # Log the error but don't raise - we want to continue tracking usage even if pricing fails
            logfire.warn(f"Failed to calculate costs for model {model_name}: {e}")

        return None, None, None
