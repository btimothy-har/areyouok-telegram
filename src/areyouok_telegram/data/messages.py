import hashlib

from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import TIMESTAMP

from areyouok_telegram.config import ENV
from areyouok_telegram.data.connection import Base


class Messages(Base):
    __tablename__ = "messages"
    __table_args__ = {"schema": ENV}

    num = Column(Integer, primary_key=True, autoincrement=True)
    message_key = Column(String, nullable=False, unique=True)
    message_id = Column(String, nullable=False)
    user_id = Column(String, nullable=False)
    chat_id = Column(String, nullable=False)
    payload = Column(JSONB, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)

    @staticmethod
    def generate_message_key(user_id: str, chat_id: str, message_id: int) -> str:
        """Generate a unique key for a message based on user ID, chat ID, and message ID."""
        return hashlib.sha256(f"{user_id}:{chat_id}:{message_id}".encode()).hexdigest()
