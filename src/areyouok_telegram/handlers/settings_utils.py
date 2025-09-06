from areyouok_telegram.data import UserMetadata
from areyouok_telegram.data import async_database
from areyouok_telegram.handlers.constants import SETTINGS_DISPLAY_TEMPLATE
from areyouok_telegram.llms.agent_settings import SettingsAgentDependencies
from areyouok_telegram.llms.agent_settings import SettingsUpdateResponse
from areyouok_telegram.llms.agent_settings import settings_agent
from areyouok_telegram.llms.utils import run_agent_with_tracking
from areyouok_telegram.utils import escape_markdown_v2


async def update_user_metadata_field(
    *,
    chat_id: str,
    session_id: str,
    field_name: str,
    new_value: str,
) -> SettingsUpdateResponse:
    update_instruction = f"Update {field_name} to {new_value}."

    update = await run_agent_with_tracking(
        settings_agent,
        chat_id=chat_id,
        session_id=session_id,
        run_kwargs={
            "user_prompt": update_instruction,
            "deps": SettingsAgentDependencies(
                tg_chat_id=chat_id,
                tg_session_id=session_id,
            ),
        },
    )
    update_outcome: SettingsUpdateResponse = update.output

    return update_outcome


async def construct_user_settings_response(user_id: str):
    async with async_database() as db_conn:
        # Get user metadata
        user_metadata = await UserMetadata.get_by_user_id(
            db_conn,
            user_id=user_id,
        )

        # Format settings display
        if user_metadata:
            name = user_metadata.preferred_name or "Not set"
            country = user_metadata.country or "Not set"
            timezone = user_metadata.timezone or "Not set"

            # Handle "rather_not_say" values
            if country == "rather_not_say":
                country = "Prefer not to say"
            if timezone == "rather_not_say":
                timezone = "Prefer not to say"
        else:
            name = "Not set"
            country = "Not set"
            timezone = "Not set"

        settings_text = SETTINGS_DISPLAY_TEMPLATE.format(
            name=escape_markdown_v2(name),
            country=escape_markdown_v2(country),
            timezone=escape_markdown_v2(timezone),
        )

    return settings_text
