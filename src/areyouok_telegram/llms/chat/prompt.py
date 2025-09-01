import pydantic

from areyouok_telegram.llms.chat import constants


class BaseChatPromptTemplate(pydantic.BaseModel):
    identity: str = pydantic.Field(default=constants.IDENTITY_PROMPT)
    rules: str = pydantic.Field(default=constants.RULES_PROMPT)
    knowledge: str = pydantic.Field(default=constants.KNOWLEDGE_PROMPT)
    response: str
    message: str | None = None
    objectives: str | None = None
    personality: str | None = None

    def as_prompt_string(self):
        prompt_parts = [
            f"<identity>{self.identity}</identity>",
            f"<rules>{self.rules}</rules>",
            f"<response>{self.response}</response>",
            f"<knowledge>{self.knowledge}</knowledge>",
        ]

        if self.message:
            prompt_parts.append(f"<message>{self.message}</message>")

        if self.objectives:
            prompt_parts.append(f"<objectives>{self.objectives}</objectives>")

        if self.personality:
            prompt_parts.append(f"<personality>{self.personality}</personality>")

        return "\n".join(prompt_parts)
