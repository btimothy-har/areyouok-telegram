"""Model for tracking LLM generation outputs and metadata."""

import dataclasses
import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import pydantic
import pydantic_ai
from sqlalchemy import Column, Integer, String, Text, select
from sqlalchemy.dialects.postgresql import TIMESTAMP, insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from areyouok_telegram.config import ENV
from areyouok_telegram.data import Base
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


class LLMGenerations(Base):
    """Track LLM generation outputs with encrypted payloads."""

    __tablename__ = "llm_generations"
    __table_args__ = {"schema": ENV}

    # Primary identification
    id = Column(Integer, primary_key=True, autoincrement=True)
    generation_id = Column(String, unique=True, nullable=False)

    # Core fields
    chat_id = Column(String, nullable=False)
    session_id = Column(String, nullable=False)
    agent = Column(String, nullable=False)
    model = Column(String, nullable=False)
    timestamp = Column(TIMESTAMP(timezone=True), nullable=False)

    # Response data
    response_type = Column(String, nullable=False)
    encrypted_output = Column(Text, nullable=False)
    encrypted_messages = Column(Text, nullable=False)
    encrypted_deps = Column(Text, nullable=True)

    @staticmethod
    def generate_generation_id(chat_id: str, session_id: str, timestamp: datetime, agent: str) -> str:
        """Generate a unique ID for a generation based on chat, session, timestamp, and agent."""
        timestamp_str = timestamp.isoformat()
        return hashlib.sha256(f"{chat_id}:{session_id}:{timestamp_str}:{agent}".encode()).hexdigest()

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
        db_conn: AsyncSession,
        *,
        chat_id: str,
        session_id: str,
        agent: pydantic_ai.Agent,
        run_result: pydantic_ai.agent.AgentRunResult,
        run_deps: Any = None,
    ) -> None:
        """Create a new LLM generation record with encrypted payload.

        Args:
            db_conn: Database connection
            chat_id: Chat ID
            session_id: Session ID
            agent: pydantic_ai.Agent object
            response: The response object to serialize and store
            duration: Generation duration in seconds
            deps: Optional dependencies passed to agent.run()
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

        generation_id = cls.generate_generation_id(chat_id, session_id, now, agent_name)

        stmt = pg_insert(cls).values(
            generation_id=generation_id,
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

        await db_conn.execute(stmt)

    @classmethod
    @traced(extract_args=["generation_id"])
    async def get_by_generation_id(
        cls,
        db_conn: AsyncSession,
        *,
        generation_id: str,
    ) -> "LLMGenerations | None":
        """Retrieve a generation by its generation_id.

        Args:
            db_conn: Database connection
            generation_id: Generation ID to filter by

        Returns:
            LLMGenerations instance if found, None otherwise
        """
        stmt = select(cls).where(cls.generation_id == generation_id)

        result = await db_conn.execute(stmt)
        generation = result.scalar_one_or_none()

        return generation

    @classmethod
    @traced(extract_args=["session_id"])
    async def get_by_session(
        cls,
        db_conn: AsyncSession,
        *,
        session_id: str,
    ) -> list["LLMGenerations"]:
        """Retrieve all generations for a specific session.

        Args:
            db_conn: Database connection
            session_id: Session ID to filter by

        Returns:
            List of LLMGenerations instances
        """
        stmt = select(cls).where(cls.session_id == session_id).order_by(cls.timestamp)

        result = await db_conn.execute(stmt)
        generations = result.scalars().all()

        return list(generations)
