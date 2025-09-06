from dataclasses import dataclass

import pydantic
import pydantic_ai
from pydantic_ai import RunContext

from areyouok_telegram.data import UserMetadata
from areyouok_telegram.data import async_database
from areyouok_telegram.llms.exceptions import MetadataFieldUpdateError
from areyouok_telegram.llms.models import UTILITY_GPT_5_NANO
from areyouok_telegram.llms.utils import log_metadata_update_context


class FeedbackMissingError(pydantic_ai.ModelRetry):
    """Exception raised for missing feedback in model output."""

    def __init__(self):
        message = "Feedback is required when completed is False."
        super().__init__(message)


@dataclass
class SettingsAgentDependencies:
    """Dependencies for the onboarding agent."""

    tg_chat_id: str
    tg_session_id: str


class SettingsUpdateResponse(pydantic.BaseModel):
    """Model for user settings response."""

    completed: bool = pydantic.Field(description="Whether the update was successful.")
    feedback: str | None = pydantic.Field(
        description="Feedback or information that needs to be passed back to the user.", default=None
    )


settings_agent = pydantic_ai.Agent(
    model=UTILITY_GPT_5_NANO.model,
    output_type=SettingsUpdateResponse,
    name="settings_agent",
    end_strategy="exhaustive",
)


@settings_agent.instructions
def generate_instructions() -> str:
    return """
You are a backend agent responsible for managing user's settings and preferences. You are \
able to manage the following settings:
- preferred name
- country
- timezone
- communication style

Your task is to facilitate data entry by translating user's input into database actions. Use \
the tools available to you to perform database actions.

If the user wishes to clear/remove their current setting, pass in the value "rather_not_say".

As a backend agent, you are unable to interact directly with the user. If you need to seek \
clarification or input, pass it back as the "feedback" field in your response. The feedback \
field can be used regardless of the completed status. Feedback should be phrased directly to the user.

If the update failed, feedback must be provided.

You do not need to ask for confirmation from the user before processing their change.
    """


@settings_agent.tool
async def update_preferred_name(
    ctx: RunContext[SettingsAgentDependencies],
    new_value: str,
) -> str:
    """Update the user's preferred name."""

    async with async_database() as db_conn:
        try:
            await UserMetadata.update_metadata(
                db_conn,
                user_id=ctx.deps.tg_chat_id,
                field="preferred_name",
                value=new_value,
            )

        except Exception as e:
            raise MetadataFieldUpdateError("preferred_name", str(e)) from e

    await log_metadata_update_context(
        chat_id=ctx.deps.tg_chat_id,
        session_id=ctx.deps.tg_session_id,
        content=f"Updated user settings: preferred_name is now {new_value}",
    )

    return f"preferred_name updated successfully to {new_value}."


@settings_agent.tool
async def update_country(
    ctx: RunContext[SettingsAgentDependencies],
    new_value: str,
) -> str:
    """Update the user's country."""

    async with async_database() as db_conn:
        try:
            await UserMetadata.update_metadata(
                db_conn,
                user_id=ctx.deps.tg_chat_id,
                field="country",
                value=new_value,
            )

        except Exception as e:
            raise MetadataFieldUpdateError("country", str(e)) from e

    await log_metadata_update_context(
        chat_id=ctx.deps.tg_chat_id,
        session_id=ctx.deps.tg_session_id,
        content=f"Updated user settings: country is now {new_value}",
    )

    return f"country updated successfully to {new_value}."


@settings_agent.tool
async def update_timezone(
    ctx: RunContext[SettingsAgentDependencies],
    new_value: str,
) -> str:
    """Update the user's timezone."""

    async with async_database() as db_conn:
        try:
            await UserMetadata.update_metadata(
                db_conn,
                user_id=ctx.deps.tg_chat_id,
                field="timezone",
                value=new_value,
            )

        except Exception as e:
            raise MetadataFieldUpdateError("timezone", str(e)) from e

    await log_metadata_update_context(
        chat_id=ctx.deps.tg_chat_id,
        session_id=ctx.deps.tg_session_id,
        content=f"Updated user settings: timezone is now {new_value}",
    )

    return f"timezone updated successfully to {new_value}."


@settings_agent.tool
async def update_communication_style(
    ctx: RunContext[SettingsAgentDependencies],
    new_value: str,
) -> str:
    """Update the user's communication style."""

    async with async_database() as db_conn:
        try:
            await UserMetadata.update_metadata(
                db_conn,
                user_id=ctx.deps.tg_chat_id,
                field="communication_style",
                value=new_value,
            )

        except Exception as e:
            raise MetadataFieldUpdateError("communication_style", str(e)) from e

    await log_metadata_update_context(
        chat_id=ctx.deps.tg_chat_id,
        session_id=ctx.deps.tg_session_id,
        content=f"Updated user settings: communication_style is now {new_value}",
    )

    return f"communication_style updated successfully to {new_value}."


@settings_agent.output_validator
async def validate_settings_agent_output(
    ctx: pydantic_ai.RunContext,  # noqa: ARG001
    data: SettingsUpdateResponse,
) -> SettingsUpdateResponse:
    if not data.completed and not data.feedback:
        raise FeedbackMissingError()

    return data
