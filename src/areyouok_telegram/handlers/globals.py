from datetime import UTC
from datetime import datetime
from datetime import timedelta

import logfire
import telegram
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from areyouok_telegram.data import Chats
from areyouok_telegram.data import Context
from areyouok_telegram.data import Users
from areyouok_telegram.data import async_database
from areyouok_telegram.data import operations as data_operations
from areyouok_telegram.handlers.exceptions import InvalidCallbackDataError
from areyouok_telegram.jobs import ConversationJob
from areyouok_telegram.jobs import schedule_job
from areyouok_telegram.utils import db_retry
from areyouok_telegram.utils import telegram_call


async def on_new_update(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    @db_retry()
    async def _handle_update():
        async with async_database() as db_conn:
            if update.effective_user:
                await Users.new_or_update(db_conn, user=update.effective_user)

            if update.effective_chat:
                await Chats.new_or_update(db_conn, chat=update.effective_chat)

    # Don't use `traced` decorator here to avoid circular logging issues
    with logfire.span(
        "New update received.",
        _span_name="handlers.globals.on_new_update",
        update=update,
    ):
        await _handle_update()

    # Only schedule the job if the update is from a private chat
    # This prevents unnecessary job scheduling for group chats or channel, which we don't support yet.
    if update.effective_chat and update.effective_chat.type == ChatType.PRIVATE:
        await schedule_job(
            context=context,
            job=ConversationJob(chat_id=str(update.effective_chat.id)),
            interval=timedelta(milliseconds=500),
            first=datetime.now(UTC) + timedelta(seconds=2),
        )


async def on_dynamic_response_callback(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa:ARG001
    @db_retry()
    async def _create_action_context():
        chat_id = str(update.effective_chat.id)

        async with async_database() as db_conn:
            active_session = await data_operations.get_or_create_active_session(
                chat_id=chat_id,
                create_if_not_exists=True,
            )
            chat_obj = await Chats.get_by_id(db_conn, chat_id=chat_id)

            await Context.new_or_update(
                db_conn,
                chat_encryption_key=chat_obj.retrieve_key(),
                chat_id=str(update.effective_chat.id),
                session_id=active_session.session_id,
                ctype="action",
                content=str(update.callback_query.data).removeprefix("response::"),
            )

            await active_session.new_activity(
                db_conn,
                timestamp=datetime.now(UTC),
                is_user=True,
            )

    if not update.callback_query or not update.callback_query.data.startswith("response::"):
        raise InvalidCallbackDataError(update.update_id)

    await telegram_call(update.callback_query.answer)
    await _create_action_context()
