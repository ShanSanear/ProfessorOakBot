# Basic Discord bot with SQLite integration
import os
import logging
from discord.ext import commands
from discord import Intents
from sqlalchemy import create_engine, Column, Integer, String, Sequence
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

token = os.getenv('DISCORD_TOKEN')
guild_ids = os.getenv('DISCORD_GUILD_IDS')

if not token or not guild_ids:
    raise ValueError("DISCORD_TOKEN and DISCORD_GUILD_IDS must be set as environment variables.")

guild_ids = [int(gid.strip()) for gid in guild_ids.split(',') if gid.strip().isdigit()]

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('discord')

logger.info(f'Allowed guild IDs: {guild_ids}')

# Set up database (SQLite)
Base = declarative_base()

class ExampleModel(Base):
    __tablename__ = 'example'
    id = Column(Integer, Sequence('user_id_seq'), primary_key=True)
    name = Column(String(50))

engine = create_engine('sqlite:///botdata.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()

# Set up Discord bot
intents = Intents.default()
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user} (ID: {bot.user.id})')
    logger.info(f'Connected to guilds: {guild_ids}')

# Example command
def is_allowed_guild():
    async def predicate(ctx):
        logger.debug(f"Checking guild: ctx.guild={ctx.guild}, ctx.guild.id={getattr(ctx.guild, 'id', None)}")
        # Allow in DMs or in allowed guilds
        return ctx.guild is None or (ctx.guild and ctx.guild.id in guild_ids)
    return commands.check(predicate)

@bot.command()
@is_allowed_guild()
async def ping(ctx):
    await ctx.send('Pong!')

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        if ctx.guild is None:
            await ctx.send("You are not allowed to use this command in this DM.")
        else:
            await ctx.send("You are not allowed to use this command in this server.")
    else:
        raise error

if __name__ == '__main__':
    bot.run(token)
