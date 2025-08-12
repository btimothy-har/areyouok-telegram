import pydantic_ai
import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.data import Sessions
from areyouok_telegram.data import async_database
from areyouok_telegram.llms.chat import chat_agent
from areyouok_telegram.llms.models import CHAT_GPT_5
from areyouok_telegram.llms.models import CHAT_SONNET_3_5
from areyouok_telegram.llms.models import CHAT_SONNET_4
from areyouok_telegram.research.model import ResearchScenario
from areyouok_telegram.utils import db_retry
from areyouok_telegram.utils import telegram_retry

from .constants import FEEDBACK_REQUEST
from .constants import NO_FEEDBACK_REQUEST
from .studies.personality_scenarios import PERSONALITY_SCENARIOS
from .utils import generate_feedback_url

MODEL_MAP = {
    "sonnet-4": CHAT_SONNET_4.model,
    "sonnet-3.5": CHAT_SONNET_3_5.model,
    "gpt-5": CHAT_GPT_5.model,
}


@db_retry()
async def generate_agent_for_research_session(
    chat_session: Sessions,
) -> pydantic_ai.Agent:
    """Insert a research scenario for a session, or return existing if already present.

    Args:
        db_conn: The database connection to use for the query.
        session_id: The unique session identifier to associate the scenario with.

    Returns:
        The ResearchScenario object, either newly created or existing.
    """
    agent = chat_agent

    async with async_database() as db_conn:
        scenario = await ResearchScenario.get_for_session_id(
            db_conn=db_conn,
            session_id=chat_session.session_id,
        )

    model = PERSONALITY_SCENARIOS.get(scenario.scenario_config, {}).get("model", None)

    if model:
        agent.model = MODEL_MAP.get(model, CHAT_SONNET_4.model)

    return agent


@telegram_retry()
async def close_research_session(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    chat_session: Sessions,
) -> None:
    """Close the research session and clean up any resources."""
    async with async_database() as db_conn:
        raw_messages = await chat_session.get_messages(db_conn)

        if len(raw_messages) <= 5:
            await context.bot.send_message(
                chat_id=chat_session.chat_id,
                text=NO_FEEDBACK_REQUEST,
            )
        else:
            scenario = await ResearchScenario.get_for_session_id(
                db_conn=db_conn,
                session_id=chat_session.session_id,
            )
            feedback_url = await generate_feedback_url(
                session_id=chat_session.session_id,
                metadata=scenario.scenario_config if scenario else "No scenario",
            )
            await context.bot.send_message(
                chat_id=chat_session.chat_id,
                text=FEEDBACK_REQUEST.format(feedback_url=feedback_url),
                link_preview_options=telegram.LinkPreviewOptions(is_disabled=False, show_above_text=False),
            )
