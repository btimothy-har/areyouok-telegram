"""LLMUsage Pydantic model for tracking LLM token usage and costs."""

from __future__ import annotations

from datetime import UTC, datetime

import logfire
import pydantic
import pydantic_ai
from genai_prices import Usage, calc_price
from sqlalchemy.dialects.postgresql import insert as pg_insert

from areyouok_telegram.data.database import async_database
from areyouok_telegram.data.database.schemas import LLMUsageTable
from areyouok_telegram.logging import traced
from areyouok_telegram.utils.retry import db_retry


class LLMUsage(pydantic.BaseModel):
    """Model for tracking LLM token usage and costs."""

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    # Foreign keys
    chat_id: int
    session_id: int | None

    # Usage metadata
    timestamp: datetime
    usage_type: str

    # Model information
    model: str
    provider: str

    # Token counts
    input_tokens: int = 0
    output_tokens: int = 0

    # Performance
    runtime: float = 0.0
    details: dict | None = None

    # Cost tracking (in USD)
    input_cost: float | None = None
    output_cost: float | None = None
    total_cost: float | None = None

    # Internal ID
    id: int = 0

    @traced()
    @db_retry()
    async def save(self) -> LLMUsage:
        """Save the LLM usage record to the database.

        Returns:
            LLMUsage instance with id populated
        """
        async with async_database() as db_conn:
            stmt = (
                pg_insert(LLMUsageTable)
                .values(
                    chat_id=self.chat_id,
                    session_id=self.session_id,
                    timestamp=self.timestamp,
                    usage_type=self.usage_type,
                    model=self.model,
                    provider=self.provider,
                    input_tokens=self.input_tokens,
                    output_tokens=self.output_tokens,
                    runtime=self.runtime,
                    details=self.details,
                    input_cost=self.input_cost,
                    output_cost=self.output_cost,
                    total_cost=self.total_cost,
                )
                .returning(LLMUsageTable)
            )

            result = await db_conn.execute(stmt)
            row = result.scalar_one()

            # Update self with the database-generated id
            self.id = row.id

            return self

    @classmethod
    def from_pydantic_usage(
        cls,
        *,
        chat_id: int,
        session_id: int | None,
        agent: pydantic_ai.Agent,
        data: pydantic_ai.usage.RunUsage,
        runtime: float,
    ) -> LLMUsage:
        """Create an LLMUsage instance from pydantic_ai usage data.

        Args:
            chat_id: Internal chat ID (FK to chats.id)
            session_id: Internal session ID (FK to sessions.id), or None for background jobs
            agent: pydantic_ai Agent object
            data: RunUsage data from pydantic_ai
            runtime: Generation runtime in seconds

        Returns:
            LLMUsage instance (not yet saved to database)
        """
        if agent.model.model_name.startswith("fallback:"):
            model = agent.model.models[0]
        else:
            model = agent.model

        model_name = model.model_name.split("/", 1)[-1]

        # Calculate costs using genai-prices
        input_cost, output_cost, total_cost = cls.calculate_costs(
            model_name=model_name,
            provider=model.system,
            input_tokens=data.input_tokens,
            output_tokens=data.output_tokens,
        )

        return cls(
            chat_id=chat_id,
            session_id=session_id,
            timestamp=datetime.now(UTC),
            usage_type=f"pydantic.{agent.name}",
            model=model_name,
            provider=model.system,
            input_tokens=data.input_tokens,
            output_tokens=data.output_tokens,
            runtime=runtime,
            details=data.details if data.details else None,
            input_cost=input_cost,
            output_cost=output_cost,
            total_cost=total_cost,
        )

    @staticmethod
    def calculate_costs(
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
