from dataclasses import dataclass
from typing import Literal

import pydantic
import pydantic_ai
from pydantic_ai import RunContext

from areyouok_telegram.data import UserMetadata
from areyouok_telegram.data import async_database
from areyouok_telegram.llms.exceptions import MetadataFieldUpdateError
from areyouok_telegram.llms.models import ClaudeSonnet4
from areyouok_telegram.llms.utils import log_metadata_update_context


class FeedbackMissingError(pydantic_ai.ModelRetry):
    """Exception raised for missing feedback in model output."""

    def __init__(self):
        message = "Feedback is required when completed is False."
        super().__init__(message)


@dataclass
class PreferencesAgentDependencies:
    """Dependencies for the preferences agent."""

    tg_chat_id: str
    tg_session_id: str


class PreferencesUpdateResponse(pydantic.BaseModel):
    """Model for user settings response."""

    completed: bool = pydantic.Field(description="Whether the update was successful.")
    feedback: str | None = pydantic.Field(
        description="Feedback or information that needs to be passed back to the user.", default=None
    )


agent_model = ClaudeSonnet4(model_settings=pydantic_ai.settings.ModelSettings(temperature=0.0))

preferences_agent = pydantic_ai.Agent(
    model=agent_model.model,
    output_type=PreferencesUpdateResponse,
    name="preferences_agent",
    end_strategy="exhaustive",
)


@preferences_agent.instructions
def generate_instructions() -> str:
    return """
You are a backend agent responsible for managing user preferences. You are \
able to manage the following settings:
- preferred name
- country
- timezone
- communication style
- response speed

Your task is to facilitate data entry by translating user's input into database actions. Use \
the tools available to you to perform database actions.

If the user wishes to clear/remove their current setting, pass in the value "rather_not_say".

As a backend agent, you are unable to interact directly with the user. If you need to seek \
clarification or input, pass it back as the "feedback" field in your response. The feedback \
field can be used regardless of the completed status. Feedback should be phrased directly to the user.

If the update failed, feedback must be provided.

You do not need to ask for confirmation from the user before processing their change.
    """


@preferences_agent.tool
async def update_preferred_name(
    ctx: RunContext[PreferencesAgentDependencies],
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
        content=f"Updated user preferences: preferred_name is now {new_value}",
    )

    return f"preferred_name updated successfully to {new_value}."


@preferences_agent.tool
async def update_country(
    ctx: RunContext[PreferencesAgentDependencies],
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
        content=f"Updated user preferences: country is now {new_value}",
    )

    return f"country updated successfully to {new_value}."


@preferences_agent.tool
async def update_timezone(
    ctx: RunContext[PreferencesAgentDependencies],
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
        content=f"Updated user preferences: timezone is now {new_value}",
    )

    return f"timezone updated successfully to {new_value}."


@preferences_agent.tool
async def update_communication_style(
    ctx: RunContext[PreferencesAgentDependencies],
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
        content=f"Updated user preferences: communication_style is now {new_value}",
    )

    return f"communication_style updated successfully to {new_value}."


@preferences_agent.tool
async def update_response_speed(
    ctx: RunContext[PreferencesAgentDependencies],
    new_value: Literal["fast", "normal", "slow"],
) -> str:
    """Update the user's response speed."""

    async with async_database() as db_conn:
        try:
            await UserMetadata.update_metadata(
                db_conn,
                user_id=ctx.deps.tg_chat_id,
                field="response_speed",
                value=new_value,
            )

        except Exception as e:
            raise MetadataFieldUpdateError("response_speed", str(e)) from e

    await log_metadata_update_context(
        chat_id=ctx.deps.tg_chat_id,
        session_id=ctx.deps.tg_session_id,
        content=f"Updated user preferences: response_speed is now {new_value}",
    )

    return f"response_speed updated successfully to {new_value}."


@preferences_agent.output_validator
async def validate_preferences_agent_output(
    ctx: pydantic_ai.RunContext,  # noqa: ARG001
    data: PreferencesUpdateResponse,
) -> PreferencesUpdateResponse:
    if not data.completed and not data.feedback:
        raise FeedbackMissingError()

    return data
