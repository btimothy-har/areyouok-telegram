from datetime import UTC, datetime, timedelta

import logfire
import telegram
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from areyouok_telegram.data.models import Chat, Context, Session, Update, User
from areyouok_telegram.handlers.exceptions import InvalidCallbackDataError, NoChatFoundError
from areyouok_telegram.jobs import ConversationJob, schedule_job
from areyouok_telegram.utils.retry import telegram_call


async def on_new_update(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    # Don't use `traced` decorator here to avoid circular logging issues
    with logfire.span(
        "New update received.",
        _span_name="handlers.globals.on_new_update",
        update=update,
    ):
        # Save the update
        update_instance = Update.from_telegram(update=update)
        update_instance = await update_instance.save()

        if update.effective_user:
            user = User.from_telegram(update.effective_user)
            user = await user.save()

        if update.effective_chat:
            chat = Chat.from_telegram(update.effective_chat)
            chat = await chat.save()

    # Only schedule the job if the update is from a private chat
    # This prevents unnecessary job scheduling for group chats or channel, which we don't support yet.
    if update.effective_chat and update.effective_chat.type == ChatType.PRIVATE:
        await schedule_job(
            context=context,
            job=ConversationJob(chat_id=chat.id),  # Use internal chat ID
            interval=timedelta(milliseconds=500),
            first=datetime.now(UTC) + timedelta(seconds=2),
        )


async def on_dynamic_response_callback(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa:ARG001
    if not update.callback_query:
        raise InvalidCallbackDataError(update.update_id)

    if not str(update.callback_query.data).startswith("response::"):
        raise InvalidCallbackDataError(update.update_id)

    await telegram_call(update.callback_query.answer)

    # Create action context
    chat = await Chat.get_by_id(telegram_chat_id=update.effective_chat.id)
    if not chat:
        raise NoChatFoundError(update.effective_chat.id)

    session = await Session.get_or_create_new_session(
        chat=chat,
        session_start=datetime.now(UTC),
    )

    context_obj = Context(
        chat=chat,
        session_id=session.id,
        type="action",
        content=str(update.callback_query.data).removeprefix("response::"),
    )
    await context_obj.save()

    await session.new_activity(
        timestamp=datetime.now(UTC),
        is_user=True,
    )
