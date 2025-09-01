from dataclasses import dataclass
from dataclasses import field
from typing import Literal

import pydantic_ai
from telegram.ext import ContextTypes

from areyouok_telegram.llms.chat.constants import CHAT_AGENT_PROMPT
from areyouok_telegram.llms.chat.constants import PERSONALITY_SWITCH_INSTRUCTIONS
from areyouok_telegram.llms.chat.constants import RESTRICT_PERSONALITY_SWITCH
from areyouok_telegram.llms.chat.constants import RESTRICT_TEXT_RESPONSE
from areyouok_telegram.llms.chat.personalities import PersonalityTypes
from areyouok_telegram.llms.chat.responses import DoNothingResponse
from areyouok_telegram.llms.chat.responses import ReactionResponse
from areyouok_telegram.llms.chat.responses import SwitchPersonalityResponse
from areyouok_telegram.llms.chat.responses import TextResponse
from areyouok_telegram.llms.chat.utils import check_restricted_responses
from areyouok_telegram.llms.chat.utils import check_special_instructions
from areyouok_telegram.llms.chat.utils import validate_response_data
from areyouok_telegram.llms.models import CHAT_SONNET_4

AgentResponse = TextResponse | ReactionResponse | SwitchPersonalityResponse | DoNothingResponse


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
    name="areyouok_chat_agent",
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

    return CHAT_AGENT_PROMPT.format(
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
    check_restricted_responses(
        response=data,
        restricted=ctx.deps.restricted_responses,
    )

    await validate_response_data(
        response=data,
        chat_id=ctx.deps.tg_chat_id,
        bot_id=str(ctx.deps.tg_context.bot.id),
    )

    if ctx.deps.instruction:
        await check_special_instructions(
            response=data,
            chat_id=ctx.deps.tg_chat_id,
            session_id=ctx.deps.tg_session_id,
            instruction=ctx.deps.instruction,
        )

    return data
