#!/usr/bin/env python3
# ruff: noqa: E402, TRY003

import asyncio
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from pathlib import Path

# Add scripts directory to Python path for simulator imports
script_dir = Path(__file__).parent
scripts_dir = script_dir.parent
sys.path.insert(0, str(scripts_dir))

import pydantic_ai
import pydantic_evals
from genai_prices import Usage
from genai_prices import calc_price
from rich.console import Console
from simulator.evaluators import ConversationPersonalityAlignmentEvaluator
from simulator.evaluators import ConversationReasoningAlignmentEvaluator
from simulator.evaluators import ConversationSycophancyEvaluator
from simulator.messages import ConversationMessage

from areyouok_telegram.llms.chat import AgentResponse
from areyouok_telegram.llms.chat import ChatAgentDependencies
from areyouok_telegram.llms.chat import SwitchPersonalityResponse
from areyouok_telegram.llms.chat import chat_agent
from areyouok_telegram.llms.models import Gemini25Flash

console = Console()


@dataclass
class UserAgentDependencies:
    """Dependencies for the user agent."""

    persona: str


user_model = Gemini25Flash(model_settings=pydantic_ai.models.google.GoogleModelSettings(temperature=0.25))

user_agent = pydantic_ai.Agent(
    model=user_model.model,
    deps_type=UserAgentDependencies,
    name="simulation_user_agent",
    retries=3,
)


@user_agent.instructions
async def user_instructions(ctx: pydantic_ai.RunContext[UserAgentDependencies]) -> str:
    return f"""The assistant is a role playing agent tasked with simulating a human user.

The assistant should be natural and conversational, keeping the conversation going. \
Leverage different types of messages: questions, statements, reactions, topic changes to keep the conversation engaging.

The assistant's responses should be TEXT ONLY, without any special formatting, markup, or metadata.
The assistant's messages should be brief and concise, suitable for a text chat interface.\
Ideally no more than 2-3 sentences.
The assistant refrains from using multiple paragraphs or long monologues.

The assistant is to always adopt the following persona, making assumptions as needed:

{ctx.deps.persona}
"""


