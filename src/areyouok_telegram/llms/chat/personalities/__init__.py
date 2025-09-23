from enum import Enum

from areyouok_telegram.llms.chat.personalities.anchoring import ANCHORING_PERSONALITY
from areyouok_telegram.llms.chat.personalities.celebration import CELEBRATION_PERSONALITY
from areyouok_telegram.llms.chat.personalities.companionship import COMPANIONSHIP_PERSONALITY
from areyouok_telegram.llms.chat.personalities.exploration import EXPLORATION_PERSONALITY
from areyouok_telegram.llms.chat.personalities.witnessing import WITNESSING_PERSONALITY
from areyouok_telegram.llms.exceptions import InvalidPersonalityError


class PersonalityTypes(Enum):
    """Enum for personality types."""

    ANCHORING = "anchoring"
    CELEBRATION = "celebration"
    COMPANIONSHIP = "companionship"
    EXPLORATION = "exploration"
    WITNESSING = "witnessing"

    @classmethod
    def choices(cls):
        return [member.value for member in cls]

    @classmethod
    def get_by_value(cls, value: str):
        """Get the personality type by its value."""
        for member in cls:
            if member.value == value:
                return member
        raise InvalidPersonalityError(value)

    def prompt_text(self) -> str:
        """Return the prompt text for the personality."""
        if self == PersonalityTypes.ANCHORING:
            return ANCHORING_PERSONALITY.as_prompt_string
        elif self == PersonalityTypes.CELEBRATION:
            return CELEBRATION_PERSONALITY.as_prompt_string
        elif self == PersonalityTypes.COMPANIONSHIP:
            return COMPANIONSHIP_PERSONALITY.as_prompt_string
        elif self == PersonalityTypes.EXPLORATION:
            return EXPLORATION_PERSONALITY.as_prompt_string
        elif self == PersonalityTypes.WITNESSING:
            return WITNESSING_PERSONALITY.as_prompt_string
        else:
            raise InvalidPersonalityError(self.value)


__all__ = [
    "ANCHORING_PERSONALITY",
    "CELEBRATION_PERSONALITY",
    "COMPANIONSHIP_PERSONALITY",
    "EXPLORATION_PERSONALITY",
    "WITNESSING_PERSONALITY",
]
