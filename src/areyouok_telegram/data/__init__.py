"""Data layer with database connection and models.

This module provides access to the data layer components:
- database: Database connection and schema definitions
- models: Pydantic data models organized by domain
- operations: High-level data operations and queries
- exceptions: Custom data layer exceptions

Usage:
    from areyouok_telegram.data.database import async_database, Base
    from areyouok_telegram.data.models import User, Session
    from areyouok_telegram.data import operations
"""

# Import submodules to make them available
from areyouok_telegram.data import database, exceptions, models, operations

__all__ = [
    "database",
    "models",
    "operations",
    "exceptions",
]
