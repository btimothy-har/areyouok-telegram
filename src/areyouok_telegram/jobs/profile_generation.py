"""Background job for generating user profile summaries from context data."""

from datetime import UTC
from datetime import datetime

import logfire
from sqlalchemy import select

from areyouok_telegram.data import Chats
from areyouok_telegram.data import Context
from areyouok_telegram.data import ContextType
from areyouok_telegram.data import Sessions
from areyouok_telegram.data import async_database
from areyouok_telegram.data import operations as data_operations
from areyouok_telegram.jobs.base import BaseJob
from areyouok_telegram.llms import run_agent_with_tracking
from areyouok_telegram.llms.profile_generation import ProfileTemplate
from areyouok_telegram.llms.profile_generation import profile_generation_agent
from areyouok_telegram.logging import traced
from areyouok_telegram.utils.retry import db_retry
from areyouok_telegram.utils.text import format_relative_time

CONTEXT_TYPES_FOR_PROFILE = [
    ContextType.MEMORY.value,
    ContextType.SESSION.value,
]

FORMATTED_CONTEXT_TEMPLATE = """
<item>
<timestamp>{timestamp}</timestamp>
<type>{type}</type>
<content>{content}</content>
</item>
"""

USER_PROMPT_TEMPLATE = """Analyze the following context data and synthesize a user profile.
{previous_profile}

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
            all_chats = await self._fetch_all_chats()

            profiles_generated = 0

            # Process each chat
            for chat in all_chats:
                try:
                    generated = await self._process_chat(
                        chat_id=chat.chat_id,
                        cutoff_time=cutoff_time,
                    )
                    if generated:
                        profiles_generated += 1
                except Exception:
                    logfire.exception(
                        f"Failed to process profile for chat {chat.chat_id}",
                        chat_id=chat.chat_id,
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

    @traced(extract_args=["chat_id"])
    async def _process_chat(self, *, chat_id: str, cutoff_time: datetime) -> bool:
        """Process a single chat for profile generation.

        Args:
            chat_id: The chat ID to process
            cutoff_time: Only process if new contexts exist after this time

        Returns:
            bool: True if a profile was generated, False otherwise
        """
        # Check if chat has active session - skip if true
        if await self._has_active_session(chat_id=chat_id):
            logfire.debug(
                f"Skipping chat {chat_id} - active session",
                chat_id=chat_id,
            )
            return False

        # Fetch ALL MEMORY + SESSION contexts for this chat
        all_contexts = await self._fetch_contexts(chat_id=chat_id)

        # Filter for new contexts created since cutoff
        new_contexts = [ctx for ctx in all_contexts if ctx.created_at >= cutoff_time]

        # If no new contexts, skip
        if not new_contexts:
            logfire.debug(
                f"Skipping chat {chat_id} - no new contexts",
                chat_id=chat_id,
            )
            return False

        # Get chat encryption key
        encryption_key = await data_operations.get_chat_encryption_key(chat_id=chat_id)

        # Decrypt all contexts
        decrypted_contents = []
        for context in all_contexts:
            try:
                content_str = context.decrypt_content(chat_encryption_key=encryption_key)
                if content_str:
                    decrypted_contents.append({
                        "type": context.type,
                        "content": content_str,
                        "created_at": context.created_at,
                    })
            except Exception:
                logfire.exception(
                    f"Failed to decrypt context {context.id}",
                    context_id=context.id,
                    chat_id=chat_id,
                )
                continue

        if not decrypted_contents:
            logfire.debug(
                f"Skipping chat {chat_id} - no decryptable contexts",
                chat_id=chat_id,
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
        previous_profile_text = ""
        async with async_database() as db_conn:
            previous_profile = await Context.get_latest_profile(db_conn, chat_id=chat_id)
            if previous_profile:
                try:
                    prev_content = previous_profile.decrypt_content(chat_encryption_key=encryption_key)
                    if prev_content:
                        previous_profile_text = f"\n\nPrevious Profile:\n{prev_content}"
                except Exception:
                    logfire.exception("Failed to decrypt previous profile")

        # Generate profile using the agent
        user_prompt = USER_PROMPT_TEMPLATE.format(
            previous_profile=previous_profile_text,
            contexts=contexts_xml,
        )

        result = await run_agent_with_tracking(
            agent=profile_generation_agent,
            user_prompt=user_prompt,
            agent_deps=None,
        )

        profile: ProfileTemplate = result.data

        # Save result as PROFILE context type (session_id is None since profiles are cross-session)
        async with async_database() as db_conn:
            await Context.new(
                db_conn,
                chat_encryption_key=encryption_key,
                chat_id=chat_id,
                session_id=None,
                ctype=ContextType.PROFILE.value,
                content=profile.content,
            )

            # Also save the change_log as a separate context
            await Context.new(
                db_conn,
                chat_encryption_key=encryption_key,
                chat_id=chat_id,
                session_id=None,
                ctype=ContextType.PROFILE_UPDATE.value,
                content=profile.change_log,
            )

        logfire.info(
            f"Generated profile for chat {chat_id}",
            chat_id=chat_id,
            context_count=len(decrypted_contents),
        )

        return True

    @db_retry()
    async def _fetch_all_chats(self) -> list[Chats]:
        """Fetch all chats from the database.

        Returns:
            List of all Chat objects
        """
        async with async_database() as db_conn:
            stmt = select(Chats)
            result = await db_conn.execute(stmt)
            return list(result.scalars().all())

    @db_retry()
    async def _has_active_session(self, *, chat_id: str) -> bool:
        """Check if a specific chat has an active session.

        Args:
            chat_id: The chat ID to check

        Returns:
            bool: True if chat has active session, False otherwise
        """
        async with async_database() as db_conn:
            active_session = await Sessions.get_active_session(db_conn, chat_id=chat_id)
            return active_session is not None

    @db_retry()
    async def _fetch_contexts(self, *, chat_id: str) -> list[Context]:
        """Fetch all MEMORY + SESSION contexts for a specific chat.

        Args:
            chat_id: The chat ID to fetch contexts for

        Returns:
            List of Context objects ordered by created_at
        """
        async with async_database() as db_conn:
            stmt = (
                select(Context)
                .where(Context.chat_id == chat_id)
                .where(Context.type.in_(CONTEXT_TYPES_FOR_PROFILE))
                .order_by(Context.created_at.asc())
            )
            result = await db_conn.execute(stmt)
            return list(result.scalars().all())
