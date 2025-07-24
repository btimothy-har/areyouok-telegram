import asyncio
import hashlib
import logging
from collections import defaultdict

from telegram.ext import ContextTypes

from areyouok_telegram.data import Messages

logger = logging.getLogger(__name__)

JOB_LOCK = defaultdict(asyncio.Lock)


class ConversationProcessor:
    """
    A class-based job processor for handling conversations in a specific chat.

    This processor:
    1. Fetches recent messages for a specific chat
    2. Processes messages and determines if a reply is needed
    3. Sends replies and saves them to the database
    """

    def __init__(self, chat_id: str):
        """
        Initialize the conversation processor for a speci   fic chat.

        Args:
            chat_id: The chat ID to process
            delay_seconds: How long to wait before processing (default: 30 seconds)
        """
        self.chat_id = chat_id

    @property
    def job_name(self) -> str:
        """Generate a consistent job name for this chat."""
        return f"conversation_processor:{self.chat_id}"

    @property
    def job_id(self) -> str:
        return hashlib.md5(self.job_name.encode()).hexdigest()

    async def process(self, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG002
        """Process conversation for this chat."""
        logger.info(f"Processing conversation for chat {self.chat_id}")

        print(f"Processing conversation for chat {self.chat_id}")

        await asyncio.sleep(5)  # Simulate delay for processing

        # async with async_database_session() as session:
        #     # Fetch recent messages for this specific chat
        #     cutoff_time = datetime.now(UTC) - timedelta(seconds=self.delay_seconds + 5)

        #     stmt = (
        #         select(Messages)
        #         .where(Messages.chat_id == self.chat_id)
        #         .where(Messages.created_at > cutoff_time)
        #         .order_by(Messages.created_at)
        #     )

        #     result = await session.execute(stmt)
        #     messages = result.scalars().all()

        #     if not messages:
        #         logger.debug(f"No recent messages for chat {self.chat_id}")
        #         return

        #     await self._process_messages(context, session, messages)

    async def _process_messages(self, context: ContextTypes.DEFAULT_TYPE, session, messages: list[Messages]) -> None:
        """Process messages for this chat and send appropriate replies."""
        logger.debug(f"Processing {len(messages)} messages for chat {self.chat_id}")

        # For now, send a simple "Are you ok?" reply to the most recent message
        # This is where we'll add more sophisticated conversation logic later

        latest_message = messages[-1]

        try:
            # Send reply to the latest message
            reply_text = "Are you ok? 🤔"

            sent_message = await context.bot.send_message(
                chat_id=int(self.chat_id), text=reply_text, reply_to_message_id=int(latest_message.message_id)
            )

            # Save the sent message to database
            await Messages.new_or_update(
                session=session,
                user_id=context.bot.id,  # Bot's user ID as the sender
                chat_id=self.chat_id,
                message=sent_message,
            )

            await session.commit()
            logger.info(f"Sent reply to chat {self.chat_id}, message {latest_message.message_id}")

        except Exception:
            logger.exception(f"Failed to send reply to chat {self.chat_id}")
            await session.rollback()


async def schedule_conversation_job(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    """
    Schedule a conversation processing job for a specific chat.

    Args:
        context: The bot context
        chat_id: The chat ID to process
        delay_seconds: How long to wait before processing (default: 30 seconds)
    """
    processor = ConversationProcessor(chat_id)

    async with JOB_LOCK[str(chat_id)]:
        # Check if a job already exists for this chat
        existing_jobs = context.job_queue.get_jobs_by_name(processor.job_name)
        if existing_jobs:
            logger.debug(f"Job already scheduled for chat {chat_id}, skipping")
            return

        # Schedule the job to run once after the specified delay
        new_job = context.job_queue.run_repeating(
            callback=processor.process,
            interval=1,
            name=processor.job_name,
            chat_id=chat_id,
            job_kwargs={
                "id": processor.job_name,
                "coalesce": True,
                "max_instances": 1,
            },
        )
        await new_job.run(context.application)
