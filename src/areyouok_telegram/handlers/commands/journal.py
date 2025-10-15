"""Handler for /journal command to initiate journaling sessions."""

from datetime import UTC, datetime, timedelta

import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.data import (
    Context,
    ContextType,
    GuidedSessions,
    GuidedSessionType,
    Sessions,
    operations as data_operations,
)
from areyouok_telegram.data.connection import async_database
from areyouok_telegram.llms.agent_journal_setup import (
    JournalPrompts,
    construct_journal_context_text,
    journal_prompts_agent,
)
from areyouok_telegram.llms.utils import run_agent_with_tracking
from areyouok_telegram.logging import traced
from areyouok_telegram.utils.retry import db_retry, telegram_call


@traced(extract_args=["update"])
async def on_journal_command(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /journal command to start a new journaling session."""

    active_session = await data_operations.get_or_create_active_session(
        chat_id=str(update.effective_chat.id),
        timestamp=update.message.date,
    )

    await data_operations.track_command_usage(
        command="journal",
        chat_id=str(update.effective_chat.id),
        session_id=active_session.session_id,
    )

    existing_session = await data_operations.get_active_guided_session(session=active_session)

    if existing_session:
        await telegram_call(
            context.bot.send_message,
            chat_id=update.effective_chat.id,
            text=(
                f"You already have an active {existing_session.session_type.capitalize()} session. "
                "Please complete it before using this command.",
            ),
        )
        return

    # Get chat encryption key
    chat_encryption_key = await data_operations.get_chat_encryption_key(chat_id=str(update.effective_chat.id))

    journal_context_items = await retrieve_journal_context(chat_id=str(update.effective_chat.id))
    [ctx.decrypt_content(chat_encryption_key=chat_encryption_key) for ctx in journal_context_items]

    journal_context_text = construct_journal_context_text(journal_context_items=journal_context_items)

    # Generate journaling prompts using the prompt agent
    prompt_result = await run_agent_with_tracking(
        journal_prompts_agent,
        chat_id=str(update.effective_chat.id),
        session_id=active_session.session_id,
        run_kwargs={
            "user_prompt": (
                "Generate 3 contextual journaling prompts based on the user's recent interactions:"
                f"\n\n{journal_context_text}"
            ),
        },
    )

    agent_response: JournalPrompts = prompt_result.output

    # Create new journaling session with initial metadata
    initial_metadata = {
        "phase": "prompt_selection",
        "generated_prompts": agent_response.prompts,
        "selected_prompt_index": None,
        "conversation": [],
        "current_prompt_index": 0,
    }

    await initialize_journaling_session(
        chat_id=str(update.effective_chat.id),
        session=active_session,
        chat_encryption_key=chat_encryption_key,
        initial_metadata=initial_metadata,
    )

    # Record this event in the session
    await data_operations.new_session_event(
        session=active_session,
        message=update.message,
        user_id=str(update.effective_user.id),
        is_user=True,
    )

    # Send prompts as keyboard buttons
    keyboard = [[telegram.KeyboardButton(text=prompt)] for prompt in agent_response.prompts]
    reply_markup = telegram.ReplyKeyboardMarkup(
        keyboard=keyboard,
        one_time_keyboard=True,
        resize_keyboard=True,
    )

    await telegram_call(
        context.bot.send_message,
        chat_id=update.effective_chat.id,
        text="Here are some journaling prompts for you today. Choose one to begin your reflection:",
        reply_markup=reply_markup,
    )


@db_retry()
async def retrieve_journal_context(*, chat_id: str) -> list[Context]:
    # Determine the start timestamp for context retrieval
    now = datetime.now(UTC)
    seven_days_ago = now - timedelta(days=7)

    relevant_context_types = [
        ContextType.SESSION.value,
        ContextType.MEMORY.value,
        ContextType.PROFILE_UPDATE.value,
        ContextType.PROFILE.value,
    ]

    # Get contexts since last journal session or last 7 days
    async with async_database() as db_conn:
        # Find the most recent completed journaling session
        last_journal_session = await GuidedSessions.get_by_chat_id(
            db_conn,
            chat_id=chat_id,
            session_type=GuidedSessionType.JOURNALING.value,
        )

        if last_journal_session and last_journal_session[0].completed_at:
            # Use the completion time of the last journal session if within 7 days
            last_journal_time = last_journal_session[0].completed_at
            from_timestamp = max(last_journal_time, seven_days_ago)
        else:
            # No previous journal session or too old, use 7 days ago
            from_timestamp = seven_days_ago

        # Retrieve contexts of specific types since the determined timestamp
        contexts = await Context.get_by_chat_id(
            db_conn,
            chat_id=chat_id,
            from_timestamp=from_timestamp,
            to_timestamp=now,
        )

        # Filter for relevant context types and this chat
        filtered_contexts = [ctx for ctx in contexts if ctx.type in relevant_context_types]

        return filtered_contexts


@db_retry()
async def initialize_journaling_session(
    *,
    chat_id: str,
    session: Sessions,
    chat_encryption_key: str,
    initial_metadata: dict,
) -> None:
    """Initialize a new journaling session."""
    journaling_session = await data_operations.get_or_create_guided_session(
        chat_id=chat_id,
        session=session,
        stype=GuidedSessionType.JOURNALING,
        create_if_not_exists=True,
    )

    async with async_database() as db_conn:
        # Update with encrypted metadata
        journaling_session.update_metadata(
            db_conn,
            metadata=initial_metadata,
            chat_encryption_key=chat_encryption_key,
        )
