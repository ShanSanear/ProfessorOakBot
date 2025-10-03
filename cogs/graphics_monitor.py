import asyncio
import datetime
import logging
import re
from typing import Optional, NamedTuple

import discord
from discord import app_commands, Interaction, TextChannel, Message, User
from discord.ext import commands, tasks
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Boolean, create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

logger = logging.getLogger("discord")

# Constants
SUPPORTED_DATE_FORMATS = """Supported formats:
• `DD.MM-DD.MM` (e.g., 25.12-31.12) - Date range
• `DD.MM HH:mm-HH:mm` (e.g., 15.03 10:00-18:00) - Time range on a specific day
• `MONTH_NAME` (e.g., January, February, Styczeń, Luty) - Entire month (English or Polish)"""


class DateParseResult(NamedTuple):
    """Result from parsing a date string"""
    original_date_string: Optional[str]
    expiry_datetime: Optional[datetime.datetime]


# Database models
Base = declarative_base()


class MonitoredGraphicsChannel(Base):
    """Channels where graphics monitoring is enabled"""
    __tablename__ = "monitored_graphics_channels"
    
    id = Column(Integer, primary_key=True)
    channel_id = Column(BigInteger, unique=True, nullable=False)
    guild_id = Column(BigInteger, nullable=False)
    enabled_at = Column(DateTime, default=datetime.datetime.now(datetime.timezone.utc))


class MonitoredGraphic(Base):
    """Individual graphics messages being monitored"""
    __tablename__ = "monitored_graphics"
    
    id = Column(Integer, primary_key=True)
    message_id = Column(BigInteger, unique=True, nullable=False)
    channel_id = Column(BigInteger, nullable=False)
    guild_id = Column(BigInteger, nullable=False)
    author_id = Column(BigInteger, nullable=False)
    
    # Time range information
    date_format = Column(String, nullable=True)  # The original date string found
    expiry_date = Column(DateTime, nullable=True)  # When it should expire (with grace period)
    
    # Status tracking
    pending_approval = Column(Boolean, default=False)
    approval_message_id = Column(BigInteger, nullable=True)  # DM message with buttons
    marked_no_date = Column(Boolean, default=False)  # X reaction added for no date format
    
    added_at = Column(DateTime, default=datetime.datetime.now(datetime.timezone.utc))


