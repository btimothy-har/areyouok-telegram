from areyouok_telegram.llms.chat.agents.chat import AgentResponse as ChatAgentResponse
from areyouok_telegram.llms.chat.agents.chat import ChatAgentDependencies
from areyouok_telegram.llms.chat.agents.chat import chat_agent
from areyouok_telegram.llms.chat.agents.onboarding import AgentResponse as OnboardingAgentResponse
from areyouok_telegram.llms.chat.agents.onboarding import OnboardingAgentDependencies
from areyouok_telegram.llms.chat.agents.onboarding import onboarding_agent
from areyouok_telegram.llms.chat.responses import DoNothingResponse
from areyouok_telegram.llms.chat.responses import ReactionResponse
from areyouok_telegram.llms.chat.responses import SwitchPersonalityResponse
from areyouok_telegram.llms.chat.responses import TextResponse
from areyouok_telegram.llms.chat.responses import TextWithButtonsResponse

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
]
