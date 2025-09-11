from dataclasses import dataclass
from dataclasses import field
from typing import Literal

import pydantic_ai
from pydantic_ai import RunContext
from telegram.ext import ContextTypes

from areyouok_telegram.data import Notifications
from areyouok_telegram.data import UserMetadata
from areyouok_telegram.data import async_database
from areyouok_telegram.llms.agent_anonymizer import anonymization_agent
from areyouok_telegram.llms.chat.constants import MESSAGE_FOR_USER_PROMPT
from areyouok_telegram.llms.chat.constants import PERSONALITY_PROMPT
from areyouok_telegram.llms.chat.constants import PERSONALITY_SWITCH_INSTRUCTIONS
from areyouok_telegram.llms.chat.constants import RESPONSE_PROMPT
from areyouok_telegram.llms.chat.constants import RESTRICT_PERSONALITY_SWITCH
from areyouok_telegram.llms.chat.constants import RESTRICT_TEXT_RESPONSE
from areyouok_telegram.llms.chat.constants import USER_PREFERENCES
from areyouok_telegram.llms.chat.personalities import PersonalityTypes
from areyouok_telegram.llms.chat.prompt import BaseChatPromptTemplate
from areyouok_telegram.llms.chat.responses import DoNothingResponse
from areyouok_telegram.llms.chat.responses import ReactionResponse
from areyouok_telegram.llms.chat.responses import SwitchPersonalityResponse
from areyouok_telegram.llms.chat.responses import TextResponse
from areyouok_telegram.llms.chat.utils import check_restricted_responses
from areyouok_telegram.llms.chat.utils import check_special_instructions
from areyouok_telegram.llms.chat.utils import validate_response_data
from areyouok_telegram.llms.exceptions import MetadataFieldUpdateError
from areyouok_telegram.llms.models import ClaudeSonnet4
from areyouok_telegram.llms.utils import log_metadata_update_context
from areyouok_telegram.llms.utils import run_agent_with_tracking

AgentResponse = TextResponse | ReactionResponse | SwitchPersonalityResponse | DoNothingResponse


@dataclass
class ChatAgentDependencies:
    """Context data passed to the LLM agent for making decisions."""

    tg_context: ContextTypes.DEFAULT_TYPE
    tg_chat_id: str
    tg_session_id: str
    personality: str = PersonalityTypes.EXPLORATION.value
    restricted_responses: set[Literal["text", "reaction", "switch_personality"]] = field(default_factory=set)
    notification: Notifications | None = None


agent_model = ClaudeSonnet4()

chat_agent = pydantic_ai.Agent(
    model=agent_model.model,
    output_type=AgentResponse,
    deps_type=ChatAgentDependencies,
    name="areyouok_chat_agent",
    end_strategy="exhaustive",
    retries=3,
)


@chat_agent.instructions
async def instructions_with_personality_switch(ctx: pydantic_ai.RunContext[ChatAgentDependencies]) -> str:
    async with async_database() as db_conn:
        user_metadata = await UserMetadata.get_by_user_id(db_conn, user_id=ctx.deps.tg_chat_id)

    personality = PersonalityTypes.get_by_value(ctx.deps.personality)
    personality_text = personality.prompt_text()

    restrict_response_text = ""

    if "text" in ctx.deps.restricted_responses:
        restrict_response_text += RESTRICT_TEXT_RESPONSE
        restrict_response_text += "\n"

    if "switch_personality" in ctx.deps.restricted_responses:
        restrict_response_text += RESTRICT_PERSONALITY_SWITCH
        restrict_response_text += "\n"

    user_preferences_text = (
        USER_PREFERENCES.format(
            preferred_name=user_metadata.preferred_name,
            country=user_metadata.country,
            timezone=user_metadata.timezone,
            current_time=user_metadata.get_current_time(),
            communication_style=user_metadata.communication_style,
        )
        if user_metadata
        else None
    )

    prompt = BaseChatPromptTemplate(
        response=RESPONSE_PROMPT.format(response_restrictions=restrict_response_text),
        message=MESSAGE_FOR_USER_PROMPT.format(important_message_for_user=ctx.deps.notification.content)
        if ctx.deps.notification
        else None,
        personality=PERSONALITY_PROMPT.format(
            personality_text=personality_text,
            personality_switch_instructions=PERSONALITY_SWITCH_INSTRUCTIONS
            if "switch_personality" not in ctx.deps.restricted_responses
            else None,
        ),
        user_preferences=user_preferences_text,
    )
    return prompt.as_prompt_string()


@chat_agent.output_validator
async def validate_agent_response(
    ctx: pydantic_ai.RunContext[ChatAgentDependencies], data: AgentResponse
) -> AgentResponse:
    check_restricted_responses(
        response=data,
        restricted=ctx.deps.restricted_responses,
    )

    await validate_response_data(
        response=data,
        chat_id=ctx.deps.tg_chat_id,
        bot_id=str(ctx.deps.tg_context.bot.id),
    )

    if ctx.deps.notification:
        await check_special_instructions(
            response=data,
            chat_id=ctx.deps.tg_chat_id,
            session_id=ctx.deps.tg_session_id,
            instruction=ctx.deps.notification.content,
        )

    return data


@chat_agent.tool
async def update_communication_style(
    ctx: RunContext[ChatAgentDependencies],
    new_communication_style: str,
) -> str:
    """
    Update the user's preferred communication style as you learn more about the user.
    This should only be used for long-lasting preferences over in-the-moment changes in needs/demands.

    Text will be anonymized before being updated in the database.
    """

    anon_text = await run_agent_with_tracking(
        anonymization_agent,
        chat_id=ctx.deps.tg_chat_id,
        session_id=ctx.deps.tg_session_id,
        run_kwargs={
            "user_prompt": new_communication_style,
        },
    )

    async with async_database() as db_conn:
        try:
            await UserMetadata.update_metadata(
                db_conn,
                user_id=ctx.deps.tg_chat_id,
                field="communication_style",
                value=anon_text.output,
            )

        except Exception as e:
            raise MetadataFieldUpdateError("communication_style", str(e)) from e

    # Log the metadata update to context
    await log_metadata_update_context(
        chat_id=ctx.deps.tg_chat_id,
        session_id=ctx.deps.tg_session_id,
        content=f"Updated usermeta: communication_style is now {str(anon_text.output)}",
    )

    return f"User's new communication_style updated to: {anon_text.output}."
