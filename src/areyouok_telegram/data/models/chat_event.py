# ruff: noqa: TRY003

import json
from datetime import datetime

import pydantic
import pydantic_ai
import telegram

from areyouok_telegram.data.models.context import Context
from areyouok_telegram.data.models.context import ContextType
from areyouok_telegram.data.models.media import MediaFiles
from areyouok_telegram.data.models.messages import Messages

CONTEXT_TYPE_MAP = {
    ContextType.SESSION.value: "prior_conversation_summary",
    ContextType.RESPONSE.value: "silent_response",
    ContextType.PERSONALITY.value: "switch_personality",
    ContextType.METADATA.value: "user_metadata_update",
}

SYSTEM_USER_ID = "system"


class ChatEvent(pydantic.BaseModel):
    """Universal model combining Message and Context data into a single event model."""

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    timestamp: datetime
    event_type: str
    event_data: dict
    attachments: list[MediaFiles] = pydantic.Field(default_factory=list)
    user_id: str | None = None

    @pydantic.model_validator(mode="after")
    def attachments_only_allowed_for_messages(self) -> "ChatEvent":
        if self.event_type == "message":
            return self
        if self.attachments:
            raise ValueError("Attachments are only allowed for message events.")
        return self

    @pydantic.model_validator(mode="after")
    def user_id_must_be_provided_for_messages(self) -> "ChatEvent":
        if self.event_type == "message":
            if not self.user_id:
                raise ValueError("User ID must be provided for message events.")
            return self
        if self.user_id:
            raise ValueError("User ID is only allowed for message events.")
        return self

    @classmethod
    def from_message(cls, message: Messages, attachments: list[MediaFiles]) -> "ChatEvent":
        if message.message_type == "Message":
            event_type = "message"
            event_data = {
                "text": message.telegram_object.text or message.telegram_object.caption or "",
                "message_id": str(message.message_id),
            }

        elif message.message_type == "MessageReactionUpdated":
            event_type = "reaction"

            # Handle reactions, assuming only emoji reactions for simplicity
            # TODO: Handle custom and paid reactions
            reaction_string = ", ".join(
                [
                    r.emoji
                    for r in message.telegram_object.new_reaction
                    if r.type == telegram.constants.ReactionType.EMOJI
                ]
            )
            event_data = {
                "emojis": reaction_string,
                "to_message_id": str(message.message_id),
            }

        else:
            raise TypeError(
                f"Unsupported message type: {type(message)}. Only Message and MessageReactionUpdated are supported."
            )

        if message.reasoning:
            event_data["reasoning"] = message.reasoning

        return cls(
            timestamp=message.telegram_object.date,
            event_type=event_type,
            event_data=event_data,
            attachments=attachments,
            user_id=message.user_id,
        )

    @classmethod
    def from_context(cls, context: Context) -> "ChatEvent":
        return cls(
            event_type=CONTEXT_TYPE_MAP.get(context.type, "context"),
            event_data={
                "content": context.content,
            },
            timestamp=context.created_at,
            attachments=[],
            user_id=None,
        )

    def to_model_message(self, bot_id: str, ts_reference: datetime) -> pydantic_ai.messages.ModelResponse:
        """Convert the chat event to a model message for AI processing."""

        default_payload = {
            "timestamp": (f"{(ts_reference - self.timestamp).total_seconds()} seconds ago"),
            "event_type": self.event_type,
            **self.event_data,  # Unpack the event data directly into the payload
        }

        if self.user_id and self.user_id not in (bot_id, SYSTEM_USER_ID):
            user_content = [json.dumps(default_payload)]

            compatible_media = [m for m in self.attachments if m.is_anthropic_supported]
            for m in compatible_media:
                if m.mime_type.startswith("image/") or m.mime_type == "application/pdf":
                    user_content.append(
                        pydantic_ai.BinaryContent(
                            data=m.bytes_data,
                            media_type=m.mime_type,
                        )
                    )
                elif m.mime_type.startswith("text/"):
                    user_content.append(m.bytes_data.decode("utf-8"))

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
