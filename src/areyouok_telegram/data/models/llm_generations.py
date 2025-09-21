"""Model for tracking LLM generation outputs and metadata."""

import hashlib
import json
from datetime import UTC
from datetime import datetime
from typing import Any

from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from areyouok_telegram.config import ENV
from areyouok_telegram.data import Base
from areyouok_telegram.encryption.content import decrypt_content
from areyouok_telegram.encryption.content import encrypt_content
from areyouok_telegram.logging import traced


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
    agent = Column(String, nullable=False)  # Agent name that generated the response
    timestamp = Column(TIMESTAMP(timezone=True), nullable=False)

    # Response data
    response_type = Column(String, nullable=False)  # TextResponse, ReactionResponse, etc.
    encrypted_payload = Column(Text, nullable=False)  # Full response object encrypted

    @staticmethod
    def generate_generation_id(chat_id: str, session_id: str, timestamp: datetime, agent: str) -> str:
        """Generate a unique ID for a generation based on chat, session, timestamp, and agent."""
        timestamp_str = timestamp.isoformat()
        return hashlib.sha256(f"{chat_id}:{session_id}:{timestamp_str}:{agent}".encode()).hexdigest()

    @property
    def payload(self) -> Any:
        """Get the decrypted payload.

        Returns:
            The decrypted and deserialized payload. For structured responses,
            returns the original dict. For other types, returns the original value.

        Note:
            This method decrypts the payload each time it's called.
            Consider caching the result if accessed frequently.
        """
        decrypted_content = decrypt_content(self.encrypted_payload)
        try:
            return json.loads(decrypted_content)
        except (json.JSONDecodeError, TypeError):
            # If JSON parsing fails, return the raw content
            return decrypted_content

    @classmethod
    @traced(extract_args=["chat_id", "session_id", "agent"])
    async def create(
        cls,
        db_conn: AsyncSession,
        *,
        chat_id: str,
        session_id: str,
        agent: str,
        response: Any,  # Any response object - we'll handle serialization
    ) -> "LLMGenerations":
        """Create a new LLM generation record with encrypted payload.

        Args:
            db_conn: Database connection
            chat_id: Chat ID
            session_id: Session ID
            agent: Name of the agent that generated the response
            response: The response object to serialize and store

        Returns:
            The created LLMGenerations instance
        """
        now = datetime.now(UTC)
        generation_id = cls.generate_generation_id(chat_id, session_id, now, agent)

        # Handle serialization based on response type
        if hasattr(response, "model_dump"):
            # Structured response object (e.g., TextResponse, ReactionResponse)
            response_type = getattr(response, "response_type", response.__class__.__name__)
            payload_content = json.dumps(response.model_dump())
        else:
            # All other types - strings, primitives, objects
            response_type = f"{response.__class__.__name__}Response"
            try:
                payload_content = json.dumps(response)
            except (TypeError, ValueError):
                # Fallback to string representation if serialization fails
                payload_content = str(response)

        # Encrypt the payload using application-level encryption
        encrypted_payload = encrypt_content(payload_content)

        stmt = pg_insert(cls).values(
            generation_id=generation_id,
            chat_id=chat_id,
            session_id=session_id,
            agent=agent,
            timestamp=now,
            response_type=response_type,
            encrypted_payload=encrypted_payload,
        )

        await db_conn.execute(stmt)

        # Return the instance
        generation = cls(
            generation_id=generation_id,
            chat_id=chat_id,
            session_id=session_id,
            agent=agent,
            timestamp=now,
            response_type=response_type,
            encrypted_payload=encrypted_payload,
        )

        return generation

    @classmethod
    @traced(extract_args=["chat_id", "session_id"])
    async def get_by_session(
        cls,
        db_conn: AsyncSession,
        *,
        chat_id: str,
        session_id: str,
    ) -> list["LLMGenerations"]:
        """Retrieve all generations for a specific chat and session.

        Args:
            db_conn: Database connection
            chat_id: Chat ID to filter by
            session_id: Session ID to filter by

        Returns:
            List of LLMGenerations instances
        """
        stmt = (
            select(cls)
            .where(
                cls.chat_id == chat_id,
                cls.session_id == session_id,
            )
            .order_by(cls.timestamp)
        )

        result = await db_conn.execute(stmt)
        generations = result.scalars().all()

        return list(generations)
