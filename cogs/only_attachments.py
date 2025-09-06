import logging

from discord.ext import commands
from discord import Message, Interaction, DiscordException
import discord
from discord import app_commands
from sqlalchemy import Column, Integer, Boolean
from sqlalchemy.orm import declarative_base
import os

Base = declarative_base()
logger = logging.getLogger("discord")


class OnlyAttachmentsChannel(Base):
    __tablename__ = "only_attachments_channels"
    id = Column(Integer, primary_key=True)
    guild_id = Column(Integer, nullable=False)  # New column
    channel_id = Column(Integer, unique=False, nullable=False)
    enabled = Column(Boolean, default=True)


# The cog itself
def setup_database(engine):
    Base.metadata.create_all(engine)


GUILD_ID = int(os.getenv("DISCORD_GUILD_IDS", "0").split(",")[0].strip())


class OnlyAttachmentsCog(commands.GroupCog, group_name="onlyattachments"):
    def __init__(self, bot, session):
        super().__init__()
        self.bot = bot
        self.session = session

    @app_commands.command(
        name="add", description="Add a channel to 'only attachments' mode."
    )
    @app_commands.describe(
        channel="Channel to set as attachments only (defaults to current channel if omitted)"
    )
    async def add(self, interaction: Interaction, channel: discord.TextChannel = None):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "You need administrator permissions to use this command.",
                ephemeral=True,
            )
            return
        channel = channel or interaction.channel
        guild_id = interaction.guild.id
        existing = (
            self.session.query(OnlyAttachmentsChannel)
            .filter_by(guild_id=guild_id, channel_id=channel.id)
            .first()
        )
        if existing:
            existing.enabled = True
        else:
            self.session.add(
                OnlyAttachmentsChannel(
                    guild_id=guild_id, channel_id=channel.id, enabled=True
                )
            )
        self.session.commit()
        logger.info(f"Set channel <#{channel.id}> to 'only attachments' mode.")
        await interaction.response.send_message(
            f"Channel <#{channel.id}> set to 'only attachments' mode.", ephemeral=True
        )

    @app_commands.command(
        name="remove", description="Remove a channel from 'only attachments' mode."
    )
    @app_commands.describe(
        channel="Channel to remove from attachments only (defaults to current channel if omitted)"
    )
    async def remove(
        self, interaction: Interaction, channel: discord.TextChannel = None
    ):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "You need administrator permissions to use this command.",
                ephemeral=True,
            )
            return
        channel = channel or interaction.channel
        guild_id = interaction.guild.id
        config = (
            self.session.query(OnlyAttachmentsChannel)
            .filter_by(guild_id=guild_id, channel_id=channel.id)
            .first()
        )
        if config:
            config.enabled = False
            self.session.commit()
            logger.info(
                f"Removed channel <#{channel.id}> from 'only attachments' mode in guild {guild_id}."
            )
            await interaction.response.send_message(
                f"Channel <#{channel.id}> removed from 'only attachments' mode.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "Channel not found in configuration.", ephemeral=True
            )

    @app_commands.command(
        name="list", description="List all channels in 'only attachments' mode."
    )
    async def list(self, interaction: Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "You need administrator permissions to use this command.",
                ephemeral=True,
            )
            return
        guild_id = interaction.guild.id
        channels = (
            self.session.query(OnlyAttachmentsChannel)
            .filter_by(guild_id=guild_id, enabled=True)
            .all()
        )
        if not channels:
            logger.info(f"No channels in 'only attachments' mode in guild {guild_id}.")
            await interaction.response.send_message(
                "No channels are set to 'only attachments' mode.", ephemeral=True
            )
        else:
            logger.info(
                f"Found {len(channels)} channels in 'only attachments' mode in guild {guild_id}."
            )
            msg = "Channels in 'only attachments' mode:\n" + "\n".join(
                f"<#{c.channel_id}>" for c in channels
            )
            await interaction.response.send_message(msg, ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: Message):
        logger.info(
            f"on_message called for channel {getattr(message.channel, 'id', None)} in guild {getattr(message.guild, 'id', None)} by {getattr(message.author, 'id', None)}"
        )
        if message.author.bot:
            return
        channel_id = message.channel.id
        guild_id = message.guild.id if message.guild else None
        if not guild_id:
            logger.info("Message is not from a guild; skipping.")
            return
        config = (
            self.session.query(OnlyAttachmentsChannel)
            .filter_by(guild_id=guild_id, channel_id=channel_id, enabled=True)
            .first()
        )
        if config:
            if not message.attachments:
                try:
                    logger.info(
                        f"Attempting to remove message by {message.author} without attachments in 'only attachments' channel {channel_id} (guild {guild_id})."
                    )
                    await message.delete()
                    logger.info(f"Message by {message.author} deleted successfully.")
                except DiscordException as e:
                    logger.error(
                        f"Failed to remove message by {message.author} without attachments in 'only attachments' channel {channel_id} (guild {guild_id}): {e}"
                    )
            else:
                logger.info(
                    f"Message by {message.author} contains attachments; no action taken."
                )


def setup(bot):
    pass
