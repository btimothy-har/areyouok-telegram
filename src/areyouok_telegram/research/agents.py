import pydantic_ai

from areyouok_telegram.data import Sessions
from areyouok_telegram.data import async_database
from areyouok_telegram.llms.chat import chat_agent
from areyouok_telegram.llms.models import CHAT_GPT_5
from areyouok_telegram.llms.models import CHAT_SONNET_3_5
from areyouok_telegram.llms.models import CHAT_SONNET_4
from areyouok_telegram.research.model import ResearchScenario

from .studies.personality_scenarios import PERSONALITY_SCENARIOS

MODEL_MAP = {
    "sonnet-4": CHAT_SONNET_4.model,
    "sonnet-3.5": CHAT_SONNET_3_5.model,
    "gpt-5": CHAT_GPT_5.model,
}


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
