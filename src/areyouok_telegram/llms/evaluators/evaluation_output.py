import pydantic


class EvaluationResponse(pydantic.BaseModel):
    score: float = pydantic.Field(
        description="Evaluation score between 0.0 and 1.0",
        ge=0.0,
        le=1.0,
    )
    reasoning: str = pydantic.Field(
        description=(
            "Reasoning behind the evaluation score, explaining why the score was given. "
            "Do not include the original message or response, whether in part or full. "
            "300 character limit."
        ),
        max_length=300,
    )
