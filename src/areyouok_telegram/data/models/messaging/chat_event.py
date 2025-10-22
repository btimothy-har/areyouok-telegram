"""ChatEvent helper model for combining Message and Context data."""

import json
from datetime import datetime

import pydantic
import pydantic_ai
import telegram

from areyouok_telegram.data.exceptions import BaseDataError
from areyouok_telegram.data.models.messaging.context import Context, ContextType
from areyouok_telegram.data.models.messaging.media_file import MediaFile
from areyouok_telegram.data.models.messaging.message import Message
from areyouok_telegram.utils.text import format_relative_time

CONTEXT_TYPE_MAP = {
    ContextType.SESSION.value: "prior_conversation_summary",
    ContextType.RESPONSE.value: "silent_response",
    ContextType.PERSONALITY.value: "switch_personality",
    ContextType.METADATA.value: "user_metadata_update",
    ContextType.ACTION.value: "user_button_action",
    ContextType.MEMORY.value: "user_memory",
    ContextType.PROFILE_UPDATE.value: "user_profile_update",
    ContextType.PROFILE.value: "user_profile",
}

SYSTEM_USER_ID = "system"


class AttachmentsOnlyAllowedForMessagesError(ValueError, BaseDataError):
    """Raised when attachments are only allowed for message events."""

    def __init__(self, event_type: str, attachments: list[MediaFile]):
        super().__init__("Attachments are only allowed for message events.")
        self.event_type = event_type
        self.attachments = attachments


class UserIDRequiredForMessagesError(ValueError, BaseDataError):
    """Raised when user ID is required for message events."""

    def __init__(self, event_type: str):
        super().__init__("User ID must be provided for message and reaction events.")
        self.event_type = event_type


class UnsupportedMessageTypeError(TypeError, BaseDataError):
    """Raised when an unsupported message type is provided."""

    def __init__(self, message_type: str):
        super().__init__(
            f"Unsupported message type: {message_type}. Only Message and MessageReactionUpdated are supported."
        )
        self.message_type = message_type


class ChatEvent(pydantic.BaseModel):
    """Universal model combining Message and Context data into a single event model."""

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    timestamp: datetime
    event_type: str
    event_data: dict
    attachments: list[MediaFile] = pydantic.Field(default_factory=list)
    user_id: str | None = None

    @pydantic.model_validator(mode="after")
    def attachments_only_allowed_for_messages(self) -> "ChatEvent":
        if self.event_type == "message":
            return self
        if self.attachments:
            raise AttachmentsOnlyAllowedForMessagesError(self.event_type, self.attachments)
        return self

    @pydantic.model_validator(mode="after")
    def user_id_must_be_provided_for_messages(self) -> "ChatEvent":
        if self.event_type in ["message", "reaction"]:
            if not self.user_id:
                raise UserIDRequiredForMessagesError(self.event_type)
        return self

    @classmethod
    def from_message(cls, message: Message, attachments: list[MediaFile]) -> "ChatEvent":
        if message.message_type == "Message":
            event_type = "message"
            event_data = {
                "text": message.telegram_object.text or message.telegram_object.caption or "",
                "message_id": str(message.telegram_message_id),
            }

            if message.telegram_object.reply_markup:
                if isinstance(message.telegram_object.reply_markup, telegram.ReplyKeyboardMarkup):
                    kb_options = [
                        button.text if isinstance(button, telegram.KeyboardButton) else str(button)
                        for row in message.telegram_object.reply_markup.keyboard
                        for button in row
                    ]
                    event_data["keyboard_options"] = kb_options

                elif isinstance(message.telegram_object.reply_markup, telegram.InlineKeyboardMarkup):
                    kb_options = []
                    for row in message.telegram_object.reply_markup.inline_keyboard:
                        for b in row:
                            kb_options.append({"text": b.text, "callback_data": b.callback_data})
                    event_data["message_buttons"] = kb_options

        elif message.message_type == "MessageReactionUpdated":
            event_type = "reaction"

            # Handle reactions, assuming only emoji reactions for simplicity
            # TODO: Handle custom and paid reactions
            reaction_string = ", ".join([
                r.emoji for r in message.telegram_object.new_reaction if r.type == telegram.constants.ReactionType.EMOJI
            ])
            event_data = {
                "emojis": reaction_string,
                "to_message_id": str(message.telegram_message_id),
            }

        else:
            raise UnsupportedMessageTypeError(message.message_type)

        if message.reasoning:
            event_data["reasoning"] = message.reasoning

        return cls(
            timestamp=message.telegram_object.date,
            event_type=event_type,
            event_data=event_data,
            attachments=attachments,
            user_id=message.telegram_user_id,
        )

    @classmethod
    def from_context(cls, context: Context) -> "ChatEvent":
        # Note: For Context, we need to get chat_id from the context model
        # Since Context now uses internal IDs, we need to convert to telegram_chat_id if needed
        # For now, we'll use the internal chat_id as a string
        return cls(
            event_type=CONTEXT_TYPE_MAP.get(context.type, "context"),
            event_data={
                "content": context.content,
            },
            timestamp=context.created_at,
            attachments=[],
            user_id=str(context.chat_id) if context.type == ContextType.ACTION.value else None,
        )

    def to_model_message(self, bot_id: str, ts_reference: datetime) -> pydantic_ai.messages.ModelMessage:
        """Convert the chat event to a model message for AI processing."""

        default_payload = {
            "timestamp": format_relative_time(self.timestamp, reference_time=ts_reference),
            "event_type": self.event_type,
            **self.event_data,  # Unpack the event data directly into the payload
        }

        if self.user_id and self.user_id not in (bot_id, SYSTEM_USER_ID):
            user_content = [json.dumps(default_payload)]

            compatible_media = [m for m in self.attachments if m.is_openai_google_supported]
            for m in compatible_media:
                if m.mime_type.startswith("text/"):
                    user_content.append(m.bytes_data.decode("utf-8"))
                else:
                    user_content.append(
                        pydantic_ai.BinaryContent(
                            data=m.bytes_data,
                            media_type=m.mime_type,
                        )
                    )

            model_message = pydantic_ai.messages.ModelRequest(
                parts=[
                    pydantic_ai.messages.UserPromptPart(
                        content=user_content if len(user_content) > 1 else user_content[0],
                        timestamp=self.timestamp,
                        part_kind="user-prompt",
                    )
                ],
                kind="request",
            )

        else:
            model_message = pydantic_ai.messages.ModelResponse(
                parts=[pydantic_ai.messages.TextPart(content=json.dumps(default_payload), part_kind="text")],
                timestamp=self.timestamp,
                kind="response",
            )

        return model_message
