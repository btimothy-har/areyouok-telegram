from areyouok_telegram.utils import shorten_url

PERSONALITY_FEEDBACK_URL = "https://docs.google.com/forms/d/e/1FAIpQLSetAAqBeLnnjpW39Z5sVeDVjaVbrR-OEJ_tE8OhMIvKVmtV_A/viewform?usp=pp_url&&entry.1140367297={session_id}&entry.604567897={metadata}&pageHistory=0,1,2,3"


async def generate_feedback_url(session_id: str, metadata: str) -> str:
    """
    Generate a feedback URL with session ID and metadata.

    Args:
        session_id (str): The session ID to include in the URL.
        metadata (str): Additional metadata to include in the URL.

    Returns:
        str: The generated feedback URL.
    """
    raw_url = PERSONALITY_FEEDBACK_URL.format(
        session_id=session_id,
        metadata=metadata.upper(),
    )

    return await shorten_url(raw_url)
