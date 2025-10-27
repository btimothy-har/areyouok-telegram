import traceback

import logfire
import telegram
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from areyouok_telegram.config import DEVELOPER_CHAT_ID, DEVELOPER_THREAD_ID
from areyouok_telegram.utils.retry import telegram_call
from areyouok_telegram.utils.text import split_long_message


async def on_error_event(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG001
    """Log the error and send a telegram message to notify the developer."""

    logfire.exception(str(context.error), _exc_info=context.error)

    if isinstance(context.error, telegram.error.NetworkError | telegram.error.TimedOut):
        return

    if DEVELOPER_CHAT_ID:
        # Chunk the traceback message
        tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
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
        chunked_messages = [f"{base_message}```\n{chunk}\n```" for chunk in tb_chunks]

        # Send each chunk to the developer
        for i, chunk in enumerate(chunked_messages):
            final_message = chunk
            if len(chunked_messages) > 1:
                # Add part indicator for multi-part messages
                chunk_header = f"*Part {i + 1}/{len(chunked_messages)}*\n\n"
                final_message = chunk_header + chunk

            try:
                await telegram_call(
                    context.bot.send_message,
                    chat_id=DEVELOPER_CHAT_ID,
                    message_thread_id=DEVELOPER_THREAD_ID,
                    text=final_message,
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
                        context.bot.send_message,
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

        logfire.info(f"Error notification sent to developer ({len(chunked_messages)} parts).")