class DateParser:
    """Handles parsing of date formats from message content"""
    
    # Regex patterns for date formats
    DATE_RANGE_PATTERN = r'(\d{1,2})\.(\d{1,2})-(\d{1,2})\.(\d{1,2})'  # DD.MM-DD.MM
    DATETIME_RANGE_PATTERN = r'(\d{1,2})\.(\d{1,2})\s+(\d{1,2}):(\d{1,2})-(\d{1,2}):(\d{1,2})'  # DD.MM HH:mm-HH:mm
    MONTH_NAME_PATTERN = r'\b(january|february|march|april|may|june|july|august|september|october|november|december|styczeń|styczen|luty|marzec|kwiecień|kwiecien|maj|czerwiec|lipiec|sierpień|sierpien|wrzesień|wrzesien|październik|pazdziernik|listopad|grudzień|grudzien)\b'
    
    MONTHS = {
        # English month names
        'january': 1, 'february': 2, 'march': 3, 'april': 4,
        'may': 5, 'june': 6, 'july': 7, 'august': 8,
        'september': 9, 'october': 10, 'november': 11, 'december': 12,
        # Polish month names (with and without diacritics)
        'styczeń': 1, 'styczen': 1,
        'luty': 2,
        'marzec': 3,
        'kwiecień': 4, 'kwiecien': 4,
        'maj': 5,
        'czerwiec': 6,
        'lipiec': 7,
        'sierpień': 8, 'sierpien': 8,
        'wrzesień': 9, 'wrzesien': 9,
        'październik': 10, 'pazdziernik': 10,
        'listopad': 11,
        'grudzień': 12, 'grudzien': 12
    }
    
    # Canonical month names for display (lowercase key -> proper capitalization)
    MONTH_DISPLAY_NAMES = {
        # English
        'january': 'January', 'february': 'February', 'march': 'March', 'april': 'April',
        'may': 'May', 'june': 'June', 'july': 'July', 'august': 'August',
        'september': 'September', 'october': 'October', 'november': 'November', 'december': 'December',
        # Polish (with diacritics as canonical)
        'styczeń': 'Styczeń', 'styczen': 'Styczeń',
        'luty': 'Luty',
        'marzec': 'Marzec',
        'kwiecień': 'Kwiecień', 'kwiecien': 'Kwiecień',
        'maj': 'Maj',
        'czerwiec': 'Czerwiec',
        'lipiec': 'Lipiec',
        'sierpień': 'Sierpień', 'sierpien': 'Sierpień',
        'wrzesień': 'Wrzesień', 'wrzesien': 'Wrzesień',
        'październik': 'Październik', 'pazdziernik': 'Październik',
        'listopad': 'Listopad',
        'grudzień': 'Grudzień', 'grudzien': 'Grudzień'
    }
    
    @classmethod
    def parse_date(cls, content: str) -> DateParseResult:
        """
        Parse date from message content.
        Returns: DateParseResult with original_date_string and expiry_datetime (includes 1-day grace period)
        """
        content_lower = content.lower()
        
        # Try DD.MM-DD.MM format
        match = re.search(cls.DATE_RANGE_PATTERN, content)
        if match:
            day1, month1, day2, month2 = map(int, match.groups())
            current_year = datetime.datetime.now().year
            
            try:
                # Create start and end dates
                start_date = datetime.datetime(current_year, month1, day1)
                end_date = datetime.datetime(current_year, month2, day2)
                
                # If end date is before start date, it spans to next year
                if end_date < start_date:
                    end_date = datetime.datetime(current_year + 1, month2, day2)
                
                # Add 1 day grace period and set to end of day
                expiry = end_date.replace(hour=23, minute=59, second=59) + datetime.timedelta(days=1)
                return DateParseResult(match.group(0), expiry)
            except ValueError:
                pass  # Invalid date, continue to next pattern
        
        # Try DD.MM HH:mm-HH:mm format
        match = re.search(cls.DATETIME_RANGE_PATTERN, content)
        if match:
            day, month, hour1, minute1, hour2, minute2 = map(int, match.groups())
            current_year = datetime.datetime.now().year
            
            try:
                # Create datetime with end time
                end_datetime = datetime.datetime(current_year, month, day, hour2, minute2)
                
                # Add 1 day grace period
                expiry = end_datetime + datetime.timedelta(days=1)
                return DateParseResult(match.group(0), expiry)
            except ValueError:
                pass  # Invalid date, continue to next pattern
        
        # Try MONTH_NAME format
        match = re.search(cls.MONTH_NAME_PATTERN, content_lower)
        if match:
            month_name = match.group(1)
            month_num = cls.MONTHS[month_name]
            current_year = datetime.datetime.now().year
            
            # Get last day of the month
            if month_num == 12:
                # December - last day is 31st
                last_day = 31
                end_date = datetime.datetime(current_year, 12, 31, 23, 59, 59)
            else:
                # Get first day of next month, then subtract 1 day
                next_month = datetime.datetime(current_year, month_num + 1, 1)
                end_date = next_month - datetime.timedelta(seconds=1)
            
            # Add 1 day grace period
            expiry = end_date + datetime.timedelta(days=1)
            # Use proper capitalization for display
            display_name = cls.MONTH_DISPLAY_NAMES.get(month_name, month_name.capitalize())
            return DateParseResult(display_name, expiry)
        
        return DateParseResult(None, None)


