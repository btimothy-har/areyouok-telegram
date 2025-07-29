import logging
from abc import abstractmethod
from datetime import UTC
from datetime import datetime

import pydantic
import telegram
from telegram.constants import ReactionEmoji
from telegram.ext import ContextTypes

from areyouok_telegram.data import Messages
from areyouok_telegram.data.connection import AsyncSessionLocal

logger = logging.getLogger(__name__)


class BaseAgentResponse(pydantic.BaseModel):
    """Base class for agent responses."""

    reasoning: str = pydantic.Field(
        description="The reasoning behind the agent's decision, used for debugging and understanding the response."
    )

    @property
    def response_type(self) -> str:
        """Return the type of response as a string."""
        return self.__class__.__name__

    @abstractmethod
    async def execute(self, db_connection: AsyncSessionLocal, context: ContextTypes.DEFAULT_TYPE, chat_id: str) -> None:
        """Execute the response action in the given context."""
        raise NotImplementedError("Subclasses must implement this method.")


class TextResponse(BaseAgentResponse):
    """Response model for text replies."""

    message_text: str = pydantic.Field(description="The text message to send as a reply to the user.")
    reply_to_message_id: str | None = pydantic.Field(
        default=None, description="Optional message ID to reply to, if the response is a reply to a specific message."
    )

    async def execute(
        self,
        db_connection: AsyncSessionLocal,  # noqa: ARG002
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: str,
    ) -> telegram.Message | None:
        """Execute the response action in the given context."""

        if self.reply_to_message_id:
            reply_parameters = telegram.ReplyParameters(
                message_id=int(self.reply_to_message_id),
                allow_sending_without_reply=True,
            )
        else:
            reply_parameters = None

        try:
            reply_message = await context.bot.send_message(
                chat_id=int(chat_id),
                text=self.message_text,
                reply_parameters=reply_parameters,
            )
        except Exception:
            logger.exception(f"Failed to send text reply to chat {chat_id}")
            return None
        else:
            return reply_message


class ReactionResponse(BaseAgentResponse):
    """Response model for emoji reactions."""

    react_to_message_id: str = pydantic.Field(description="The message ID to react to with an emoji.")
    emoji: ReactionEmoji = pydantic.Field(description="The emoji to use for the reaction.")

    async def execute(
        self, db_connection: AsyncSessionLocal, context: ContextTypes.DEFAULT_TYPE, chat_id: str
    ) -> telegram.MessageReactionUpdated | None:
        message, _ = await Messages.retrieve_message_by_id(
            session=db_connection,
            message_id=self.react_to_message_id,
            chat_id=chat_id,
        )

        if not message:
            logger.error(f"Message with ID {self.react_to_message_id} not found in chat {chat_id}")
            return None

        if message.from_user.id == context.bot.id:
            logger.warning(f"Cannot react to own message {self.react_to_message_id} in chat {chat_id}")
            return None

        try:
            react_sent = await context.bot.set_message_reaction(
                chat_id=int(chat_id),
                message_id=int(self.react_to_message_id),
                reaction=self.emoji,
            )
        except Exception:
            logger.exception(f"Failed to send reaction to message {self.react_to_message_id} in chat {chat_id}")
            return None
        else:
            if react_sent:
                # Manually create MessageReactionUpdated object as Telegram API does not return it
                reaction_message = telegram.MessageReactionUpdated(
                    chat=message.chat,
                    message_id=int(self.react_to_message_id),
                    date=datetime.now(UTC),
                    old_reaction=(),
                    new_reaction=(telegram.ReactionTypeEmoji(emoji=self.emoji),),
                    user=await context.bot.get_me(),
                )

            return reaction_message

        return None


class DoNothingResponse(BaseAgentResponse):
    """Response model for do-nothing actions."""

    async def execute(self, db_connection: AsyncSessionLocal, context: ContextTypes.DEFAULT_TYPE, chat_id: str) -> None:  # noqa: ARG002
        """Execute the do-nothing action."""
        logger.debug(f"DoNothingResponse executed for chat {chat_id}. No action taken.")
        return None
