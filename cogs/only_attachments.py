from discord.ext import commands
from discord import Message, Interaction
import discord
from discord import app_commands
from sqlalchemy import Column, Integer, Boolean
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class OnlyAttachmentsChannel(Base):
    __tablename__ = 'only_attachments_channels'
    id = Column(Integer, primary_key=True)
    channel_id = Column(Integer, unique=True, nullable=False)
    enabled = Column(Boolean, default=True)

# The cog itself
def setup_database(engine):
    Base.metadata.create_all(engine)

class OnlyAttachmentsCog(commands.Cog):
    def __init__(self, bot, session):
        self.bot = bot
        self.session = session
        self.tree = bot.tree
        self._register_app_commands()

    def _register_app_commands(self):
        @self.tree.command(name="onlyattachments_add", description="Add a channel to 'only attachments' mode.")
        @app_commands.describe(channel="Channel to set as attachements only (defaults to current channel if omitted)")
        async def onlyattachments_add(interaction: Interaction, channel: discord.TextChannel = None):
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("You need administrator permissions to use this command.", ephemeral=True)
                return
            channel = channel or interaction.channel
            existing = self.session.query(OnlyAttachmentsChannel).filter_by(channel_id=channel.id).first()
            if existing:
                existing.enabled = True
            else:
                self.session.add(OnlyAttachmentsChannel(channel_id=channel.id, enabled=True))
            self.session.commit()
            await interaction.response.send_message(f"Channel <#{channel.id}> set to 'only attachments' mode.")

        @self.tree.command(name="onlyattachments_remove", description="Remove a channel from 'only attachments' mode.")
        @app_commands.describe(channel="Channel to remove attachements from (defaults to current channel if omitted)")
        async def onlyattachments_remove(interaction: Interaction, channel: discord.TextChannel = None):
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("You need administrator permissions to use this command.", ephemeral=True)
                return
            channel = channel or interaction.channel
            config = self.session.query(OnlyAttachmentsChannel).filter_by(channel_id=channel.id).first()
            if config:
                config.enabled = False
                self.session.commit()
                await interaction.response.send_message(f"Channel <#{channel.id}> removed from 'only attachments' mode.")
            else:
                await interaction.response.send_message("Channel not found in configuration.")

        @self.tree.command(name="onlyattachments_list", description="List all channels in 'only attachments' mode.")
        async def onlyattachments_list(interaction: Interaction):
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("You need administrator permissions to use this command.", ephemeral=True)
                return
            channels = self.session.query(OnlyAttachmentsChannel).filter_by(enabled=True).all()
            if not channels:
                await interaction.response.send_message("No channels are set to 'only attachments' mode.")
            else:
                msg = "Channels in 'only attachments' mode:\n" + '\n'.join(f"<#{c.channel_id}>" for c in channels)
                await interaction.response.send_message(msg)

    @commands.Cog.listener()
    async def on_message(self, message: Message):
        if message.author.bot:
            return
        channel_id = message.channel.id
        config = self.session.query(OnlyAttachmentsChannel).filter_by(channel_id=channel_id, enabled=True).first()
        if config:
            if not message.attachments:
                try:
                    await message.delete()
                except Exception:
                    pass

def setup(bot):
    # The session and engine must be passed from main bot file
    pass
