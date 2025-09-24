#!/usr/bin/env python3
# ruff: noqa: E402, TRY003

import os

os.environ["SIMULATION_MODE"] = "true"

import argparse
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


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Simulate text-only conversations between a user agent and the chat agent",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "-s",
        "--simulation",
        type=str,
        required=True,
        help="Name of the simulation file (without .md extension) in scripts/sim_personas/",
    )

    parser.add_argument(
        "-p",
        "--personality",
        type=str,
        default="companionship",
        choices=["anchoring", "celebration", "companionship", "exploration", "witnessing"],
        help="Bot personality to use for the simulation",
    )

    parser.add_argument(
        "-t",
        "--turns",
        type=int,
        default=5,
        help="Number of conversation turns to simulate",
    )

    parser.add_argument(
        "--no-switch",
        action="store_true",
        default=False,
        help="Disable the bot from switching personalities during conversation",
    )

    return parser.parse_args()


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

        # Token usage tracking
        self.token_usage: dict[str, dict[str, int]] = {
            "user_agent": {"input": 0, "output": 0, "requests": 0},
            "chat_agent": {"input": 0, "output": 0, "requests": 0},
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
        self.token_usage["user_agent"]["input"] += usage.input_tokens or 0
        self.token_usage["user_agent"]["output"] += usage.output_tokens or 0
        self.token_usage["user_agent"]["requests"] += usage.requests or 0

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
        self.token_usage["chat_agent"]["input"] += usage.input_tokens or 0
        self.token_usage["chat_agent"]["output"] += usage.output_tokens or 0
        self.token_usage["chat_agent"]["requests"] += usage.requests or 0

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
        """Print simple token usage summary."""
        console.print("\n[bold cyan]🎯 Token Usage Summary[/bold cyan]")
        console.print("-" * 40)

        total_tokens = 0
        for agent_name, usage in self.token_usage.items():
            agent_total = usage["input"] + usage["output"]
            total_tokens += agent_total
            console.print(f"[yellow]{agent_name.replace('_', ' ').title()}:[/yellow] "
                         f"Input: {usage['input']:,}, Output: {usage['output']:,}, "
                         f"Total: {agent_total:,} tokens ({usage['requests']} requests)")

        console.print(f"[bold green]Grand Total: {total_tokens:,} tokens[/bold green]")


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


async def main():
    """Main entry point for conversation simulation."""
    args = parse_args()

    console.print("\n[bold magenta]🎭 Conversation Simulation Script[/bold magenta]")
    console.print("=" * 50)
    console.print(f"[yellow]Simulation:[/yellow] {args.simulation}")
    console.print(f"[yellow]Personality:[/yellow] {args.personality}")
    console.print(f"[yellow]Turns:[/yellow] {args.turns}")
    console.print(f"[yellow]Personality Switching:[/yellow] {'Disabled' if args.no_switch else 'Enabled'}")

    try:
        # Create simulator with specified parameters
        simulator = ConversationSimulator(
            user_persona_file=args.simulation,
            personality=args.personality,
            no_switch=args.no_switch,
        )

        await simulator.simulate_conversation(num_turns=args.turns)

        console.print(
            f"\n[bold green]✅ Simulation complete! "
            f"Total turns: {len(simulator.conversation_history)}, "
            f"Total messages: {len(simulator.chronological_messages)}[/bold green]"
            "\n"
        )

        # Print token usage summary
        simulator.print_token_summary()

        evaluator = ConversationEvaluator(simulator)
        evaluation = await evaluator.evaluate_conversation(name="test_evaluation")

        evaluation.print()

        console.print("\n[bold green]🎉 Test complete![/bold green]")

    except FileNotFoundError as e:
        console.print(f"\n[bold red]❌ Error:[/bold red] {e}")
        console.print("[yellow]Available simulations in scripts/sim_personas/:[/yellow]")

        # List available persona files
        script_dir = Path(__file__).parent
        persona_dir = script_dir / "sim_personas"
        if persona_dir.exists():
            for persona_file in persona_dir.glob("*.md"):
                console.print(f"  • {persona_file.stem}")
        else:
            console.print("  [red]No sim_personas directory found[/red]")

    except Exception as e:
        console.print(f"\n[bold red]❌ Unexpected error:[/bold red] {e}")


if __name__ == "__main__":
    asyncio.run(main())
