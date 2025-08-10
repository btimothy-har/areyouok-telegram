"""Pydantic models for personality definitions."""

from pydantic import BaseModel
from pydantic import Field

PERSONALITY_TEMPLATE = """
<core_personality>
personality: {name}
{core_personality}
</core_personality>

<communication_style>
{communication_style}
</communication_style>

<emotional_expression>
{emotional_expression}
</emotional_expression>

<interaction_patterns>
{interaction_patterns}
</interaction_patterns>

<boundaries>
{boundaries}
</boundaries>

<therapeutic_approach>
{therapeutic_approach}
</therapeutic_approach>

<language_patterns>
{language_patterns}
</language_patterns>

<special_features>
{special_features}
</special_features>
"""


class PersonalityModel(BaseModel):
    name: str = Field(description="Name identifier for the personality")

    core_personality: str = Field(description="Content of the <core_personality> section")

    communication_style: str = Field(description="Content of the <communication_style> section")

    emotional_expression: str = Field(description="Content of the <emotional_expression> section")

    interaction_patterns: str = Field(description="Content of the <interaction_patterns> section")

    boundaries: str = Field(description="Content of the <boundaries> section")

    therapeutic_approach: str = Field(description="Content of the <therapeutic_approach> section")

    language_patterns: str = Field(description="Content of the <language_patterns> section")

    special_features: str = Field(description="Content of the <special_features> section")

    @property
    def as_prompt_string(self) -> str:
        """Convert the personality model to a prompt string format."""
        return PERSONALITY_TEMPLATE.format(
            name=self.name,
            core_personality=self.core_personality,
            communication_style=self.communication_style,
            emotional_expression=self.emotional_expression,
            interaction_patterns=self.interaction_patterns,
            boundaries=self.boundaries,
            therapeutic_approach=self.therapeutic_approach,
            language_patterns=self.language_patterns,
            special_features=self.special_features,
        )
