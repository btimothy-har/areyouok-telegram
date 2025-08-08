import telegram
from telegram.ext import Application
from telegram.ext import ContextTypes


async def setup_bot_commands_research(ctx: Application | ContextTypes.DEFAULT_TYPE):
    """Set the bot commands for the research environment."""
    await ctx.bot.set_my_commands(
        commands=[
            telegram.BotCommand(command="start", description="Start a new chat session with RUOK."),
            telegram.BotCommand(
                command="end",
                description="End the current chat session with RUOK.",
            ),
        ],
    )