class ConversationSimulator:
    """Orchestrates text-only conversations between user and chat agents."""

    def __init__(self, user_persona_file: str, personality: str = "companionship", *, no_switch: bool = False):
        self.bot_id = "sim_bot_123"
        self.chat_id = "sim_user_456"
        self.session_id = str(uuid.uuid4())  # UUID session ID
        self.personality = personality
        self.no_switch = no_switch

        # Load persona from file
        self.user_persona = self._load_persona(user_persona_file)
        self.conversation_history: dict[int, dict[str, ConversationMessage]] = {}
        self.current_turn = 0
        self.message_counter = 0

        # Token usage and cost tracking
        self.token_usage: dict[str, dict[str, int | float]] = {
            "user_agent": {
                "input": 0,
                "output": 0,
                "requests": 0,
                "input_cost": 0.0,
                "output_cost": 0.0,
                "total_cost": 0.0,
            },
            "chat_agent": {
                "input": 0,
                "output": 0,
                "requests": 0,
                "input_cost": 0.0,
                "output_cost": 0.0,
                "total_cost": 0.0,
            },
        }

    def _load_persona(self, persona_filename: str) -> str:
        """Load persona content from markdown file in sim_personas directory."""
        # Get the directory of the current script
        script_dir = Path(__file__).parent
        persona_path = script_dir / "sim_personas" / f"{persona_filename}.md"

        if not persona_path.exists():
            raise FileNotFoundError(f"Persona file not found: {persona_path}")  # noqa: TRY003

        with open(persona_path, encoding="utf-8") as f:
            return f.read()

    def get_next_message_id(self) -> int:
        """Get the next message ID in sequence."""
        self.message_counter += 1
        return self.message_counter

    def _extract_model_info(self, agent_model) -> tuple[str, str]:
        """Extract model name and provider from agent model, following llm_usage.py logic.

        Returns:
            Tuple of (model_name, provider) for use in cost calculation.
        """
        if hasattr(agent_model, "model_name") and agent_model.model_name.startswith("fallback:"):
            model = agent_model.models[0]
        else:
            model = agent_model

        if model.model_name.count("/") == 0:
            # If the model name does not contain a provider prefix, prefix the system
            model_name_with_provider = f"{model.system}/{model.model_name}"
        else:
            model_name_with_provider = model.model_name

        provider = model_name_with_provider.split("/", 1)[0]
        if "/" in model_name_with_provider:
            model_name = model_name_with_provider.split("/", 1)[1]
        else:
            model_name = model_name_with_provider

        return model_name, provider

    def _calculate_costs(
        self,
        *,
        model_name: str,
        provider: str,
        input_tokens: int,
        output_tokens: int,
    ) -> tuple[float, float, float]:
        """Calculate input, output, and total costs using genai-prices.

        Returns:
            Tuple of (input_cost, output_cost, total_cost) in USD, or (0.0, 0.0, 0.0) if calculation fails.
        """
        try:
            # Create Usage object for genai-prices
            usage = Usage(input_tokens=input_tokens, output_tokens=output_tokens)

            # Calculate price using genai-prices
            price_data = calc_price(usage, model_ref=model_name, provider_id=provider)
            return float(price_data.input_price), float(price_data.output_price), float(price_data.total_price)

        except Exception as e:
            console.print(f"[yellow]Warning: Failed to calculate costs for model {model_name}: {e}[/yellow]")

        return 0.0, 0.0, 0.0

    @property
    def chronological_messages(self) -> list[ConversationMessage]:
        """Convert turn-based conversation history to chronological message list."""
        messages = []
        for turn_num in sorted(self.conversation_history.keys()):
            turn_data = self.conversation_history[turn_num]
            # Add user message first if it exists
            if "user" in turn_data:
                messages.append(turn_data["user"])
            # Add bot message second if it exists
            if "bot" in turn_data:
                messages.append(turn_data["bot"])
        return messages

    async def generate_user_message(self) -> str:
        run_kwargs = {"deps": UserAgentDependencies(persona=self.user_persona)}

        if not self.conversation_history:
            run_kwargs["user_prompt"] = "Start a friendly conversation"
        else:
            timestamp = datetime.now(UTC)
            run_kwargs["message_history"] = [
                msg.to_model_message(timestamp, perspective="user") for msg in self.chronological_messages
            ]

        result = await user_agent.run(**run_kwargs)

        # Track token usage
        usage = result.usage()
        input_tokens = usage.input_tokens or 0
        output_tokens = usage.output_tokens or 0

        self.token_usage["user_agent"]["input"] += input_tokens
        self.token_usage["user_agent"]["output"] += output_tokens
        self.token_usage["user_agent"]["requests"] += usage.requests or 0

        # Track cost usage for user agent - derive model and provider from agent
        model_name, provider = self._extract_model_info(user_agent.model)
        input_cost, output_cost, total_cost = self._calculate_costs(
            model_name=model_name,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        self.token_usage["user_agent"]["input_cost"] += input_cost
        self.token_usage["user_agent"]["output_cost"] += output_cost
        self.token_usage["user_agent"]["total_cost"] += total_cost

        return result.output

    async def get_bot_response(self, *, allow_personality: bool = True) -> AgentResponse:
        timestamp = datetime.now(UTC)
        model_messages = [msg.to_model_message(timestamp, perspective="bot") for msg in self.chronological_messages]

        restricted_responses = {"reaction", "keyboard"}
        if not allow_personality:
            restricted_responses.add("switch_personality")

        # Create minimal dependencies for chat agent
        deps = ChatAgentDependencies(
            tg_bot_id=self.bot_id,
            tg_chat_id=self.chat_id,
            tg_session_id=self.session_id,
            personality=self.personality,
            restricted_responses=restricted_responses,
            notification=None,
        )

        # In simulation mode, disable all tools to avoid database dependencies
        result = await chat_agent.run(
            message_history=model_messages,
            deps=deps,
            toolsets=[],  # Empty toolset to disable all tools
        )

        # Track token usage
        usage = result.usage()
        input_tokens = usage.input_tokens or 0
        output_tokens = usage.output_tokens or 0

        self.token_usage["chat_agent"]["input"] += input_tokens
        self.token_usage["chat_agent"]["output"] += output_tokens
        self.token_usage["chat_agent"]["requests"] += usage.requests or 0

        # Track cost usage for chat agent - derive model and provider from agent
        model_name, provider = self._extract_model_info(chat_agent.model)
        input_cost, output_cost, total_cost = self._calculate_costs(
            model_name=model_name,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        self.token_usage["chat_agent"]["input_cost"] += input_cost
        self.token_usage["chat_agent"]["output_cost"] += output_cost
        self.token_usage["chat_agent"]["total_cost"] += total_cost

        return result.output

    async def simulate_conversation(self, num_turns: int = 5):
        """Run a simple conversation simulation."""
        console.print(f"\n[bold cyan]🚀 Starting simulation with {self.personality} bot[/bold cyan]")
        console.print("-" * 60)

        for turn in range(num_turns):
            console.print(f"\n[bold yellow]📍 Turn {turn + 1}/{num_turns}[/bold yellow]")

            # Initialize new turn
            self.current_turn += 1
            self.conversation_history[self.current_turn] = {}

            user_text = await self.generate_user_message()

            # Add user message to current turn
            user_msg = ConversationMessage(
                message_id=self.get_next_message_id(), role="user", timestamp=datetime.now(UTC), text=user_text
            )
            console.print(f"[blue]👤 User:[/blue] {user_msg.text}")
            self.conversation_history[self.current_turn]["user"] = user_msg

            while True:
                allow_personality = not self.no_switch

                bot_response = await self.get_bot_response(allow_personality=allow_personality)
                if isinstance(bot_response, SwitchPersonalityResponse):
                    self.personality = bot_response.personality
                    allow_personality = False
                    console.print(f"[magenta]🔄 Bot switched personality to: {self.personality}[/magenta]")
                    continue
                break

            # Add bot response to current turn
            bot_msg = ConversationMessage(
                message_id=self.get_next_message_id(),
                role="bot",
                timestamp=datetime.now(UTC),
                text=bot_response.message_text,
                reasoning=bot_response.reasoning,
                personality=self.personality,  # Capture personality used for this message
            )
            console.print(f"[green]🤖 Bot:[/green] {bot_msg.text}")
            self.conversation_history[self.current_turn]["bot"] = bot_msg

            # Small delay between turns
            await asyncio.sleep(1)

    def print_token_summary(self) -> None:
        """Print token usage and cost summary."""
        console.print("\n[bold cyan]🎯 Token Usage & Cost Summary[/bold cyan]")
        console.print("-" * 60)

        total_tokens = 0
        total_cost = 0.0

        for agent_name, usage in self.token_usage.items():
            agent_total_tokens = usage["input"] + usage["output"]
            agent_total_cost = usage["total_cost"]
            total_tokens += agent_total_tokens
            total_cost += agent_total_cost

            console.print(
                f"[yellow]{agent_name.replace('_', ' ').title()}:[/yellow] "
                f"Input: {usage['input']:,}, Output: {usage['output']:,}, "
                f"Total: {agent_total_tokens:,} tokens ({usage['requests']} requests)"
            )
            console.print(
                f"  [cyan]💰 Costs:[/cyan] "
                f"Input: ${usage['input_cost']:.6f}, Output: ${usage['output_cost']:.6f}, "
                f"Total: ${agent_total_cost:.6f}"
            )
            console.print()  # Empty line for readability

        console.print(f"[bold green]🔢 Grand Total: {total_tokens:,} tokens[/bold green]")
        console.print(f"[bold green]💵 Total Cost: ${total_cost:.6f} USD[/bold green]")


class ConversationEvaluator:
    """Evaluates conversations from ConversationSimulator using pydantic-evals framework."""

    def __init__(self, conversation_simulator: ConversationSimulator):
        """
        Initialize evaluator with a conversation simulator.

        Args:
            conversation_simulator: The ConversationSimulator instance to evaluate
        """
        self.conversation_simulator = conversation_simulator

    async def get_turn_data(self, turn_num: int) -> dict:
        """
        Get conversation data for a specific turn.

        This method is called by pydantic-evals during evaluation to provide turn-specific data.

        Args:
            turn_num: The turn number to get data for

        Returns:
            Dictionary containing turn data for evaluation

        Raises:
            ValueError: If turn not found or missing required data
        """
        if turn_num not in self.conversation_simulator.conversation_history:
            raise ValueError(f"Turn {turn_num} not found in conversation history")

        turn_data = self.conversation_simulator.conversation_history[turn_num]
        user_msg = turn_data.get("user")
        bot_msg = turn_data.get("bot")

        # Validate required data exists
        if not user_msg:
            raise ValueError(f"Turn {turn_num} missing user message")
        if not bot_msg:
            raise ValueError(f"Turn {turn_num} missing bot message")
        if not bot_msg.reasoning:
            raise ValueError(f"Turn {turn_num} bot message missing reasoning")
        if not bot_msg.personality:
            raise ValueError(f"Turn {turn_num} bot message missing personality")

        # Get conversation history up to this turn for context
        conversation_history = []
        for msg in self.conversation_simulator.chronological_messages:
            conversation_history.append(msg)
            # Stop after including the bot message for this turn
            if bot_msg and msg.message_id == bot_msg.message_id:
                break

        return {
            "turn_number": turn_num,
            "user_message": user_msg.text,
            "bot_message": bot_msg.text,
            "bot_reasoning": bot_msg.reasoning,
            "personality": bot_msg.personality,  # Use personality from this specific message
            "timestamp": bot_msg.timestamp,
            "conversation_history": conversation_history,
            "total_turns": len(self.conversation_simulator.conversation_history),
        }

    async def evaluate_conversation(self, name: str | None = None, max_concurrency: int = 1) -> None:
        """
        Evaluate all turns in the conversation.

        Args:
            name: Name for the evaluation run (defaults to session_id)
            max_concurrency: Maximum concurrent evaluations to run
        """
        if not self.conversation_simulator.conversation_history:
            raise ValueError("No conversation history to evaluate")

        # Create evaluation cases for each completed turn
        cases = []
        for turn_num in sorted(self.conversation_simulator.conversation_history.keys()):
            turn_data = self.conversation_simulator.conversation_history[turn_num]

            # Only evaluate turns with both user and bot messages
            if "user" not in turn_data or "bot" not in turn_data:
                continue

            case_evaluators = []

            # Add reasoning evaluator if bot message has reasoning
            if turn_data["bot"].reasoning:
                case_evaluators.append(ConversationReasoningAlignmentEvaluator())

            # Always add personality evaluator
            case_evaluators.append(ConversationPersonalityAlignmentEvaluator())

            cases.append(
                pydantic_evals.Case(
                    name=f"turn_{turn_num}",
                    inputs=turn_num,  # Turn number as input
                    metadata={
                        "personality": turn_data["bot"].personality,  # Use bot message's personality
                        "total_turns": len(self.conversation_simulator.conversation_history),
                        "session_id": self.conversation_simulator.session_id,
                    },
                    evaluators=case_evaluators,
                )
            )

        if not cases:
            raise ValueError("No complete turns found to evaluate")

        # Create dataset with per-case and global evaluators
        dataset = pydantic_evals.Dataset(
            cases=cases,
            evaluators=[ConversationSycophancyEvaluator()],  # Global evaluator for all turns
        )

        # Run evaluation
        evaluation_name = name or f"conversation_{self.conversation_simulator.session_id}"
        return await dataset.evaluate(
            self.get_turn_data,
            name=evaluation_name,
            max_concurrency=max_concurrency,
        )
