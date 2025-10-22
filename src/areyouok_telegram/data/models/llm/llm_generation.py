"""LLMGeneration Pydantic model for tracking LLM generation outputs."""

import dataclasses
import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import pydantic
import pydantic_ai
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from areyouok_telegram.data.database import async_database
from areyouok_telegram.data.database.schemas import LLMGenerationsTable
from areyouok_telegram.logging import traced


def serialize_object(obj: Any) -> str:
    """Serialize an object to JSON string or string representation.

    Args:
        obj: Object to serialize

    Returns:
        Serialized string representation
    """
    if obj is None:
        return ""

    try:
        # Try Pydantic model first
        if isinstance(obj, pydantic.BaseModel):
            return json.dumps(obj.model_dump())

        # Try object with __dict__
        if dataclasses.is_dataclass(obj):
            if hasattr(obj, "to_dict"):
                return json.dumps(obj.to_dict())
            else:
                return json.dumps(dataclasses.asdict(obj))

        return json.dumps(obj)

    except (TypeError, ValueError):
        return str(obj)


class LLMGeneration(pydantic.BaseModel):
    """Model for tracking LLM generation outputs."""

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    # Foreign keys
    chat_id: int
    session_id: int

    # Generation metadata
    agent: str
    model: str
    timestamp: datetime

    # Response data
    response_type: str
    output: Any
    messages: list[pydantic_ai.messages.ModelMessage]
    deps: Any | None = None

    # Internal ID
    id: int = 0

    @property
    def object_key(self) -> str:
        """Generate a unique object key for a generation based on chat, session, timestamp, and agent."""
        timestamp_str = self.timestamp.isoformat()
        return hashlib.sha256(
            f"llm_gen:{self.chat_id}:{self.session_id}:{timestamp_str}:{self.agent}".encode()
        ).hexdigest()

    @staticmethod
    def _deserialize_from_storage(
        output_data: dict, messages_data: list, deps_data: dict | None
    ) -> tuple[Any, list[pydantic_ai.messages.ModelMessage], Any | None]:
        """Deserialize data from JSONB storage.

        Args:
            output_data: Output dictionary
            messages_data: Messages list
            deps_data: Dependencies dictionary (or None)

        Returns:
            Tuple of (output, messages, deps)
        """
        # Parse messages
        messages = pydantic_ai.messages.ModelMessagesTypeAdapter.validate_python(messages_data)

        return output_data, messages, deps_data

    def _serialize_for_storage(self) -> tuple[dict, list[dict], dict | None]:
        """Serialize data for JSONB storage.

        Returns:
            Tuple of (output_dict, messages_list, deps_dict)
        """
        # Serialize output
        output_dict = json.loads(serialize_object(self.output))

        # Serialize messages to list of dicts
        messages_json = json.loads(
            json.dumps([m.model_dump() if hasattr(m, "model_dump") else m for m in self.messages])
        )

        # Serialize deps
        deps_dict = json.loads(serialize_object(self.deps)) if self.deps else None

        return output_dict, messages_json, deps_dict

    @traced()
    async def save(self) -> "LLMGeneration":
        """Save the LLM generation to the database.

        Returns:
            LLMGeneration instance refreshed from database
        """
        # Serialize content for storage
        output_dict, messages_list, deps_dict = self._serialize_for_storage()

        async with async_database() as db_conn:
            stmt = (
                pg_insert(LLMGenerationsTable)
                .values(
                    object_key=self.object_key,
                    chat_id=self.chat_id,
                    session_id=self.session_id,
                    agent=self.agent,
                    model=self.model,
                    timestamp=self.timestamp,
                    response_type=self.response_type,
                    output=output_dict,
                    messages=messages_list,
                    deps=deps_dict,
                )
                .returning(LLMGenerationsTable)
            )

            result = await db_conn.execute(stmt)
            row = result.scalar_one()

            # Deserialize and return
            output, messages, deps = self._deserialize_from_storage(row.output, row.messages, row.deps)

            return LLMGeneration(
                id=row.id,
                chat_id=row.chat_id,
                session_id=row.session_id,
                agent=row.agent,
                model=row.model,
                timestamp=row.timestamp,
                response_type=row.response_type,
                output=output,
                messages=messages,
                deps=deps,
            )

    @classmethod
    def from_agent_run(
        cls,
        *,
        chat_id: int,
        session_id: int,
        agent: pydantic_ai.Agent,
        run_result: pydantic_ai.agent.AgentRunResult,
        run_deps: Any = None,
    ) -> "LLMGeneration":
        """Create an LLMGeneration instance from an agent run result.

        Args:
            chat_id: Internal chat ID (FK to chats.id)
            session_id: Internal session ID (FK to sessions.id)
            agent: pydantic_ai.Agent object
            run_result: The agent run result to serialize and store
            run_deps: Optional dependencies passed to agent.run()

        Returns:
            LLMGeneration instance (not yet saved to database)
        """
        agent_name = agent.name

        # Extract model name using the same logic as LLMUsage
        if agent.model.model_name.startswith("fallback:"):
            model = agent.model.models[0]
        else:
            model = agent.model

        if model.model_name.count("/") == 0:
            # If the model name does not contain a provider prefix, prefix the system
            model_name = f"{model.system}/{model.model_name}"
        else:
            model_name = model.model_name

        # Parse messages from JSON bytes
        messages_json = json.loads(run_result.all_messages_json().decode("utf-8"))
        messages = pydantic_ai.messages.ModelMessagesTypeAdapter.validate_python(messages_json)

        return cls(
            chat_id=chat_id,
            session_id=session_id,
            agent=agent_name,
            model=model_name,
            timestamp=datetime.now(UTC),
            response_type=run_result.output.__class__.__name__,
            output=run_result.output,
            messages=messages,
            deps=run_deps,
        )

    @classmethod
    @traced(extract_args=["generation_id"])
    async def get_by_id(
        cls,
        *,
        generation_id: int,
    ) -> "LLMGeneration | None":
        """Retrieve a generation by its internal ID.

        Args:
            generation_id: Internal generation ID

        Returns:
            LLMGeneration instance if found, None otherwise
        """
        async with async_database() as db_conn:
            stmt = select(LLMGenerationsTable).where(LLMGenerationsTable.id == generation_id)

            result = await db_conn.execute(stmt)
            row = result.scalar_one_or_none()

            if row is None:
                return None

            # Deserialize content
            output, messages, deps = cls._deserialize_from_storage(row.output, row.messages, row.deps)

            return cls(
                id=row.id,
                chat_id=row.chat_id,
                session_id=row.session_id,
                agent=row.agent,
                model=row.model,
                timestamp=row.timestamp,
                response_type=row.response_type,
                output=output,
                messages=messages,
                deps=deps,
            )

    @classmethod
    @traced(extract_args=["session_id"])
    async def get_by_session(
        cls,
        *,
        session_id: int,
    ) -> list["LLMGeneration"]:
        """Retrieve all generations for a specific session.

        Args:
            session_id: Internal session ID (FK to sessions.id)

        Returns:
            List of LLMGeneration instances
        """
        async with async_database() as db_conn:
            stmt = (
                select(LLMGenerationsTable)
                .where(LLMGenerationsTable.session_id == session_id)
                .order_by(LLMGenerationsTable.timestamp)
            )

            result = await db_conn.execute(stmt)
            rows = result.scalars().all()

            generations = []
            for row in rows:
                # Deserialize content
                output, messages, deps = cls._deserialize_from_storage(row.output, row.messages, row.deps)

                generation = cls(
                    id=row.id,
                    chat_id=row.chat_id,
                    session_id=row.session_id,
                    agent=row.agent,
                    model=row.model,
                    timestamp=row.timestamp,
                    response_type=row.response_type,
                    output=output,
                    messages=messages,
                    deps=deps,
                )
                generations.append(generation)

            return generations