@app_commands.default_permissions(administrator=True)
class GraphicsMonitorCog(commands.GroupCog, group_name="graphics"):
    """Monitors graphics channels and manages time-based message deletion"""
    
    def __init__(self, bot, session, moderator_id: int):
        self.bot = bot
        self.session = session
        self.moderator_id = moderator_id
        self.pending_approvals = {}  # message_id -> MonitoredGraphic
        
        # Start the monitoring task
        self.check_expired_graphics.start()
    
    def cog_unload(self):
        """Stop background tasks when cog is unloaded"""
        self.check_expired_graphics.cancel()
    
    @tasks.loop(hours=1)
    async def check_expired_graphics(self):
        """Hourly task to check for expired graphics"""
        logger.info("Running hourly graphics expiry check...")
        
        try:
            now = datetime.datetime.now(datetime.timezone.utc)
            
            # Find all expired graphics that haven't been marked for approval yet
            expired_graphics = self.session.query(MonitoredGraphic).filter(
                MonitoredGraphic.expiry_date <= now,
                MonitoredGraphic.pending_approval == False,
                MonitoredGraphic.marked_no_date == False
            ).all()
            
            for graphic in expired_graphics:
                await self._request_deletion_approval(graphic)
            
            logger.info(f"Processed {len(expired_graphics)} expired graphics")
            
        except Exception as e:
            logger.error(f"Error in check_expired_graphics task: {e}", exc_info=True)
    
    @check_expired_graphics.before_loop
    async def before_check_expired_graphics(self):
        """Wait for bot to be ready before starting the task"""
        await self.bot.wait_until_ready()
    
    async def _request_deletion_approval(self, graphic: MonitoredGraphic):
        """Send DM to moderator asking for deletion approval"""
        try:
            moderator = await self.bot.fetch_user(self.moderator_id)
            channel = self.bot.get_channel(graphic.channel_id)
            
            if not channel:
                logger.warning(f"Channel {graphic.channel_id} not found for graphic {graphic.message_id}")
                return
            
            try:
                message = await channel.fetch_message(graphic.message_id)
            except discord.NotFound:
                # Message already deleted
                logger.info(f"Message {graphic.message_id} already deleted, removing from monitoring")
                self.session.delete(graphic)
                self.session.commit()
                return
            
            # Create embed with message preview
            embed = discord.Embed(
                title="Graphics Deletion Approval Needed",
                description=f"A graphic in {channel.mention} has expired.",
                color=discord.Color.orange()
            )
            embed.add_field(name="Channel", value=channel.mention, inline=True)
            embed.add_field(name="Date Range", value=graphic.date_format or "N/A", inline=True)
            embed.add_field(name="Expired", value=graphic.expiry_date.strftime("%Y-%m-%d %H:%M UTC") if graphic.expiry_date else "N/A", inline=True)
            
            if message.content:
                preview = message.content[:200] + "..." if len(message.content) > 200 else message.content
                embed.add_field(name="Message Content", value=preview, inline=False)
            
            if message.attachments:
                embed.add_field(name="Attachments", value=f"{len(message.attachments)} attachment(s)", inline=True)
                # Add first image as thumbnail if available
                for att in message.attachments:
                    if att.content_type and att.content_type.startswith('image/'):
                        embed.set_thumbnail(url=att.url)
                        break
            
            embed.add_field(name="Message Link", value=f"[Jump to Message]({message.jump_url})", inline=False)
            
            # Create view with buttons
            view = ApprovalView(self, graphic)
            
            try:
                dm_message = await moderator.send(embed=embed, view=view)
                
                # Update graphic record
                graphic.pending_approval = True
                graphic.approval_message_id = dm_message.id
                self.session.commit()
                
                self.pending_approvals[graphic.message_id] = graphic
                
                logger.info(f"Sent deletion approval request to moderator for message {graphic.message_id}")
                
            except discord.Forbidden:
                logger.error(f"Cannot send DM to moderator {self.moderator_id}")
                # Add X reaction as fallback
                await self._mark_no_response(graphic, message)
                
        except Exception as e:
            logger.error(f"Error requesting deletion approval for graphic {graphic.message_id}: {e}", exc_info=True)
    
    async def _mark_no_response(self, graphic: MonitoredGraphic, message: Message = None):
        """Add X reaction when moderator doesn't respond or can't be reached"""
        try:
            if not message:
                channel = self.bot.get_channel(graphic.channel_id)
                if channel:
                    try:
                        message = await channel.fetch_message(graphic.message_id)
                    except discord.NotFound:
                        pass
            
            if message:
                await message.add_reaction("❌")
                logger.info(f"Added ❌ reaction to message {graphic.message_id}")
            
            graphic.marked_no_date = True
            self.session.commit()
            
        except Exception as e:
            logger.error(f"Error adding reaction to message {graphic.message_id}: {e}", exc_info=True)
    
    async def handle_deletion_approval(self, graphic: MonitoredGraphic, approved: bool, interaction: Interaction):
        """Handle moderator's response to deletion request"""
        try:
            channel = self.bot.get_channel(graphic.channel_id)
            if not channel:
                await interaction.response.send_message("Channel not found.", ephemeral=True)
                return
            
            try:
                message = await channel.fetch_message(graphic.message_id)
            except discord.NotFound:
                await interaction.response.send_message("Message has already been deleted.", ephemeral=True)
                self.session.delete(graphic)
                self.session.commit()
                if graphic.message_id in self.pending_approvals:
                    del self.pending_approvals[graphic.message_id]
                return
            
            if approved:
                # Delete the message
                await message.delete()
                await interaction.response.send_message(f"✅ Message deleted from {channel.mention}.", ephemeral=True)
                logger.info(f"Deleted message {graphic.message_id} after moderator approval")
            else:
                # Keep the message, remove from monitoring
                await interaction.response.send_message(f"✅ Message kept in {channel.mention} and removed from monitoring.", ephemeral=True)
                logger.info(f"Kept message {graphic.message_id} after moderator denial")
            
            # Remove from database and tracking
            self.session.delete(graphic)
            self.session.commit()
            if graphic.message_id in self.pending_approvals:
                del self.pending_approvals[graphic.message_id]
                
        except Exception as e:
            logger.error(f"Error handling deletion approval: {e}", exc_info=True)
            await interaction.response.send_message(f"Error processing request: {e}", ephemeral=True)
    
    @commands.Cog.listener()
    async def on_message(self, message: Message):
        """Monitor new messages in enabled channels"""
        # Ignore bot messages
        if message.author.bot:
            return
        
        # Check if message is in a monitored channel
        monitored_channel = self.session.query(MonitoredGraphicsChannel).filter_by(
            channel_id=message.channel.id
        ).first()
        
        if not monitored_channel:
            return
        
        # Only process messages from admins/mods (users with manage_messages permission)
        if not message.author.guild_permissions.manage_messages:
            return
        
        # Check if message has attachments
        if not message.attachments:
            return
        
        # Try to parse date from message content
        parse_result = DateParser.parse_date(message.content)
        
        if parse_result.original_date_string and parse_result.expiry_datetime:
            # Add to monitoring
            graphic = MonitoredGraphic(
                message_id=message.id,
                channel_id=message.channel.id,
                guild_id=message.guild.id,
                author_id=message.author.id,
                date_format=parse_result.original_date_string,
                expiry_date=parse_result.expiry_datetime
            )
            self.session.add(graphic)
            self.session.commit()
            
            logger.info(f"Automatically added graphic {message.id} to monitoring (expires: {parse_result.expiry_datetime})")
            
        else:
            # No valid date format found - ask moderator
            await self._request_date_format(message)
    
    async def _request_date_format(self, message: Message):
        """Ask moderator to provide date format for a message"""
        try:
            moderator = await self.bot.fetch_user(self.moderator_id)
            
            embed = discord.Embed(
                title="Graphics Date Format Needed",
                description=f"A graphic was posted in {message.channel.mention} without a recognized date format.",
                color=discord.Color.blue()
            )
            embed.add_field(name="Channel", value=message.channel.mention, inline=True)
            embed.add_field(name="Author", value=message.author.mention, inline=True)
            
            if message.content:
                preview = message.content[:500] + "..." if len(message.content) > 500 else message.content
                embed.add_field(name="Message Content", value=preview, inline=False)
            
            embed.add_field(name="Message Link", value=f"[Jump to Message]({message.jump_url})", inline=False)
            embed.add_field(
                name="Instructions",
                value="Please use `/graphics add-graphics-monitor` to add this message with a proper date range.",
                inline=False
            )
            
            await moderator.send(embed=embed)
            logger.info(f"Sent date format request to moderator for message {message.id}")
            
        except discord.Forbidden:
            logger.error(f"Cannot send DM to moderator {self.moderator_id}")
        except Exception as e:
            logger.error(f"Error requesting date format: {e}", exc_info=True)
    
    @app_commands.command(name="enable-channel", description="Enable graphics monitoring for a channel")
    @app_commands.describe(channel="The channel to monitor (defaults to current channel)")
    async def enable_channel(self, interaction: Interaction, channel: TextChannel = None):
        """Enable graphics monitoring for a channel"""
        channel = channel or interaction.channel
        
        # Check if already enabled
        existing = self.session.query(MonitoredGraphicsChannel).filter_by(
            channel_id=channel.id
        ).first()
        
        if existing:
            await interaction.response.send_message(
                f"Graphics monitoring is already enabled for {channel.mention}.",
                ephemeral=True
            )
            return
        
        # Add to database
        monitored_channel = MonitoredGraphicsChannel(
            channel_id=channel.id,
            guild_id=interaction.guild_id
        )
        self.session.add(monitored_channel)
        self.session.commit()
        
        await interaction.response.send_message(
            f"✅ Graphics monitoring enabled for {channel.mention}.",
            ephemeral=True
        )
        logger.info(f"Enabled graphics monitoring for channel {channel.id}")
    
    @app_commands.command(name="disable-channel", description="Disable graphics monitoring for a channel")
    @app_commands.describe(channel="The channel to stop monitoring (defaults to current channel)")
    async def disable_channel(self, interaction: Interaction, channel: TextChannel = None):
        """Disable graphics monitoring for a channel"""
        channel = channel or interaction.channel
        
        # Check if enabled
        monitored_channel = self.session.query(MonitoredGraphicsChannel).filter_by(
            channel_id=channel.id
        ).first()
        
        if not monitored_channel:
            await interaction.response.send_message(
                f"Graphics monitoring is not enabled for {channel.mention}.",
                ephemeral=True
            )
            return
        
        # Remove from database
        self.session.delete(monitored_channel)
        
        # Also remove any monitored graphics from this channel
        graphics = self.session.query(MonitoredGraphic).filter_by(
            channel_id=channel.id
        ).all()
        for graphic in graphics:
            self.session.delete(graphic)
        
        self.session.commit()
        
        await interaction.response.send_message(
            f"✅ Graphics monitoring disabled for {channel.mention}. Removed {len(graphics)} monitored graphic(s).",
            ephemeral=True
        )
        logger.info(f"Disabled graphics monitoring for channel {channel.id}")
    
    @app_commands.command(name="list-monitored-graphics", description="List all graphics being monitored")
    async def list_monitored_graphics(self, interaction: Interaction):
        """List all monitored graphics and their expiry times"""
        graphics = self.session.query(MonitoredGraphic).order_by(MonitoredGraphic.expiry_date).all()
        
        if not graphics:
            await interaction.response.send_message(
                "No graphics are currently being monitored.",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="Monitored Graphics",
            description=f"Total: {len(graphics)} graphic(s)",
            color=discord.Color.green()
        )
        
        for i, graphic in enumerate(graphics[:25], 1):  # Discord limit: 25 fields
            channel = self.bot.get_channel(graphic.channel_id)
            channel_name = channel.mention if channel else f"<#{graphic.channel_id}>"
            
            status = "⏳ Pending approval" if graphic.pending_approval else "✅ Active"
            if graphic.marked_no_date:
                status = "❌ No response"
            
            expiry_str = graphic.expiry_date.strftime("%Y-%m-%d %H:%M UTC") if graphic.expiry_date else "No date"
            
            field_value = f"**Channel:** {channel_name}\n**Date:** {graphic.date_format}\n**Expires:** {expiry_str}\n**Status:** {status}"
            
            embed.add_field(
                name=f"{i}. Message {graphic.message_id}",
                value=field_value,
                inline=False
            )
        
        if len(graphics) > 25:
            embed.set_footer(text=f"Showing first 25 of {len(graphics)} graphics")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="add-graphics-monitor", description="Add a message to graphics monitoring")
    @app_commands.describe(
        message_reference="Message ID or link (right-click message → Copy ID/Copy Message Link)",
        date_range="Date range (e.g., '25.12-31.12', '15.03 10:00-18:00', 'January')",
        channel="The channel containing the message (defaults to current channel, ignored if using message link)"
    )
    async def add_graphics_monitor(self, interaction: Interaction, message_reference: str, date_range: str, channel: TextChannel = None):
        """
        Manually add a message to graphics monitoring.
        
        To get a message ID/link in Discord:
        1. Enable Developer Mode: User Settings → Advanced → Developer Mode
        2. Right-click the message → Copy ID or Copy Message Link
        """
        # Try to parse message link format: https://discord.com/channels/guild_id/channel_id/message_id
        msg_id = None
        target_channel = channel or interaction.channel
        
        # Check if it's a message link
        link_match = re.match(r'https://(?:discord\.com|ptb\.discord\.com|canary\.discord\.com)/channels/\d+/(\d+)/(\d+)', message_reference)
        if link_match:
            channel_id, msg_id = map(int, link_match.groups())
            # Get the channel from the link
            target_channel = self.bot.get_channel(channel_id)
            if not target_channel:
                await interaction.response.send_message(
                    f"Could not find channel with ID {channel_id}.",
                    ephemeral=True
                )
                return
        else:
            # Try to parse as plain message ID
            try:
                msg_id = int(message_reference)
            except ValueError:
                await interaction.response.send_message(
                    "Invalid message reference. Please provide either:\n"
                    "• A message ID (right-click message → Copy ID)\n"
                    "• A message link (right-click message → Copy Message Link)\n\n"
                    "**Note:** You need to enable Developer Mode in Discord settings to access these options.",
                    ephemeral=True
                )
                return
        
        # Check if already monitored
        existing = self.session.query(MonitoredGraphic).filter_by(message_id=msg_id).first()
        if existing:
            await interaction.response.send_message(
                f"Message {msg_id} is already being monitored.",
                ephemeral=True
            )
            return
        
        # Try to fetch the message
        try:
            message = await target_channel.fetch_message(msg_id)
        except discord.NotFound:
            await interaction.response.send_message(
                f"Message {msg_id} not found in {target_channel.mention}.",
                ephemeral=True
            )
            return
        except discord.Forbidden:
            await interaction.response.send_message(
                f"I don't have permission to access messages in {target_channel.mention}.",
                ephemeral=True
            )
            return
        
        # Parse the date range
        parse_result = DateParser.parse_date(date_range)
        
        if not parse_result.original_date_string or not parse_result.expiry_datetime:
            await interaction.response.send_message(
                f"Could not parse date range: `{date_range}`\n\n{SUPPORTED_DATE_FORMATS}",
                ephemeral=True
            )
            return
        
        # Add to monitoring
        graphic = MonitoredGraphic(
            message_id=msg_id,
            channel_id=target_channel.id,
            guild_id=interaction.guild_id,
            author_id=message.author.id,
            date_format=parse_result.original_date_string,
            expiry_date=parse_result.expiry_datetime
        )
        self.session.add(graphic)
        self.session.commit()
        
        await interaction.response.send_message(
            f"✅ Added message to monitoring.\n"
            f"**Message:** [Jump to message]({message.jump_url})\n"
            f"**Date range:** {parse_result.original_date_string}\n"
            f"**Expires:** {parse_result.expiry_datetime.strftime('%Y-%m-%d %H:%M UTC')} (includes 1-day grace period)",
            ephemeral=True
        )
        logger.info(f"Manually added graphic {msg_id} to monitoring (expires: {parse_result.expiry_datetime})")
    
    @app_commands.command(name="remove-graphics-monitor", description="Remove a message from graphics monitoring")
    @app_commands.describe(message_id="The ID of the message to stop monitoring")
    async def remove_graphics_monitor(self, interaction: Interaction, message_id: str):
        """Remove a message from graphics monitoring without deleting it"""
        try:
            msg_id = int(message_id)
        except ValueError:
            await interaction.response.send_message("Invalid message ID.", ephemeral=True)
            return
        
        graphic = self.session.query(MonitoredGraphic).filter_by(message_id=msg_id).first()
        
        if not graphic:
            await interaction.response.send_message(
                f"Message {msg_id} is not being monitored.",
                ephemeral=True
            )
            return
        
        self.session.delete(graphic)
        self.session.commit()
        
        if msg_id in self.pending_approvals:
            del self.pending_approvals[msg_id]
        
        await interaction.response.send_message(
            f"✅ Removed message {msg_id} from monitoring.",
            ephemeral=True
        )
        logger.info(f"Removed graphic {msg_id} from monitoring")


class ApprovalView(discord.ui.View):
    """View with buttons for moderator approval"""
    
    def __init__(self, cog: GraphicsMonitorCog, graphic: MonitoredGraphic):
        super().__init__(timeout=None)  # No timeout since it can wait hours
        self.cog = cog
        self.graphic = graphic
    
    @discord.ui.button(label="Delete Message", style=discord.ButtonStyle.danger, custom_id="delete_yes")
    async def delete_button(self, interaction: Interaction, button: discord.ui.Button):
        """Delete the message"""
        await self.cog.handle_deletion_approval(self.graphic, True, interaction)
        # Disable buttons after response
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
    
    @discord.ui.button(label="Keep Message", style=discord.ButtonStyle.success, custom_id="delete_no")
    async def keep_button(self, interaction: Interaction, button: discord.ui.Button):
        """Keep the message"""
        await self.cog.handle_deletion_approval(self.graphic, False, interaction)
        # Disable buttons after response
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

