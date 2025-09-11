import pydantic
import pydantic_ai

from areyouok_telegram.data import UserMetadata
from areyouok_telegram.data.models.user_metadata import InvalidTimezoneError
from areyouok_telegram.llms.exceptions import MetadataFieldUpdateError
from areyouok_telegram.llms.models import GPT5Nano


class CountryTimezone(pydantic.BaseModel):
    """Model for Country Timezone response."""

    timezone: str = pydantic.Field(description="The timezone for the country in IANA format.")
    has_multiple: bool = pydantic.Field(default=False, description="Whether this country has multiple timezones.")


country_timezone_agent = pydantic_ai.Agent(
    model=GPT5Nano().model,
    output_type=CountryTimezone,
    name="country_timezone_agent",
    end_strategy="exhaustive",
)


@country_timezone_agent.instructions
def generate_instructions() -> str:
    return """
Given the input country, identify the appropriate timezone for the country.

Where there may be multiple timezones for the country, return the best fit by \
convention (i.e. by the capital or most populous city).

Return the timezone string in IANA format, and only the timezone string.
    """


@country_timezone_agent.output_validator
async def validate_country_timezone_output(ctx: pydantic_ai.RunContext, data: CountryTimezone) -> CountryTimezone:  # noqa: ARG001
    try:
        UserMetadata._validate_timezone(data.timezone)
    except InvalidTimezoneError as e:
        raise MetadataFieldUpdateError("timezone") from e

    return data
