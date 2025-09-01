"""Local test configuration for models tests to avoid freezegun/pydantic conflicts."""

import pytest


@pytest.fixture(autouse=True)
def disable_frozen_time():
    """Disable the frozen time fixture for model tests to avoid pydantic conflicts."""
    yield
