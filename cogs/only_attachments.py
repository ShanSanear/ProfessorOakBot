from discord.ext import commands
from discord import Message
import discord
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

    @commands.group(name='onlyattachments', invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def onlyattachments(self, ctx):
        """Manage 'only attachments' channels."""
        await ctx.send("Use subcommands: add, remove, list.")

    @onlyattachments.command(name='add')
    @commands.has_permissions(administrator=True)
    async def add_channel(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        existing = self.session.query(OnlyAttachmentsChannel).filter_by(channel_id=channel.id).first()
        if existing:
            existing.enabled = True
        else:
            self.session.add(OnlyAttachmentsChannel(channel_id=channel.id, enabled=True))
        self.session.commit()
        await ctx.send(f"Channel <#{channel.id}> set to 'only attachments' mode.")

    @onlyattachments.command(name='remove')
    @commands.has_permissions(administrator=True)
    async def remove_channel(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        config = self.session.query(OnlyAttachmentsChannel).filter_by(channel_id=channel.id).first()
        if config:
            config.enabled = False
            self.session.commit()
            await ctx.send(f"Channel <#{channel.id}> removed from 'only attachments' mode.")
        else:
            await ctx.send("Channel not found in configuration.")

    @onlyattachments.command(name='list')
    @commands.has_permissions(administrator=True)
    async def list_channels(self, ctx):
        channels = self.session.query(OnlyAttachmentsChannel).filter_by(enabled=True).all()
        if not channels:
            await ctx.send("No channels are set to 'only attachments' mode.")
        else:
            msg = "Channels in 'only attachments' mode:\n" + '\n'.join(f"<#{c.channel_id}>" for c in channels)
            await ctx.send(msg)

def setup(bot):
    # The session and engine must be passed from main bot file
    pass
