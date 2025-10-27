"""Journaling agent for guided reflection sessions."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import logfire
import pydantic_ai
from pydantic_ai import RunContext

from areyouok_telegram.config import SIMULATION_MODE
from areyouok_telegram.data.models import (
    Context,
    ContextType,
    GuidedSession,
    GuidedSessionType,
    JournalContextMetadata,
    UserMetadata,
)
from areyouok_telegram.llms.agent_journal_setup import (
    JournalPrompts,
    construct_journal_context_text,
    journal_prompts_agent,
)
from areyouok_telegram.llms.chat.constants import (
    JOURNALING_SESSION_JOURNALING_OBJECTIVES,
    JOURNALING_SESSION_TOPIC_SELECTION_OBJECTIVES,
    MESSAGE_FOR_USER_PROMPT,
    RESPONSE_PROMPT,
    RESTRICT_TEXT_RESPONSE,
    USER_PREFERENCES,
    USER_PROFILE,
)
from areyouok_telegram.llms.chat.prompt import BaseChatPromptTemplate
from areyouok_telegram.llms.chat.responses import DoNothingResponse, KeyboardResponse, ReactionResponse, TextResponse
from areyouok_telegram.llms.chat.utils import (
    CommonChatAgentDependencies,
    check_restricted_responses,
    check_special_instructions,
    validate_response_data,
)
from areyouok_telegram.llms.exceptions import JournalingSessionNotActiveError
from areyouok_telegram.llms.models import Gemini25Pro
from areyouok_telegram.llms.utils import run_agent_with_tracking

AgentResponse = TextResponse | ReactionResponse | DoNothingResponse | KeyboardResponse


@dataclass
class JournalingAgentDependencies(CommonChatAgentDependencies):
    """Dependencies for the journaling agent."""

    journaling_session: GuidedSession = field(kw_only=True)

    @property
    def journaling_session_metadata(self) -> JournalContextMetadata:
        """Parse metadata from the session."""
        return JournalContextMetadata(**self.journaling_session.metadata)

    def to_dict(self) -> dict:
        return super().to_dict() | {
            "journaling_session_id": self.journaling_session.id,
        }


agent_model = Gemini25Pro()


journaling_agent = pydantic_ai.Agent(
    model=agent_model.model,
    output_type=AgentResponse,
    deps_type=JournalingAgentDependencies,
    name="areyouok_journaling_agent",
    end_strategy="exhaustive",
    retries=3,
)


@journaling_agent.instructions
async def journaling_instructions(ctx: RunContext[JournalingAgentDependencies]) -> str:
    """Provide instructions for the journaling agent based on current session state."""

    restrict_response_text = ""

    if "text" in ctx.deps.restricted_responses:
        restrict_response_text += RESTRICT_TEXT_RESPONSE
        restrict_response_text += "\n"

    if ctx.deps.journaling_session_metadata.phase == "topic_selection":
        journal_sys_prompt = JOURNALING_SESSION_TOPIC_SELECTION_OBJECTIVES
    else:
        journal_sys_prompt = JOURNALING_SESSION_JOURNALING_OBJECTIVES.format(
            selected_topic=ctx.deps.journaling_session_metadata.selected_topic
        )

    # Fetch the latest profile for this chat
    user_profile_text = ""
    user_preferences_text = ""
    if not SIMULATION_MODE:
        try:
            profile_contexts = await Context.get_by_chat(
                chat=ctx.deps.chat,
                ctype=ContextType.PROFILE.value,
            )
            if profile_contexts:
                user_profile = profile_contexts[0]  # Most recent
                user_profile_text = USER_PROFILE.format(user_profile=user_profile.content)

        except Exception as e:
            # If profile fetch fails, just continue without it
            logfire.warning(
                "Failed to fetch user profile, continuing without it",
                chat_id=ctx.deps.chat.id,
                error=str(e),
                _exc_info=True,
            )

        user_metadata = await UserMetadata.get_by_user_id(user_id=ctx.deps.user.id)
        if user_metadata:
            user_preferences_text = USER_PREFERENCES.format(
                preferred_name=user_metadata.preferred_name or "Not provided.",
                country=user_metadata.country or "Not provided.",
                timezone=user_metadata.timezone or "Not provided.",
                communication_style=user_metadata.communication_style or "",
            )

    prompt = BaseChatPromptTemplate(
        response=RESPONSE_PROMPT.format(response_restrictions=restrict_response_text),
        message=MESSAGE_FOR_USER_PROMPT.format(important_message_for_user=ctx.deps.notification.content)
        if ctx.deps.notification
        else None,
        objectives=journal_sys_prompt,
        user_preferences=user_preferences_text,
        user_profile=user_profile_text,
    )

    return prompt.as_prompt_string()


@journaling_agent.tool
async def generate_topics(ctx: RunContext[JournalingAgentDependencies]) -> str:
    """
    Generates up to three (3) possible topics for reflection based on the user's prior interactions.
    Returns a newline-separated string of topics.
    """

    # Retrieve journal context - determine the start timestamp
    now = datetime.now(UTC)
    seven_days_ago = now - timedelta(days=7)

    relevant_context_types = [
        ContextType.SESSION.value,
        ContextType.MEMORY.value,
        ContextType.PROFILE_UPDATE.value,
        ContextType.PROFILE.value,
    ]

    # Find the most recent completed journaling session
    all_journal_sessions = await GuidedSession.get_by_chat(
        chat=ctx.deps.chat,
        session_type=GuidedSessionType.JOURNALING.value,
    )

    completed_sessions = [s for s in all_journal_sessions if s.completed_at]
    if completed_sessions:
        last_journal_time = max(s.completed_at for s in completed_sessions)
        from_timestamp = max(last_journal_time, seven_days_ago)
    else:
        from_timestamp = seven_days_ago

    # Retrieve contexts of specific types since the determined timestamp
    contexts = await Context.get_by_chat(
        chat=ctx.deps.chat,
        from_timestamp=from_timestamp,
        to_timestamp=now,
    )

    journal_context_items = [ctx for ctx in contexts if ctx.type in relevant_context_types] if contexts else None

    if journal_context_items:
        journal_context_text = construct_journal_context_text(journal_context_items=journal_context_items)

        # Generate journaling prompts using the prompt agent
        prompt_result = await run_agent_with_tracking(
            journal_prompts_agent,
            chat=ctx.deps.chat,
            session=ctx.deps.session,
            run_kwargs={
                "user_prompt": (
                    "Generate 3 contextual journaling prompts based on the user's recent interactions:"
                    f"\n\n{journal_context_text}"
                ),
            },
        )

        agent_response: JournalPrompts = prompt_result.output

        # Update metadata with generated topics
        metadata = ctx.deps.journaling_session_metadata
        metadata.generated_topics = agent_response.prompts
        ctx.deps.journaling_session.metadata = metadata.model_dump()
        await ctx.deps.journaling_session.save()

        return "\n".join(agent_response.prompts)

    return "No recent context available. Generate 3 generic journaling prompts for the user to choose from."


@journaling_agent.tool
async def update_selected_topic(ctx: RunContext[JournalingAgentDependencies], topic: str) -> str:
    """
    Usable when the journal session is in the topic_selection phase.
    Sets the selected topic for the journaling session.
    """

    metadata = ctx.deps.journaling_session_metadata

    if metadata.phase != "topic_selection":
        raise pydantic_ai.ModelRetry("Journaling session is not in the topic_selection phase.")  # noqa: TRY003

    metadata.phase = "journaling"
    metadata.selected_topic = topic

    ctx.deps.journaling_session.metadata = metadata.model_dump()
    await ctx.deps.journaling_session.save()

    return "User's selected topic updated successfully."


@journaling_agent.tool
async def complete_journaling_session(ctx: RunContext[JournalingAgentDependencies]) -> str:
    """Mark the journaling session as complete."""

    if not ctx.deps.journaling_session.is_active:
        raise JournalingSessionNotActiveError

    metadata = ctx.deps.journaling_session_metadata
    metadata.phase = "complete"
    ctx.deps.journaling_session.metadata = metadata.model_dump()

    await ctx.deps.journaling_session.save()
    await ctx.deps.journaling_session.complete()

    return (
        "Journaling session completed successfully. "
        "Summarize the user's reflections and encourage them to continue journaling in future."
    )


@journaling_agent.output_validator
async def validate_journaling_output(
    ctx: RunContext[JournalingAgentDependencies],
    data: AgentResponse,
) -> AgentResponse:
    """Validate the response data."""
    check_restricted_responses(
        response=data,
        restricted=ctx.deps.restricted_responses,
    )

    if SIMULATION_MODE:
        # In simulation mode, skip database-dependent validations
        return data

    await validate_response_data(
        response=data,
        chat=ctx.deps.chat,
        bot_id=ctx.deps.bot_id,
    )

    if ctx.deps.notification:
        await check_special_instructions(
            response=data,
            chat=ctx.deps.chat,
            session=ctx.deps.session,
            instruction=ctx.deps.notification.content,
        )

    return data
