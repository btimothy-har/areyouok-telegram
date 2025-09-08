import traceback

import logfire
import telegram
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from areyouok_telegram.config import DEVELOPER_CHAT_ID
from areyouok_telegram.config import DEVELOPER_THREAD_ID
from areyouok_telegram.data import Updates
from areyouok_telegram.data import async_database
from areyouok_telegram.utils import db_retry
from areyouok_telegram.utils import split_long_message
from areyouok_telegram.utils import telegram_call


async def on_error_event(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""

    logfire.exception(str(context.error), _exc_info=context.error)

    if update:
        await _save_update(update)

    if isinstance(context.error, telegram.error.NetworkError | telegram.error.TimedOut):
        return

    if DEVELOPER_CHAT_ID:
        chunked_messages = _chunk_traceback_message(context.error)

        for i, chunk in enumerate(chunked_messages):
            final_message = chunk
            if len(chunked_messages) > 1:
                # Add part indicator for multi-part messages
                chunk_header = f"*Part {i + 1}/{len(chunked_messages)}*\n\n"
                final_message = chunk_header + chunk

            await _send_message_to_developer(context.bot, final_message)

        logfire.info(f"Error notification sent to developer ({len(chunked_messages)} parts).")


@db_retry()
async def _save_update(update: telegram.Update):
    async with async_database() as db_conn:
        await Updates.new_or_upsert(db_conn, update=update)


def _chunk_traceback_message(exception: Exception) -> list[str]:
    tb_list = traceback.format_exception(None, exception, exception.__traceback__)
    tb_string = "".join(tb_list)

    # Escape backticks in the traceback for MarkdownV2 code block
    tb_string = tb_string.replace("`", "\\`")

    # Split the traceback text only (not the full message with code fences)
    base_message = "An exception was raised while handling an update\n\n"

    # Calculate available space for traceback content
    # Account for: base message + code fence markers + some buffer
    code_fence_overhead = len("```\n") + len("\n```")
    available_length = 4000 - len(base_message) - code_fence_overhead

    # Split just the traceback content
    tb_chunks = split_long_message(tb_string, max_length=available_length)

    # Wrap each chunk in its own code fence
    return [f"{base_message}```\n{chunk}\n```" for chunk in tb_chunks]


async def _send_message_to_developer(bot: telegram.Bot, message: str):
    try:
        await telegram_call(
            bot.send_message,
            chat_id=DEVELOPER_CHAT_ID,
            message_thread_id=DEVELOPER_THREAD_ID,
            text=message,
            disable_notification=True,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    except Exception as e:
        logfire.exception(
            "Failed to send error notification to developer",
            _exc_info=e,
            chat_id=DEVELOPER_CHAT_ID,
            thread_id=DEVELOPER_THREAD_ID,
        )

        try:
            await telegram_call(
                bot.send_message,
                chat_id=DEVELOPER_CHAT_ID,
                message_thread_id=DEVELOPER_THREAD_ID,
                text="Error: Failed to send error notification to developer. Please check logs.",
                disable_notification=True,
            )
        except Exception as fallback_error:
            logfire.exception(
                "Fallback error notification to developer failed.",
                _exc_info=fallback_error,
                chat_id=DEVELOPER_CHAT_ID,
                thread_id=DEVELOPER_THREAD_ID,
            )
