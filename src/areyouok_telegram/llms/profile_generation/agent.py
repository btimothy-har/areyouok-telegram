import pydantic
import pydantic_ai

from areyouok_telegram.llms.models import Gemini25Flash
from areyouok_telegram.llms.profile_generation.constants import AGENT_INSTRUCTIONS
from areyouok_telegram.llms.profile_generation.constants import EMOTIONAL_PATTERNS_DESC
from areyouok_telegram.llms.profile_generation.constants import IDENTITY_DESC
from areyouok_telegram.llms.profile_generation.constants import KEY_INFORMATION_DESC
from areyouok_telegram.llms.profile_generation.constants import PREFERENCES_DESC
from areyouok_telegram.llms.profile_generation.constants import PROFILE_TEMPLATE
from areyouok_telegram.llms.profile_generation.constants import PROFILE_UPDATE_DESC


class ProfileTemplate(pydantic.BaseModel):
    """Model for user profile synthesis."""

    identity: str = pydantic.Field(
        description=IDENTITY_DESC,
    )
    preferences: str = pydantic.Field(
        description=PREFERENCES_DESC,
    )
    emotional_patterns: str = pydantic.Field(
        description=EMOTIONAL_PATTERNS_DESC,
    )
    key_information: str = pydantic.Field(
        description=KEY_INFORMATION_DESC,
    )
    profile_update: str = pydantic.Field(
        description=PROFILE_UPDATE_DESC,
    )

    @property
    def content(self) -> str:
        """Return the profile as a formatted string."""
        return PROFILE_TEMPLATE.format(
            identity=self.identity,
            preferences=self.preferences,
            emotional_patterns=self.emotional_patterns,
            key_information=self.key_information,
            profile_update=self.profile_update,
        )


agent_model = Gemini25Flash(
    model_settings=pydantic_ai.models.google.GoogleModelSettings(
        temperature=0.0,
        google_thinking_config={"thinking_budget": 0},
    ),
)

profile_generation_agent = pydantic_ai.Agent(
    model=agent_model.model,
    output_type=ProfileTemplate,
    name="profile_generation_agent",
    end_strategy="exhaustive",
)


@profile_generation_agent.instructions
def profile_generation_instructions() -> str:
    return AGENT_INSTRUCTIONS
