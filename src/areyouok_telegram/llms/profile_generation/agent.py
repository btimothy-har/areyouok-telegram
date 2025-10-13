import pydantic
import pydantic_ai

from areyouok_telegram.llms.models import GPT5
from areyouok_telegram.llms.profile_generation.constants import AGENT_INSTRUCTIONS
from areyouok_telegram.llms.profile_generation.constants import CHANGE_LOG_DESC
from areyouok_telegram.llms.profile_generation.constants import EMOTIONAL_PATTERNS_DESC
from areyouok_telegram.llms.profile_generation.constants import GOALS_OUTCOMES_DESC
from areyouok_telegram.llms.profile_generation.constants import IDENTITY_MARKERS_DESC
from areyouok_telegram.llms.profile_generation.constants import PROFILE_TEMPLATE
from areyouok_telegram.llms.profile_generation.constants import SAFETY_PLAN_DESC
from areyouok_telegram.llms.profile_generation.constants import STRENGTHS_VALUES_DESC


class ProfileTemplate(pydantic.BaseModel):
    """Model for user profile synthesis."""

    identity_markers: str = pydantic.Field(
        description=IDENTITY_MARKERS_DESC,
    )
    strengths_values: str = pydantic.Field(
        description=STRENGTHS_VALUES_DESC,
    )
    goals_outcomes: str = pydantic.Field(
        description=GOALS_OUTCOMES_DESC,
    )
    emotional_patterns: str = pydantic.Field(
        description=EMOTIONAL_PATTERNS_DESC,
    )
    safety_plan: str = pydantic.Field(
        description=SAFETY_PLAN_DESC,
    )
    change_log: str = pydantic.Field(
        description=CHANGE_LOG_DESC,
    )

    @property
    def content(self) -> str:
        """Return the profile as a formatted string."""
        return PROFILE_TEMPLATE.format(
            identity_markers=self.identity_markers,
            strengths_values=self.strengths_values,
            goals_outcomes=self.goals_outcomes,
            emotional_patterns=self.emotional_patterns,
            safety_plan=self.safety_plan,
        )


agent_model = GPT5(
    model_settings=pydantic_ai.settings.ModelSettings(
        temperature=0.2,
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
