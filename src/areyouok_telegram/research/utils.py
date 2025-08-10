from areyouok_telegram.config import FEEDBACK_URL
from areyouok_telegram.config import FORM_NUM_PAGES
from areyouok_telegram.config import METADATA_FIELD
from areyouok_telegram.config import SESSION_ID_FIELD
from areyouok_telegram.utils import shorten_url


async def generate_feedback_url(session_id: str, metadata: str) -> str:
    """
    Generate a feedback URL with session ID and metadata.

    Args:
        session_id (str): The session ID to include in the URL.
        metadata (str): Additional metadata to include in the URL.

    Returns:
        str: The generated feedback URL.
    """
    page_history = ",".join(str(i) for i in range(FORM_NUM_PAGES + 1))
    raw_url = (
        f"{FEEDBACK_URL}{SESSION_ID_FIELD}={session_id}{METADATA_FIELD}={metadata.upper()}&pageHistory={page_history}"
    )

    return await shorten_url(raw_url)
