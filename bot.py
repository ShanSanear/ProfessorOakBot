# Basic Discord bot with SQLite integration
import os
import logging
from discord.ext import commands
from discord import Intents
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from cogs.only_attachments import OnlyAttachmentsCog
from cogs.cleanup import CleanupCog
from cogs.graphics_monitor import GraphicsMonitorCog

# Import shared models and cogs
from database.models import Base

# Load environment variables from .env if present
load_dotenv(".env")
load_dotenv("stack.env")

token = os.getenv("DISCORD_TOKEN")
guild_ids = os.getenv("DISCORD_GUILD_IDS")
moderator_id = os.getenv("MODERATOR_ID")

# Graphics Monitor Reminder Configuration (with defaults)
reminder_timezone = os.getenv("REMINDER_TIMEZONE", "Europe/Warsaw")
reminder_time_hour = int(os.getenv("REMINDER_TIME_HOUR", "9"))
reminder_time_minute = int(os.getenv("REMINDER_TIME_MINUTE", "0"))
reminder_text = os.getenv("REMINDER_TEXT", "przypominajka")
disable_reminders = os.getenv("DISABLE_REMINDERS", "false").lower() == "true"

if not token or not guild_ids:
    raise ValueError(
        "DISCORD_TOKEN and DISCORD_GUILD_IDS must be set as environment variables."
    )

if not moderator_id:
    raise ValueError(
        "MODERATOR_ID must be set as environment variable for graphics monitoring."
    )

moderator_id = int(moderator_id)

guild_ids = [int(gid.strip()) for gid in guild_ids.split(",") if gid.strip().isdigit()]

logger = logging.getLogger("discord")
if not logger.hasHandlers():
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.DEBUG)
    for handler in logger.handlers:
        handler.setLevel(logging.DEBUG)

# logger.info(f'Allowed guild IDs: {guild_ids}')

DATABASE_PATH = os.getenv("DATABASE_PATH", "database/botdata.db")
Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(f"sqlite://{DATABASE_PATH}")

# Run database migrations automatically on startup
from database.migrations import run_migrations
if not run_migrations():
    logger.error("Failed to run database migrations. Bot may not function correctly.")

Session = sessionmaker(bind=engine)
session = Session()

# Set up Discord bot
intents = Intents(
    reactions=True,
    moderation=True,
    guilds=True,
    messages=True,
    members=True,
    guild_messages=True,
    message_content=True,
)
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# Load OnlyAttachmentsCog
@bot.event
async def setup_hook():
    await bot.add_cog(OnlyAttachmentsCog(bot, session))
    await bot.add_cog(CleanupCog(bot))
    await bot.add_cog(
        GraphicsMonitorCog(
            bot,
            session,
            moderator_id,
            reminder_timezone=reminder_timezone,
            reminder_time_hour=reminder_time_hour,
            reminder_time_minute=reminder_time_minute,
            reminder_text=reminder_text,
            disable_reminders=disable_reminders,
        )
    )
    try:
        await bot.tree.sync()
        logger.info("Slash commands synced globally")
    except Exception as e:
        logger.error(f"Failed to sync commands globally: {e}")


@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    logger.info(f"Connected to guilds: {guild_ids}")


# Example command
def is_allowed_guild():
    async def predicate(ctx):
        logger.debug(
            f"Checking guild: ctx.guild={ctx.guild}, ctx.guild.id={getattr(ctx.guild, 'id', None)}"
        )
        # Allow in DMs or in allowed guilds
        return ctx.guild is None or (ctx.guild and ctx.guild.id in guild_ids)

    return commands.check(predicate)


@bot.command()
@is_allowed_guild()
async def ping(ctx):
    await ctx.send("Pong!")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        if ctx.guild is None:
            await ctx.send("You are not allowed to use this command in this DM.")
        else:
            await ctx.send("You are not allowed to use this command in this server.")
    else:
        raise error


if __name__ == "__main__":
    bot.run(token)
