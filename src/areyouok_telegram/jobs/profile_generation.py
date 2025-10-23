"""Background job for generating user profile summaries from context data."""

from datetime import UTC, datetime, timedelta

import logfire

from areyouok_telegram.data.models import Chat, Context, ContextType, Session
from areyouok_telegram.jobs.base import BaseJob
from areyouok_telegram.llms import run_agent_with_tracking
from areyouok_telegram.llms.profile_generation import ProfileTemplate, profile_generation_agent
from areyouok_telegram.logging import traced
from areyouok_telegram.utils.text import format_relative_time

# Context types that trigger profile generation (excludes job outputs)
TRIGGER_CONTEXT_TYPES = [
    ContextType.MEMORY.value,
    ContextType.SESSION.value,
    ContextType.METADATA.value,
]

# Context types used as input for profile generation (includes all relevant context)
INPUT_CONTEXT_TYPES = [
    ContextType.MEMORY.value,
    ContextType.SESSION.value,
    ContextType.METADATA.value,
    ContextType.PROFILE_UPDATE.value,
]

FORMATTED_CONTEXT_TEMPLATE = """
<item>
<timestamp>{timestamp}</timestamp>
<type>{type}</type>
<content>{content}</content>
</item>
"""

USER_PROMPT_TEMPLATE = """Analyze the following context data and synthesize a user profile.

<previous_profile>
{previous_profile}
</previous_profile>

<contexts>
{contexts}
</contexts>"""


class ProfileGenerationJob(BaseJob):
    """Batch job to generate user profiles from MEMORY and SESSION contexts.

    This job runs on a schedule (hourly by default) and processes all chats
    that have new contexts since the last run. It skips chats with active sessions
    to avoid interfering with ongoing conversations.
    """

    @property
    def name(self) -> str:
        """Generate job name."""
        return "profile_generation"

    @traced(extract_args=False)
    async def run_job(self) -> None:
        """Batch process profile generation for all chats."""

        try:
            # Load persisted state
            state = await self.load_state()
            last_run_time_str = state.get("last_run_time")

            # Determine cutoff time (use epoch if first run)
            if last_run_time_str:
                cutoff_time = datetime.fromisoformat(last_run_time_str)
            else:
                cutoff_time = datetime(1970, 1, 1, tzinfo=UTC)

            # Fetch all chats
            all_chats = await Chat.get()

            profiles_generated = 0

            # Process each chat
            for chat in all_chats:
                try:
                    generated = await self._process_chat(
                        chat=chat,
                        cutoff_time=cutoff_time,
                    )
                    if generated:
                        profiles_generated += 1
                except Exception:
                    logfire.exception(
                        f"Failed to process profile for chat {chat.id}",
                        chat_id=chat.id,
                        _exc_info=True,
                    )
                    # Continue processing other chats

            # Save state with last run timestamp
            await self.save_state(
                last_run_time=self._run_timestamp.isoformat(),
                profiles_generated=profiles_generated,
            )

            logfire.info(
                f"Generated {profiles_generated} profiles from {len(all_chats)} chats.",
                profiles_generated=profiles_generated,
                total_chats=len(all_chats),
                run_timestamp=self._run_timestamp.isoformat(),
            )

        except Exception:
            logfire.exception("Failed to run profile generation batch job")
            raise

    @traced(extract_args=["chat"])
    async def _process_chat(self, *, chat: Chat, cutoff_time: datetime) -> bool:
        """Process a single chat for profile generation.

        Args:
            chat: Chat object
            cutoff_time: Only process if new contexts exist after this time

        Returns:
            bool: True if a profile was generated, False otherwise
        """
        # Check if chat has active session - skip if true
        active_sessions = await Session.get_sessions(chat=chat, active=True)
        if active_sessions:
            logfire.debug(
                f"Skipping chat {chat.id} - active session",
                chat_id=chat.id,
            )
            return False

        # Fetch contexts within the last 30 days
        thirty_days_ago = self._run_timestamp - timedelta(days=30)
        all_contexts = await Context.get_by_chat(
            chat=chat,
            ctype=None,  # Will filter by type below
            from_timestamp=thirty_days_ago,
        )

        # Filter for new TRIGGER contexts created since last run (excludes job outputs)
        new_contexts = [
            ctx for ctx in all_contexts if ctx.created_at >= cutoff_time and ctx.type in TRIGGER_CONTEXT_TYPES
        ]

        # If no new trigger contexts, skip
        if not new_contexts:
            logfire.debug(
                f"Skipping chat {chat.id} - no new contexts",
                chat_id=chat.id,
            )
            return False

        # Collect contexts with content (already auto-decrypted by get_by_chat)
        decrypted_contents = [
            {
                "type": context.type,
                "content": context.content,
                "created_at": context.created_at,
            }
            for context in all_contexts
            if context.content
        ]

        if not decrypted_contents:
            logfire.debug(
                f"Skipping chat {chat.id} - no contexts with content",
                chat_id=chat.id,
            )
            return False

        # Format contexts for the agent using XML structure
        context_items = [
            FORMATTED_CONTEXT_TEMPLATE.format(
                timestamp=format_relative_time(ctx["created_at"], self._run_timestamp),
                type=ctx["type"],
                content=ctx["content"],
            )
            for ctx in decrypted_contents
        ]
        contexts_xml = "\n".join(context_items)

        # Get the most recent PROFILE context to include in the prompt
        prev_content = "No previous profile available."
        previous_profiles = await Context.get_by_chat(
            chat=chat,
            ctype=ContextType.PROFILE.value,
        )
        if previous_profiles:
            # get_by_chat returns in descending order by created_at, so first is most recent
            previous_profile = previous_profiles[0]
            if previous_profile.content:
                prev_content = previous_profile.content

        # Generate profile using the agent
        user_prompt = USER_PROMPT_TEMPLATE.format(
            previous_profile=prev_content,
            contexts=contexts_xml,
        )

        result = await run_agent_with_tracking(
            profile_generation_agent,
            chat_id=chat.id,
            session_id="profile_generation",
            run_kwargs={"user_prompt": user_prompt},
        )

        profile: ProfileTemplate = result.output

        # Save result as PROFILE context type (session_id is None since profiles are cross-session)
        profile_context = Context(
            chat=chat,
            session_id=None,
            type=ContextType.PROFILE.value,
            content=profile.content,
        )
        await profile_context.save()

        # Also save the change_log as a separate context
        update_context = Context(
            chat=chat,
            session_id=None,
            type=ContextType.PROFILE_UPDATE.value,
            content=profile.change_log,
        )
        await update_context.save()

        logfire.info(
            f"Generated profile for chat {chat.id}",
            chat_id=chat.id,
            context_count=len(decrypted_contents),
        )

        return True
