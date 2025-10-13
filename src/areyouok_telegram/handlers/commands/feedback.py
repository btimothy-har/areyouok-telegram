import asyncio
import random
import uuid
from datetime import UTC
from datetime import datetime
from urllib.parse import quote_plus

import logfire
import telegram
from cachetools import TTLCache
from telegram.constants import ReactionEmoji
from telegram.ext import ContextTypes

from areyouok_telegram.config import ENV
from areyouok_telegram.data import ChatEvent
from areyouok_telegram.data import Chats
from areyouok_telegram.data import Context
from areyouok_telegram.data import ContextType
from areyouok_telegram.data import MediaFiles
from areyouok_telegram.data import Sessions
from areyouok_telegram.data import async_database
from areyouok_telegram.data import operations as data_operations
from areyouok_telegram.handlers.constants import MD2_FEEDBACK_MESSAGE
from areyouok_telegram.llms import run_agent_with_tracking
from areyouok_telegram.llms.agent_feedback_context import ContextAgentDependencies
from areyouok_telegram.llms.agent_feedback_context import feedback_context_agent
from areyouok_telegram.logging import traced
from areyouok_telegram.utils.retry import db_retry
from areyouok_telegram.utils.retry import telegram_call
from areyouok_telegram.utils.text import package_version
from areyouok_telegram.utils.text import shorten_url

FEEDBACK_CACHE = TTLCache(maxsize=1000, ttl=300)  # Cache feedback context for 5 minutes

FEEDBACK_URL = "https://docs.google.com/forms/d/e/1FAIpQLScV9gxqsBE0vNyQ_xJJI1ykPwT43xmc6ClyCo8ORkY4nMsgZA/viewform?usp=pp_url&entry.265305704={uuid}&entry.1140367297={session_id}&entry.604567897={context}&entry.4225678={env}&entry.191939218={version}&pageHistory=0,1,2"


@traced(extract_args=["update"])
@db_retry()
async def on_feedback_command(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /feedback command - provide a feedback URL to the user."""

    feedback_uuid = str(uuid.uuid4())

    active_session = await data_operations.get_or_create_active_session(
        chat_id=str(update.effective_chat.id),
        create_if_not_exists=False,
    )

    await data_operations.track_command_usage(
        command="feedback",
        chat_id=str(update.effective_chat.id),
        session_id=getattr(active_session, "session_id", None),
    )

    if not active_session:
        feedback_url = FEEDBACK_URL.format(
            uuid=quote_plus(feedback_uuid),
            session_id=quote_plus("no_active_session"),
            context=quote_plus("No active session found."),
            env=quote_plus(ENV),
            version=quote_plus(package_version()),
        )
    else:
        context_task = asyncio.create_task(
            generate_feedback_context(
                bot_id=str(context.bot.id),
                session=active_session,
            )
        )

        await telegram_call(
            context.bot.set_message_reaction,
            chat_id=update.effective_chat.id,
            message_id=update.message.message_id,
            reaction=random.choice(
                [
                    ReactionEmoji.THUMBS_UP,
                    ReactionEmoji.EYES,
                    ReactionEmoji.THINKING_FACE,
                    ReactionEmoji.SALUTING_FACE,
                ]
            ),
        )

        await telegram_call(
            context.bot.send_chat_action,
            chat_id=update.effective_chat.id,
            action=telegram.constants.ChatAction.TYPING,
        )

        feedback_context = await context_task

        feedback_url = FEEDBACK_URL.format(
            uuid=quote_plus(feedback_uuid),
            session_id=quote_plus(active_session.session_id),
            context=quote_plus(feedback_context),
            env=quote_plus(ENV),
            version=quote_plus(package_version()),
        )

    try:
        short_url = await shorten_url(feedback_url)
    except Exception:
        logfire.warning(
            "Failed to shorten feedback URL, using full URL instead.",
            url=feedback_url,
            _exc_info=True,
        )
        short_url = feedback_url

    reply_markup = [
        [
            telegram.InlineKeyboardButton(
                text="Submit Your Feedback",
                url=short_url,
            )
        ]
    ]

    await telegram_call(
        context.bot.send_message,
        chat_id=update.effective_chat.id,
        text=MD2_FEEDBACK_MESSAGE,
        parse_mode="MarkdownV2",
        reply_markup=telegram.InlineKeyboardMarkup(reply_markup),
    )


@db_retry()
async def generate_feedback_context(bot_id: str, session: Sessions) -> str:
    feedback_ts = datetime.now(UTC)

    chat_id = session.chat_id

    if chat_id in FEEDBACK_CACHE:
        cached_output, cached_ts = FEEDBACK_CACHE[chat_id]
        if (feedback_ts - cached_ts).total_seconds() < 300:
            return cached_output

    chat_events_for_feedback = []

    async with async_database() as db_conn:
        chat_obj = await Chats.get_by_id(db_conn, chat_id=chat_id)

        chat_messages = await session.get_messages(db_conn)

        if len(chat_messages) < 10:
            return "Less than 10 messages in the session. Not enough context for feedback context."

        for msg in chat_messages:
            msg.decrypt(chat_obj.retrieve_key())

            if msg.message_type == "Message":
                media = await MediaFiles.get_by_message_id(
                    db_conn,
                    chat_id=chat_id,
                    message_id=msg.message_id,
                )
            elif msg.message_type == "MessageReactionUpdated":
                media = []
            else:
                continue  # Skip unknown message types

            if media:
                [m.decrypt_content(chat_encryption_key=chat_obj.retrieve_key()) for m in media]

            chat_events_for_feedback.append(ChatEvent.from_message(msg, media))

        chat_context = await Context.get_by_session_id(
            db_conn,
            session_id=session.session_id,
        )
        if chat_context:
            context = [c for c in chat_context if c.type != ContextType.SESSION.value]
            [c.decrypt_content(chat_encryption_key=chat_obj.retrieve_key()) for c in context]
            chat_events_for_feedback.extend([ChatEvent.from_context(c) for c in context])

    chat_events_for_feedback.sort(key=lambda x: x.timestamp)

    agent_run_payload = await run_agent_with_tracking(
        feedback_context_agent,
        chat_id=chat_id,
        session_id=session.session_id,
        run_kwargs={
            "message_history": [c.to_model_message(str(bot_id), feedback_ts) for c in chat_events_for_feedback],
            "deps": ContextAgentDependencies(
                tg_chat_id=chat_id,
                tg_session_id=session.session_id,
            ),
        },
    )

    FEEDBACK_CACHE[chat_id] = (agent_run_payload.output, feedback_ts)

    return agent_run_payload.output
