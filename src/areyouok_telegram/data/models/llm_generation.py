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
from areyouok_telegram.encryption.content import decrypt_content, encrypt_content
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
    """Model for tracking LLM generation outputs with encrypted payloads."""

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    # Internal ID
    id: int

    # Foreign keys
    chat_id: int
    session_id: int

    # Generation metadata
    agent: str
    model: str
    timestamp: datetime

    # Response data (encrypted)
    response_type: str
    encrypted_output: str
    encrypted_messages: str
    encrypted_deps: str | None = None

    @staticmethod
    def generate_object_key(chat_id: int, session_id: int, timestamp: datetime, agent: str) -> str:
        """Generate a unique object key for a generation based on chat, session, timestamp, and agent."""
        timestamp_str = timestamp.isoformat()
        return hashlib.sha256(f"llm_gen:{chat_id}:{session_id}:{timestamp_str}:{agent}".encode()).hexdigest()

    @property
    def run_messages(self) -> pydantic_ai.messages.ModelMessage:
        decrypted_content = decrypt_content(self.encrypted_messages)
        try:
            message_json = json.loads(decrypted_content)
            return pydantic_ai.messages.ModelMessagesTypeAdapter.validate_python(message_json)
        except (json.JSONDecodeError, TypeError):
            return decrypted_content

    @property
    def run_output(self) -> Any:
        decrypted_content = decrypt_content(self.encrypted_output)
        try:
            return json.loads(decrypted_content)
        except (json.JSONDecodeError, TypeError):
            # If JSON parsing fails, return the raw content
            return decrypted_content

    @property
    def run_deps(self) -> Any:
        if self.encrypted_deps is None:
            return None

        decrypted_content = decrypt_content(self.encrypted_deps)
        try:
            return json.loads(decrypted_content)
        except (json.JSONDecodeError, TypeError):
            # If JSON parsing fails, return the raw content
            return decrypted_content

    @classmethod
    @traced(extract_args=["chat_id", "session_id"])
    async def create(
        cls,
        *,
        chat_id: int,
        session_id: int,
        agent: pydantic_ai.Agent,
        run_result: pydantic_ai.agent.AgentRunResult,
        run_deps: Any = None,
    ) -> "LLMGeneration":
        """Create a new LLM generation record with encrypted payload.

        Args:
            chat_id: Internal chat ID (FK to chats.id)
            session_id: Internal session ID (FK to sessions.id)
            agent: pydantic_ai.Agent object
            run_result: The agent run result to serialize and store
            run_deps: Optional dependencies passed to agent.run()

        Returns:
            LLMGeneration instance
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

        now = datetime.now(UTC)
        object_key = cls.generate_object_key(chat_id, session_id, now, agent_name)

        async with async_database() as db_conn:
            stmt = (
                pg_insert(LLMGenerationsTable)
                .values(
                    object_key=object_key,
                    chat_id=chat_id,
                    session_id=session_id,
                    agent=agent_name,
                    model=model_name,
                    timestamp=now,
                    response_type=run_result.output.__class__.__name__,
                    encrypted_output=encrypt_content(serialize_object(run_result.output)),
                    encrypted_messages=encrypt_content(run_result.all_messages_json().decode("utf-8")),
                    encrypted_deps=encrypt_content(serialize_object(run_deps)) if run_deps else None,
                )
                .returning(LLMGenerationsTable)
            )

            result = await db_conn.execute(stmt)
            row = result.scalar_one()

            return cls.model_validate(row, from_attributes=True)

    @classmethod
    @traced(extract_args=["id"])
    async def get_by_id(
        cls,
        *,
        id: int,
    ) -> "LLMGeneration | None":
        """Retrieve a generation by its internal ID.

        Args:
            id: Internal generation ID

        Returns:
            LLMGeneration instance if found, None otherwise
        """
        async with async_database() as db_conn:
            stmt = select(LLMGenerationsTable).where(LLMGenerationsTable.id == id)

            result = await db_conn.execute(stmt)
            row = result.scalar_one_or_none()

            if row is None:
                return None

            return cls.model_validate(row, from_attributes=True)

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

            return [cls.model_validate(row, from_attributes=True) for row in rows]
