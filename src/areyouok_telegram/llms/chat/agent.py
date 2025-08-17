from dataclasses import dataclass
from dataclasses import field
from typing import Literal

import pydantic_ai
from telegram.ext import ContextTypes

from areyouok_telegram.data import Messages
from areyouok_telegram.data import async_database
from areyouok_telegram.llms.chat.constants import AGENT_PROMPT
from areyouok_telegram.llms.chat.constants import PERSONALITY_SWITCH_INSTRUCTIONS
from areyouok_telegram.llms.chat.constants import RESTRICT_PERSONALITY_SWITCH
from areyouok_telegram.llms.chat.constants import RESTRICT_TEXT_RESPONSE
from areyouok_telegram.llms.chat.personalities import PersonalityTypes
from areyouok_telegram.llms.chat.responses import AgentResponse
from areyouok_telegram.llms.exceptions import InvalidMessageError
from areyouok_telegram.llms.exceptions import ReactToSelfError
from areyouok_telegram.llms.exceptions import ResponseRestrictedError
from areyouok_telegram.llms.exceptions import UnacknowledgedImportantMessageError
from areyouok_telegram.llms.models import CHAT_SONNET_4
from areyouok_telegram.llms.utils import run_agent_with_tracking
from areyouok_telegram.llms.validators.content_check import ContentCheckDependencies
from areyouok_telegram.llms.validators.content_check import ContentCheckResponse
from areyouok_telegram.llms.validators.content_check import content_check_agent


@dataclass
class ChatAgentDependencies:
    """Context data passed to the LLM agent for making decisions."""

    # TODO: Add user preferences so we have context
    tg_context: ContextTypes.DEFAULT_TYPE
    tg_chat_id: str
    tg_session_id: str
    personality: str = PersonalityTypes.EXPLORATION.value
    restricted_responses: set[Literal["text", "reaction", "switch_personality"]] = field(default_factory=set)
    instruction: str | None = None


chat_agent = pydantic_ai.Agent(
    model=CHAT_SONNET_4.model,
    output_type=AgentResponse,
    deps_type=ChatAgentDependencies,
    name="areyouok_telegram_agent",
    end_strategy="exhaustive",
    retries=3,
)


@chat_agent.instructions
async def instructions_with_personality_switch(ctx: pydantic_ai.RunContext[ChatAgentDependencies]) -> str:
    personality = PersonalityTypes.get_by_value(ctx.deps.personality)
    personality_text = personality.prompt_text()

    restrict_response_text = ""

    if "text" in ctx.deps.restricted_responses:
        restrict_response_text += RESTRICT_TEXT_RESPONSE
        restrict_response_text += "\n"

    if "switch_personality" in ctx.deps.restricted_responses:
        restrict_response_text += RESTRICT_PERSONALITY_SWITCH
        restrict_response_text += "\n"

    return AGENT_PROMPT.format(
        important_message_for_user=ctx.deps.instruction if ctx.deps.instruction else "None",
        personality_text=personality_text,
        personality_switch_instructions=PERSONALITY_SWITCH_INSTRUCTIONS
        if "switch_personality" not in ctx.deps.restricted_responses
        else "",
        response_restrictions=restrict_response_text or "",
    )


@chat_agent.output_validator
async def validate_agent_response(
    ctx: pydantic_ai.RunContext[ChatAgentDependencies], data: AgentResponse
) -> AgentResponse:
    if "text" in ctx.deps.restricted_responses and data.response_type == "TextResponse":
        raise ResponseRestrictedError(data.response_type)

    if "switch_personality" in ctx.deps.restricted_responses and data.response_type == "SwitchPersonalityResponse":
        raise ResponseRestrictedError(data.response_type)

    if data.response_type == "ReactionResponse":
        async with async_database() as db_conn:
            message, _ = await Messages.retrieve_message_by_id(
                db_conn=db_conn,
                message_id=data.react_to_message_id,
                chat_id=ctx.deps.tg_chat_id,
            )

        if not message:
            raise InvalidMessageError(data.react_to_message_id)

        if message.user_id == str(ctx.deps.tg_context.bot.id):
            raise ReactToSelfError(data.react_to_message_id)

    if ctx.deps.instruction:
        if data.response_type != "TextResponse":
            raise UnacknowledgedImportantMessageError(ctx.deps.instruction)

        else:
            content_check_run = await run_agent_with_tracking(
                agent=content_check_agent,
                chat_id=ctx.deps.tg_chat_id,
                session_id=ctx.deps.tg_session_id,
                run_kwargs={
                    "user_prompt": data.message_text,
                    "deps": ContentCheckDependencies(
                        check_content_exists=ctx.deps.instruction,
                    ),
                },
            )

            content_check: ContentCheckResponse = content_check_run.output

            if not content_check.check_pass:
                raise UnacknowledgedImportantMessageError(ctx.deps.instruction, content_check.feedback)

    return data
