import hashlib

from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import TIMESTAMP

from areyouok_telegram.config import ENV
from areyouok_telegram.data.connection import Base


class Updates(Base):
    __tablename__ = "updates"
    __table_args__ = {"schema": ENV}

    num = Column(Integer, primary_key=True, autoincrement=True)
    update_key = Column(String, nullable=False, unique=True)
    update_id = Column(String, nullable=False)
    payload = Column(JSONB, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)

    @staticmethod
    def generate_update_key(payload: str) -> str:
        """Generate a unique key for an update based on its payload."""
        return hashlib.sha256(payload.encode()).hexdigest()
