"""LLMUsage Pydantic model for tracking LLM token usage and costs."""

from datetime import UTC, datetime

import logfire
import pydantic
import pydantic_ai
from genai_prices import Usage, calc_price
from sqlalchemy.dialects.postgresql import insert as pg_insert

from areyouok_telegram.data.database import async_database
from areyouok_telegram.data.database.schemas import LLMUsageTable
from areyouok_telegram.logging import traced


class LLMUsage(pydantic.BaseModel):
    """Model for tracking LLM token usage and costs."""

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    # Internal ID
    id: int

    # Foreign keys
    chat_id: int
    session_id: int

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
    runtime: float
    details: dict | None = None

    # Cost tracking (in USD)
    input_cost: float | None = None
    output_cost: float | None = None
    total_cost: float | None = None

    @classmethod
    @traced(extract_args=["chat_id", "session_id", "agent", "data"])
    async def track_pydantic_usage(
        cls,
        *,
        chat_id: int,
        session_id: int,
        agent: pydantic_ai.Agent,
        data: pydantic_ai.usage.RunUsage,
        runtime: float,
    ) -> int:
        """Log usage data from pydantic in the database.

        Args:
            chat_id: Internal chat ID (FK to chats.id)
            session_id: Internal session ID (FK to sessions.id)
            agent: pydantic_ai Agent object
            data: RunUsage data from pydantic_ai
            runtime: Generation runtime in seconds

        Returns:
            Number of rows inserted
        """
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

        async with async_database() as db_conn:
            stmt = pg_insert(LLMUsageTable).values(
                chat_id=chat_id,
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
        *,
        chat_id: int,
        session_id: int,
        usage_type: str,
        model: str,
        provider: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        runtime: float = 0.0,
    ) -> int:
        """Log generic usage data in the database.

        Args:
            chat_id: Internal chat ID (FK to chats.id)
            session_id: Internal session ID (FK to sessions.id)
            usage_type: Type of usage
            model: Model name
            provider: Provider name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            runtime: Runtime in seconds

        Returns:
            Number of rows inserted
        """
        now = datetime.now(UTC)

        async with async_database() as db_conn:
            stmt = pg_insert(LLMUsageTable).values(
                chat_id=chat_id,
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
