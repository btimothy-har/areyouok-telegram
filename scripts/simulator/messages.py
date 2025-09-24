import json
from datetime import datetime
from typing import Literal

import pydantic
import pydantic_ai


class ConversationMessage(pydantic.BaseModel):
    """Simple message model for conversation tracking."""

    message_id: int
    role: Literal["user", "bot"]
    timestamp: datetime
    text: str
    reasoning: str | None = None
    personality: str | None = None  # Personality used for bot messages

    def to_model_message(
        self, current_time: datetime, perspective: Literal["user", "bot"]
    ) -> pydantic_ai.messages.ModelMessage:
        """Convert to pydantic_ai ModelMessage format from given perspective.

        Args:
            current_time: Reference time for calculating relative timestamps
            perspective: Which agent's perspective to use ("user" or "bot")
                - From bot's perspective: user messages are requests, bot messages are responses
                - From user's perspective: user messages are responses, bot messages are requests
        """
        # From user's perspective, only show clean text without metadata
        if perspective == "user":
            content = self.text
        else:
            # From bot's perspective, include full metadata structure
            seconds_ago = int((current_time - self.timestamp).total_seconds())
            content_dict = {
                "timestamp": f"{seconds_ago} seconds ago",
                "event_type": "message",
                "text": self.text,
                "message_id": str(self.message_id),
            }

            # Include reasoning for bot responses when viewed from bot's perspective
            if self.role == "bot" and perspective == "bot" and self.reasoning:
                content_dict["reasoning"] = self.reasoning

            content = json.dumps(content_dict)

        # Determine if this message should be a request or response from the given perspective
        if perspective == "bot":
            # From bot's perspective: user messages are requests, bot messages are responses
            is_request = self.role == "user"
        else:  # perspective == "user"
            # From user's perspective: user messages are responses, bot messages are requests
            is_request = self.role == "bot"

        if is_request:
            return pydantic_ai.messages.ModelRequest(
                parts=[
                    pydantic_ai.messages.UserPromptPart(
                        content=content,
                        timestamp=self.timestamp,
                        part_kind="user-prompt",
                    )
                ],
                kind="request",
            )
        else:
            return pydantic_ai.messages.ModelResponse(
                parts=[pydantic_ai.messages.TextPart(content=content, part_kind="text")],
                timestamp=self.timestamp,
                kind="response",
            )
