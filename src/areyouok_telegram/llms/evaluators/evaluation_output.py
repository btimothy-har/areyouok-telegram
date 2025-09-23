import pydantic


class EvaluationResponse(pydantic.BaseModel):
    score: float = pydantic.Field(
        description="Evaluation score between 0.0 and 1.0",
        ge=0.0,
        le=1.0,
    )
    reasoning: str = pydantic.Field(
        description=(
            "A brief reasoning, no more than 500 characters, explaining the evaluation score. "
            "Do not include the original message or response, whether in part or full. "
        ),
        max_length=500,
    )
