from enum import Enum

from areyouok_telegram.llms.exceptions import InvalidPersonalityError

from .anchoring import ANCHORING_PERSONALITY
from .celebration import CELEBRATION_PERSONALITY
from .exploration import EXPLORATION_PERSONALITY
from .witnessing import WITNESSING_PERSONALITY


class PersonalityTypes(Enum):
    """Enum for personality types."""

    ANCHORING = "anchoring"
    CELEBRATION = "celebration"
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
        elif self == PersonalityTypes.EXPLORATION:
            return EXPLORATION_PERSONALITY.as_prompt_string
        elif self == PersonalityTypes.WITNESSING:
            return WITNESSING_PERSONALITY.as_prompt_string
        else:
            raise InvalidPersonalityError(self.value)


__all__ = [
    "ANCHORING_PERSONALITY",
    "CELEBRATION_PERSONALITY",
    "EXPLORATION_PERSONALITY",
    "WITNESSING_PERSONALITY",
]
