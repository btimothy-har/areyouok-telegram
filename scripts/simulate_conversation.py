#!/usr/bin/env python3
"""
Simplified conversation simulation script.
Simulates text-only conversations between a user agent and the chat agent.
"""

# Enable simulation mode to skip database dependencies
import os

os.environ["SIMULATION_MODE"] = "true"

import argparse
import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import Literal

import pydantic
import pydantic_ai
from rich.console import Console

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
        "-p",
        "--persona",
        type=str,
        required=True,
        help="Name of the persona file (without .md extension) in scripts/sim_personas/",
    )

    parser.add_argument(
        "-P",
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

    return parser.parse_args()


class ConversationMessage(pydantic.BaseModel):
    """Simple message model for conversation tracking."""

    message_id: int
    role: Literal["user", "bot"]
    timestamp: datetime
    text: str
    reasoning: str | None = None

    def to_model_message(
        self, current_time: datetime, perspective: Literal["user", "bot"]
    ) -> pydantic_ai.messages.ModelMessage:
        """Convert to pydantic_ai ModelMessage format from given perspective.

        Args:
            current_time: Reference time for calculating relative timestamps
            perspective: Which agent's perspective to use ("user" or "bot")
                - From bot's perspective: user messages are requests, bot messages are responses
                - From user's perspective: user messages are responses, bot messages are requests
        """
        seconds_ago = int((current_time - self.timestamp).total_seconds())

        # Build content dictionary
        content_dict = {
            "timestamp": f"{seconds_ago} seconds ago",
            "event_type": "message",
            "text": self.text,
            "message_id": str(self.message_id),
        }

        # Include reasoning for bot responses when viewed from bot's perspective
        if self.role == "bot" and perspective == "bot" and self.reasoning:
            content_dict["reasoning"] = self.reasoning

        content = json.dumps(content_dict)

        # Determine if this message should be a request or response from the given perspective
        if perspective == "bot":
            # From bot's perspective: user messages are requests, bot messages are responses
            is_request = self.role == "user"
        else:  # perspective == "user"
            # From user's perspective: user messages are responses, bot messages are requests
            is_request = self.role == "bot"

        if is_request:
            return pydantic_ai.messages.ModelRequest(
                parts=[
                    pydantic_ai.messages.UserPromptPart(
                        content=content,
                        timestamp=self.timestamp,
                        part_kind="user-prompt",
                    )
                ],
                kind="request",
            )
        else:
            return pydantic_ai.messages.ModelResponse(
                parts=[pydantic_ai.messages.TextPart(content=content, part_kind="text")],
                timestamp=self.timestamp,
                kind="response",
            )


@dataclass
class UserAgentDependencies:
    """Dependencies for the user agent."""

    persona: str


user_model = Gemini25Flash()

user_agent = pydantic_ai.Agent(
    model=user_model.model,
    deps_type=UserAgentDependencies,
    name="simulation_user_agent",
    retries=3,
)


@user_agent.instructions
async def user_instructions(ctx: pydantic_ai.RunContext[UserAgentDependencies]) -> str:
    return f"""The assistant is a role playing agent tasked with simulating a human user.

The assistant should:
- Be natural and conversational, keeping the conversation going
- Keep messages brief (1-2 sentences typically)
- Vary between different types of messages: questions, statements, reactions, topic changes

The assistant is to always adopt the following persona, making assumptions as needed:

{ctx.deps.persona}
"""


class ConversationSimulator:
    """Orchestrates text-only conversations between user and chat agents."""

    def __init__(self, user_persona_file: str, personality: str = "companionship"):
        self.bot_id = "sim_bot_123"
        self.chat_id = "sim_user_456"
        self.session_id = str(uuid.uuid4())  # UUID session ID
        self.personality = personality

        # Load persona from file
        self.user_persona = self._load_persona(user_persona_file)
        self.conversation_history: list[ConversationMessage] = []
        self.message_counter = 0

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

    async def generate_user_message(self) -> str:
        run_kwargs = {"deps": UserAgentDependencies(persona=self.user_persona)}

        if not self.conversation_history:
            run_kwargs["user_prompt"] = "Start a friendly conversation"
        else:
            timestamp = datetime.now(UTC)
            run_kwargs["message_history"] = [
                msg.to_model_message(timestamp, perspective="user") for msg in self.conversation_history
            ]

        result = await user_agent.run(**run_kwargs)
        return result.output

    async def get_bot_response(self, *, allow_personality: bool = True) -> AgentResponse:
        timestamp = datetime.now(UTC)
        model_messages = [msg.to_model_message(timestamp, perspective="bot") for msg in self.conversation_history]

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

        return result.output

    async def simulate_conversation(self, num_turns: int = 5):
        """Run a simple conversation simulation."""
        console.print(f"\n[bold cyan]🚀 Starting simulation with {self.personality} bot[/bold cyan]")
        console.print("-" * 60)

        for turn in range(num_turns):
            console.print(f"\n[bold yellow]📍 Turn {turn + 1}/{num_turns}[/bold yellow]")

            user_text = await self.generate_user_message()

            # Add user message to history
            user_msg = ConversationMessage(
                message_id=self.get_next_message_id(), role="user", timestamp=datetime.now(UTC), text=user_text
            )
            console.print(f"[blue]👤 User:[/blue] {user_msg.text}")
            self.conversation_history.append(user_msg)

            while True:
                allow_personality = True

                bot_response = await self.get_bot_response(allow_personality=allow_personality)
                if isinstance(bot_response, SwitchPersonalityResponse):
                    self.personality = bot_response.personality
                    allow_personality = False
                    console.print(f"[magenta]🔄 Bot switched personality to: {self.personality}[/magenta]")
                    continue
                break

            # Add bot response to history
            bot_msg = ConversationMessage(
                message_id=self.get_next_message_id(),
                role="bot",
                timestamp=datetime.now(UTC),
                text=bot_response.message_text,
                reasoning=bot_response.reasoning,
            )
            console.print(f"[green]🤖 Bot:[/green] {bot_msg.text}")
            self.conversation_history.append(bot_msg)

            # Small delay between turns
            await asyncio.sleep(1)

        console.print(
            f"\n[bold green]✅ Simulation complete! Total messages: {len(self.conversation_history)}[/bold green]"
        )


async def main():
    """Main entry point for conversation simulation."""
    args = parse_args()

    console.print("\n[bold magenta]🎭 Conversation Simulation Script[/bold magenta]")
    console.print("=" * 50)
    console.print(f"[yellow]Persona:[/yellow] {args.persona}")
    console.print(f"[yellow]Personality:[/yellow] {args.personality}")
    console.print(f"[yellow]Turns:[/yellow] {args.turns}")

    try:
        # Create simulator with specified parameters
        simulator = ConversationSimulator(
            user_persona_file=args.persona,
            personality=args.personality,
        )

        await simulator.simulate_conversation(num_turns=args.turns)

        console.print("\n[bold green]🎉 Test complete![/bold green]")

    except FileNotFoundError as e:
        console.print(f"\n[bold red]❌ Error:[/bold red] {e}")
        console.print("[yellow]Available personas in scripts/sim_personas/:[/yellow]")

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
