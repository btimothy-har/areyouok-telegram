from areyouok_telegram.llms.chat.agents.chat import (
    AgentResponse as ChatAgentResponse,
    ChatAgentDependencies,
    chat_agent,
)
from areyouok_telegram.llms.chat.agents.onboarding import (
    AgentResponse as OnboardingAgentResponse,
    OnboardingAgentDependencies,
    onboarding_agent,
)
from areyouok_telegram.llms.chat.responses import (
    DoNothingResponse,
    KeyboardResponse,
    ReactionResponse,
    SwitchPersonalityResponse,
    TextResponse,
    TextWithButtonsResponse,
)

AgentResponse = ChatAgentResponse | OnboardingAgentResponse

__all__ = [
    "chat_agent",
    "ChatAgentDependencies",
    "ChatAgentResponse",
    "ReactionResponse",
    "TextResponse",
    "TextWithButtonsResponse",
    "onboarding_agent",
    "OnboardingAgentDependencies",
    "OnboardingAgentResponse",
    "TextWithButtonsResponse",
    "DoNothingResponse",
    "SwitchPersonalityResponse",
    "AgentResponse",
    "DoNothingResponse",
    "TextWithButtonsResponse",
    "KeyboardResponse",
]
