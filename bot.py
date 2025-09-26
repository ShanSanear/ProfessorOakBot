# Basic Discord bot with SQLite integration
import os
import logging
from discord.ext import commands
from discord import Intents

from sqlalchemy import create_engine, Column, Integer, String, Sequence
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
from cogs.only_attachments import (
    OnlyAttachmentsCog,
    OnlyAttachmentsChannel,
    Base as OA_Base,
)
from cogs.cleanup import CleanupCog
from pathlib import Path

# Load environment variables from .env if present
load_dotenv(".env")
load_dotenv("stack.env")

token = os.getenv("DISCORD_TOKEN")
guild_ids = os.getenv("DISCORD_GUILD_IDS")

if not token or not guild_ids:
    raise ValueError(
        "DISCORD_TOKEN and DISCORD_GUILD_IDS must be set as environment variables."
    )

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

# Set up database (SQLite)
Base = declarative_base()
database_path = "database/botdata.db"
Path(database_path).parent.mkdir(parents=True, exist_ok=True)
# Import and merge OnlyAttachmentsChannel model
engine = create_engine(f"sqlite:///{database_path}")
OA_Base.metadata.create_all(bind=engine)

Base.metadata.create_all(engine)
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
