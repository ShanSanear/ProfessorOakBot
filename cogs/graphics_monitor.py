import asyncio
import datetime
import logging
import re
from typing import Optional, NamedTuple
from zoneinfo import ZoneInfo

import discord
from discord import app_commands, Interaction, TextChannel, Message, User
from discord.ext import commands, tasks

# Import shared models
from database.models import Base, MonitoredGraphicsChannel, MonitoredGraphic

logger = logging.getLogger("discord")

# Constants
SUPPORTED_DATE_FORMATS = """Supported formats:
• `DD.MM-DD.MM` (e.g., 25.12-31.12 or 25.12 - 31.12) - Date range (spaces optional)
• `DD.MM HH:mm-HH:mm` (e.g., 15.03 10:00-18:00 or 04.10 14:00 - 17:00) - Time range (spaces optional)
• `MONTH_NAME` (e.g., January, February, Styczeń, Luty) - Entire month (English or Polish)"""


class DateParseResult(NamedTuple):
    """Result from parsing a date string"""
    original_date_string: Optional[str]
    expiry_datetime: Optional[datetime.datetime]
    in_effect_datetime: Optional[datetime.datetime]  # When the graphic goes "in effect" (start time)


class DateParser:
    """Handles parsing of date formats from message content"""
    
    # Regex patterns for date formats
    DATE_RANGE_PATTERN = r'(\d{1,2})\.(\d{1,2})\s*-\s*(\d{1,2})\.(\d{1,2})'  # DD.MM-DD.MM (spaces around dash optional)
    DATETIME_RANGE_PATTERN = r'(\d{1,2})\.(\d{1,2})\s+(\d{1,2}):(\d{1,2})\s*-\s*(\d{1,2}):(\d{1,2})'  # DD.MM HH:mm-HH:mm (spaces around dash optional)
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
        Returns: DateParseResult with original_date_string, expiry_datetime (includes 1-day grace period),
                 and in_effect_datetime (start time)
        """
        content_lower = content.lower()
        current_date = datetime.datetime.now()
        current_month = current_date.month
        # Try DD.MM-DD.MM format
        match = re.search(cls.DATE_RANGE_PATTERN, content)
        if match:
            day1, month1, day2, month2 = map(int, match.groups())
            current_date = datetime.datetime.now()
            start_year_to_use = current_date.year
            end_year_to_use = current_date.year
            current_month = current_date.month
            # Corner case, where we are in November/December and the range is completely in next year
            if current_month > month1 + 6:
                start_year_to_use += 1
                end_year_to_use += 1
            # Case when it spans both years
            if month2 < month1:
                end_year_to_use += 1
            
            try:
                # Create start and end dates
                start_date = datetime.datetime(start_year_to_use, month1, day1, tzinfo=datetime.timezone.utc)
                end_date = datetime.datetime(end_year_to_use, month2, day2, tzinfo=datetime.timezone.utc)
                
                # Add 1 day grace period and set to end of day
                expiry = end_date.replace(hour=23, minute=59, second=59) + datetime.timedelta(days=1)
                return DateParseResult(match.group(0), expiry, start_date)
            except ValueError:
                pass  # Invalid date, continue to next pattern
        
        # Try DD.MM HH:mm-HH:mm format
        match = re.search(cls.DATETIME_RANGE_PATTERN, content)
        if match:
            day, month, hour1, minute1, hour2, minute2 = map(int, match.groups())
            # Corner case, where we are in November/December and the range is completely in next year
            year_to_use = current_date.year
            if current_month > month + 6:
                year_to_use += 1
            
            try:
                # Create datetime with start and end times
                start_datetime = datetime.datetime(year_to_use, month, day, hour1, minute1, tzinfo=datetime.timezone.utc)
                end_datetime = datetime.datetime(year_to_use, month, day, hour2, minute2, tzinfo=datetime.timezone.utc)
                
                # Add 1 day grace period
                expiry = end_datetime + datetime.timedelta(days=1)
                return DateParseResult(match.group(0), expiry, start_datetime)
            except ValueError:
                pass  # Invalid date, continue to next pattern
        
        # Try MONTH_NAME format
        match = re.search(cls.MONTH_NAME_PATTERN, content_lower)
        if match:
            month_name = match.group(1)
            month_num = cls.MONTHS[month_name]
            year_to_use = current_date.year
            if current_month > month_num + 6:
                year_to_use += 1
            
            # Start date is first day of the month
            start_date = datetime.datetime(year_to_use, month_num, 1, tzinfo=datetime.timezone.utc)
            
            # Get last day of the month
            if month_num == 12:
                # December - last day is 31st
                last_day = 31
                end_date = datetime.datetime(year_to_use, 12, 31, 23, 59, 59, tzinfo=datetime.timezone.utc)
            else:
                # Get first day of next month, then subtract 1 day
                next_month = datetime.datetime(year_to_use, month_num + 1, 1, tzinfo=datetime.timezone.utc)
                end_date = next_month - datetime.timedelta(seconds=1)
            
            # Add 1 day grace period
            expiry = end_date + datetime.timedelta(days=1)
            # Use proper capitalization for display
            display_name = cls.MONTH_DISPLAY_NAMES.get(month_name, month_name.capitalize())
            return DateParseResult(display_name, expiry, start_date)
        
        return DateParseResult(None, None, None)


@app_commands.default_permissions(administrator=True)
class GraphicsMonitorCog(commands.GroupCog, group_name="graphics"):
    """Monitors graphics channels and manages time-based message deletion"""
    
    def __init__(self, bot, session, moderator_id: int, 
                 reminder_timezone: str = "Europe/Warsaw",
                 reminder_time_hour: int = 9,
                 reminder_time_minute: int = 0,
                 reminder_text: str = "przypominajka",
                 disable_reminders: bool = False):
        self.bot = bot
        self.session = session
        self.moderator_id = moderator_id
        self.pending_approvals = {}  # message_id -> MonitoredGraphic
        self.pending_date_requests = {}  # message_id -> Message (for persistence)
        
        # Reminder configuration
        self.reminder_timezone = ZoneInfo(reminder_timezone)
        self.reminder_time_hour = reminder_time_hour
        self.reminder_time_minute = reminder_time_minute
        self.reminder_text = reminder_text
        self.reminder_emoji = "⏰"  # Clock emoji for marking messages with reminders
        self.disable_reminders = disable_reminders
        
        # Start the monitoring tasks
        self.check_expired_graphics.start()
        self.check_and_send_reminders.start()
    
    def cog_unload(self):
        """Stop background tasks when cog is unloaded"""
        self.check_expired_graphics.cancel()
        self.check_and_send_reminders.cancel()
    
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
    
    def _calculate_reminder_time(self, in_effect_datetime: datetime.datetime, message_posted_at: datetime.datetime) -> Optional[datetime.datetime]:
        """
        Calculate when reminder should be posted based on 48h rule.
        Returns None if reminder should not be posted.
        
        Rules:
        - If message posted <48h before in_effect time: no reminder
        - Otherwise: post reminder day before at configured time
        """
        time_until_effect = in_effect_datetime - message_posted_at
        
        # If less than 48 hours until in effect, no reminder
        if time_until_effect < datetime.timedelta(hours=48):
            return None
        
        # Calculate day before in_effect_datetime at configured time
        day_before = in_effect_datetime.date() - datetime.timedelta(days=1)
        
        # Create datetime in the configured timezone
        reminder_time_local = datetime.datetime.combine(
            day_before,
            datetime.time(self.reminder_time_hour, self.reminder_time_minute),
            tzinfo=self.reminder_timezone
        )
        
        # Convert to UTC for storage
        reminder_time_utc = reminder_time_local.astimezone(datetime.timezone.utc)
        
        return reminder_time_utc
    
    @tasks.loop(hours=1)
    async def check_and_send_reminders(self):
        """Hourly task to check for reminders that need to be sent"""
        if self.disable_reminders:
            logger.info("Reminders are disabled; skipping reminder check.")
            return
        logger.info("Running reminder check...")
        
        try:
            now = datetime.datetime.now(datetime.timezone.utc)
            
            # Find all graphics that need reminders sent
            # (scheduled time has passed, reminder not yet sent, and not marked as no date)
            graphics_needing_reminders = self.session.query(MonitoredGraphic).filter(
                MonitoredGraphic.reminder_scheduled_time <= now,
                MonitoredGraphic.reminder_sent == False,
                MonitoredGraphic.marked_no_date == False,
                MonitoredGraphic.reminder_scheduled_time.isnot(None)
            ).all()
            
            for graphic in graphics_needing_reminders:
                await self._send_reminder(graphic)
            
            logger.info(f"Processed {len(graphics_needing_reminders)} reminders")
            
        except Exception as e:
            logger.error(f"Error in check_and_send_reminders task: {e}", exc_info=True)
    
    @check_and_send_reminders.before_loop
    async def before_check_and_send_reminders(self):
        """Wait for bot to be ready before starting the task"""
        await self.bot.wait_until_ready()
    
    async def _send_reminder(self, graphic: MonitoredGraphic):
        """Send a reminder message by replying to the original message"""
        try:
            channel = self.bot.get_channel(graphic.channel_id)
            if not channel:
                logger.warning(f"Channel {graphic.channel_id} not found for graphic {graphic.message_id}")
                # Mark as sent so we don't keep trying
                graphic.reminder_sent = True
                self.session.commit()
                return
            
            try:
                original_message = await channel.fetch_message(graphic.message_id)
            except discord.NotFound:
                # Original message deleted, cancel reminder and clean up
                logger.info(f"Original message {graphic.message_id} deleted, removing from monitoring")
                self.session.delete(graphic)
                self.session.commit()
                return
            
            # Send reminder as a reply to the original message
            try:
                reminder_message = await original_message.reply(self.reminder_text)
                
                # Add clock emoji to original message
                await original_message.add_reaction(self.reminder_emoji)
                
                # Update database
                graphic.reminder_sent = True
                graphic.reminder_message_id = reminder_message.id
                self.session.commit()
                
                logger.info(f"Sent reminder for message {graphic.message_id} (reminder message: {reminder_message.id})")
                
            except discord.Forbidden:
                logger.error(f"Cannot send message or add reaction in channel {graphic.channel_id}")
                graphic.reminder_sent = True  # Mark as sent to avoid retrying
                self.session.commit()
                
        except Exception as e:
            logger.error(f"Error sending reminder for graphic {graphic.message_id}: {e}", exc_info=True)
    
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
            
            # Delete reminder message if it exists
            if graphic.reminder_message_id:
                try:
                    reminder_message = await channel.fetch_message(graphic.reminder_message_id)
                    await reminder_message.delete()
                    logger.info(f"Deleted reminder message {graphic.reminder_message_id}")
                except discord.NotFound:
                    logger.info(f"Reminder message {graphic.reminder_message_id} already deleted")
                except Exception as e:
                    logger.error(f"Error deleting reminder message: {e}", exc_info=True)
            
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
        
        # Check if already being monitored (avoid duplicates)
        existing = self.session.query(MonitoredGraphic).filter_by(
            message_id=message.id
        ).first()
        
        if existing:
            logger.info(f"Message {message.id} is already being monitored, skipping")
            return
        
        # Try to parse date from message content
        parse_result = DateParser.parse_date(message.content)
        
        if parse_result.original_date_string and parse_result.expiry_datetime:
            # Calculate reminder time
            reminder_time = None
            if parse_result.in_effect_datetime:
                reminder_time = self._calculate_reminder_time(
                    parse_result.in_effect_datetime,
                    message.created_at
                )
            
            # Add to monitoring
            graphic = MonitoredGraphic(
                message_id=message.id,
                channel_id=message.channel.id,
                guild_id=message.guild.id,
                author_id=message.author.id,
                date_format=parse_result.original_date_string,
                expiry_date=parse_result.expiry_datetime,
                in_effect_date=parse_result.in_effect_datetime,
                reminder_scheduled_time=reminder_time
            )
            self.session.add(graphic)
            self.session.commit()
            
            reminder_info = f", reminder at: {reminder_time}" if reminder_time else ", no reminder"
            logger.info(f"Automatically added graphic {message.id} to monitoring (expires: {parse_result.expiry_datetime}{reminder_info})")
            
        else:
            # No valid date format found - ask moderator
            await self._request_date_format(message)
    
    @commands.Cog.listener()
    async def on_message_edit(self, before: Message, after: Message):
        """Handle message edits to update reminder information"""
        # Ignore bot messages
        if after.author.bot:
            return
        
        # Check if message is being monitored
        graphic = self.session.query(MonitoredGraphic).filter_by(message_id=after.id).first()
        if not graphic:
            return
        
        # If reminder already sent, don't update
        if graphic.reminder_sent:
            logger.info(f"Skipping reminder update for {after.id} - reminder already sent")
            return
        
        # Re-parse the date from updated content
        parse_result = DateParser.parse_date(after.content)
        
        if parse_result.original_date_string and parse_result.expiry_datetime:
            # Recalculate reminder time based on original message creation time
            reminder_time = None
            if parse_result.in_effect_datetime:
                reminder_time = self._calculate_reminder_time(
                    parse_result.in_effect_datetime,
                    after.created_at
                )
            
            # Update the graphic record
            graphic.date_format = parse_result.original_date_string
            graphic.expiry_date = parse_result.expiry_datetime
            graphic.in_effect_date = parse_result.in_effect_datetime
            graphic.reminder_scheduled_time = reminder_time
            self.session.commit()
            
            logger.info(f"Updated graphic {after.id} after edit (new expiry: {parse_result.expiry_datetime}, reminder: {reminder_time})")
        else:
            # No valid date format in edited message - remove from monitoring and delete reminder if exists
            logger.info(f"No valid date in edited message {after.id}, removing from monitoring")
            
            # Delete reminder message if it exists
            if graphic.reminder_message_id:
                try:
                    channel = self.bot.get_channel(graphic.channel_id)
                    if channel:
                        reminder_message = await channel.fetch_message(graphic.reminder_message_id)
                        await reminder_message.delete()
                        logger.info(f"Deleted reminder message {graphic.reminder_message_id} after edit")
                except discord.NotFound:
                    pass
                except Exception as e:
                    logger.error(f"Error deleting reminder message: {e}", exc_info=True)
            
            self.session.delete(graphic)
            self.session.commit()
    
    async def _request_date_format(self, message: Message):
        """Ask moderator to provide date format for a message"""
        try:
            # Check if we already sent a request for this message
            if message.id in self.pending_date_requests:
                logger.info(f"Date format request already pending for message {message.id}")
                return
            
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
            
            if message.attachments:
                embed.add_field(name="Attachments", value=f"{len(message.attachments)} attachment(s)", inline=True)
                # Add first image as thumbnail if available
                for att in message.attachments:
                    if att.content_type and att.content_type.startswith('image/'):
                        embed.set_thumbnail(url=att.url)
                        break
            
            embed.add_field(name="Message Link", value=f"[Jump to Message]({message.jump_url})", inline=False)
            embed.add_field(
                name="Supported Date Formats",
                value=SUPPORTED_DATE_FORMATS,
                inline=False
            )
            
            # Create view with buttons
            view = DateRequestView(self, message)
            
            await moderator.send(embed=embed, view=view)
            
            # Track pending request
            self.pending_date_requests[message.id] = message
            
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
            
            # Add reminder info
            reminder_info = ""
            if graphic.reminder_scheduled_time:
                if graphic.reminder_sent:
                    reminder_info = f"\n**Reminder:** Sent ✅"
                else:
                    reminder_info = f"\n**Reminder:** {graphic.reminder_scheduled_time.strftime('%Y-%m-%d %H:%M UTC')}"
            else:
                reminder_info = "\n**Reminder:** None"
            
            field_value = f"**Channel:** {channel_name}\n**Date:** {graphic.date_format}\n**Expires:** {expiry_str}\n**Status:** {status}{reminder_info}"
            
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
        
        # Calculate reminder time based on when command is run
        reminder_time = None
        if parse_result.in_effect_datetime:
            command_time = datetime.datetime.now(datetime.timezone.utc)
            reminder_time = self._calculate_reminder_time(
                parse_result.in_effect_datetime,
                command_time
            )
        
        # Add to monitoring
        graphic = MonitoredGraphic(
            message_id=msg_id,
            channel_id=target_channel.id,
            guild_id=interaction.guild_id,
            author_id=message.author.id,
            date_format=parse_result.original_date_string,
            expiry_date=parse_result.expiry_datetime,
            in_effect_date=parse_result.in_effect_datetime,
            reminder_scheduled_time=reminder_time
        )
        self.session.add(graphic)
        self.session.commit()
        
        reminder_text = f"\n**Reminder:** {reminder_time.strftime('%Y-%m-%d %H:%M UTC')}" if reminder_time else "\n**Reminder:** None (message posted <48h before effect time)"
        
        await interaction.response.send_message(
            f"✅ Added message to monitoring.\n"
            f"**Message:** [Jump to message]({message.jump_url})\n"
            f"**Date range:** {parse_result.original_date_string}\n"
            f"**Expires:** {parse_result.expiry_datetime.strftime('%Y-%m-%d %H:%M UTC')} (includes 1-day grace period)"
            f"{reminder_text}",
            ephemeral=True
        )
        logger.info(f"Manually added graphic {msg_id} to monitoring (expires: {parse_result.expiry_datetime}, reminder: {reminder_time})")
    
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
        
        # Delete reminder message if it exists
        if graphic.reminder_message_id:
            try:
                channel = self.bot.get_channel(graphic.channel_id)
                if channel:
                    reminder_message = await channel.fetch_message(graphic.reminder_message_id)
                    await reminder_message.delete()
                    logger.info(f"Deleted reminder message {graphic.reminder_message_id}")
            except discord.NotFound:
                logger.info(f"Reminder message {graphic.reminder_message_id} already deleted")
            except Exception as e:
                logger.error(f"Error deleting reminder message: {e}", exc_info=True)
        
        self.session.delete(graphic)
        self.session.commit()
        
        if msg_id in self.pending_approvals:
            del self.pending_approvals[msg_id]
        
        await interaction.response.send_message(
            f"✅ Removed message {msg_id} from monitoring.",
            ephemeral=True
        )
        logger.info(f"Removed graphic {msg_id} from monitoring")


class DateInputModal(discord.ui.Modal, title="Add Date Format"):
    """Modal for moderator to input date format"""
    
    date_input = discord.ui.TextInput(
        label="Date Format",
        placeholder="e.g., 25.12-31.12, 15.03 10:00-18:00, January",
        style=discord.TextStyle.short,
        required=True,
        max_length=100
    )
    
    def __init__(self, cog: GraphicsMonitorCog, message: Message):
        super().__init__()
        self.cog = cog
        self.message = message
    
    async def on_submit(self, interaction: Interaction):
        """Handle modal submission with date validation"""
        date_string = self.date_input.value.strip()
        
        # Check if message still exists
        try:
            channel = self.cog.bot.get_channel(self.message.channel.id)
            if not channel:
                await interaction.response.send_message(
                    "❌ Channel no longer exists.",
                    ephemeral=True
                )
                return
            
            # Verify message still exists
            await channel.fetch_message(self.message.id)
        except discord.NotFound:
            await interaction.response.send_message(
                "❌ Message has been deleted and cannot be monitored.",
                ephemeral=True
            )
            # Clean up tracking
            if self.message.id in self.cog.pending_date_requests:
                del self.cog.pending_date_requests[self.message.id]
            return
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I no longer have access to that channel.",
                ephemeral=True
            )
            return
        
        # Check if already being monitored
        existing = self.cog.session.query(MonitoredGraphic).filter_by(
            message_id=self.message.id
        ).first()
        
        if existing:
            await interaction.response.send_message(
                f"ℹ️ This message is already being monitored (expires: {existing.expiry_date.strftime('%Y-%m-%d %H:%M UTC')}).",
                ephemeral=True
            )
            return
        
        # Parse the date using existing DateParser
        parse_result = DateParser.parse_date(date_string)
        
        if not parse_result.original_date_string or not parse_result.expiry_datetime:
            # Invalid date format - send error embed
            error_embed = discord.Embed(
                title="❌ Invalid Date Format",
                description=f"Could not parse: `{date_string}`\n\nPlease try again with a supported format.",
                color=discord.Color.red()
            )
            error_embed.add_field(
                name="Supported Formats",
                value=SUPPORTED_DATE_FORMATS,
                inline=False
            )
            error_embed.add_field(
                name="Message Link",
                value=f"[Jump to Message]({self.message.jump_url})",
                inline=False
            )
            
            # Send error and keep the original view active for retry
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
            logger.info(f"Invalid date format provided for message {self.message.id}: {date_string}")
            return
        
        # Valid date - add to monitoring
        graphic = MonitoredGraphic(
            message_id=self.message.id,
            channel_id=self.message.channel.id,
            guild_id=self.message.guild.id,
            author_id=self.message.author.id,
            date_format=parse_result.original_date_string,
            expiry_date=parse_result.expiry_datetime
        )
        self.cog.session.add(graphic)
        self.cog.session.commit()
        
        # Clean up tracking
        if self.message.id in self.cog.pending_date_requests:
            del self.cog.pending_date_requests[self.message.id]
        
        # Send success message
        success_embed = discord.Embed(
            title="✅ Monitoring Enabled",
            description=f"Successfully added message to graphics monitoring.",
            color=discord.Color.green()
        )
        success_embed.add_field(name="Channel", value=self.message.channel.mention, inline=True)
        success_embed.add_field(name="Date Range", value=parse_result.original_date_string, inline=True)
        success_embed.add_field(
            name="Expires",
            value=parse_result.expiry_datetime.strftime('%Y-%m-%d %H:%M UTC'),
            inline=True
        )
        success_embed.add_field(
            name="Message Link",
            value=f"[Jump to Message]({self.message.jump_url})",
            inline=False
        )
        
        await interaction.response.send_message(embed=success_embed, ephemeral=True)
        logger.info(f"Added graphic {self.message.id} to monitoring via modal (expires: {parse_result.expiry_datetime})")
        
        # Update the original DM to show it's been handled
        try:
            original_embed = interaction.message.embeds[0]
            original_embed.color = discord.Color.green()
            original_embed.title = "✅ Graphics Date Format Added"
            await interaction.message.edit(embed=original_embed, view=None)
        except:
            pass  # If we can't update the original message, that's okay


class DateRequestView(discord.ui.View):
    """View with buttons for handling graphics without recognized date formats"""
    
    def __init__(self, cog: GraphicsMonitorCog, message: Message):
        super().__init__(timeout=None)  # No timeout
        self.cog = cog
        self.message = message
    
    @discord.ui.button(label="Add Date", style=discord.ButtonStyle.primary, emoji="📅", custom_id="add_date")
    async def add_date_button(self, interaction: Interaction, button: discord.ui.Button):
        """Open modal to input date format"""
        modal = DateInputModal(self.cog, self.message)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Skip Monitoring", style=discord.ButtonStyle.secondary, emoji="⏭️", custom_id="skip_monitoring")
    async def skip_button(self, interaction: Interaction, button: discord.ui.Button):
        """Skip monitoring for this message"""
        # Clean up tracking
        if self.message.id in self.cog.pending_date_requests:
            del self.cog.pending_date_requests[self.message.id]
        
        await interaction.response.send_message(
            f"✅ Skipped monitoring for message in {self.message.channel.mention}.",
            ephemeral=True
        )
        logger.info(f"Skipped monitoring for message {self.message.id}")
        
        # Update the original DM to show it's been handled
        try:
            original_embed = interaction.message.embeds[0]
            original_embed.color = discord.Color.greyple()
            original_embed.title = "⏭️ Graphics Monitoring Skipped"
            await interaction.message.edit(embed=original_embed, view=None)
        except:
            pass
    
    @discord.ui.button(label="View Message", style=discord.ButtonStyle.secondary, emoji="🔗", custom_id="view_message")
    async def view_button(self, interaction: Interaction, button: discord.ui.Button):
        """Send message link again for easy access"""
        view_embed = discord.Embed(
            title="Message Reference",
            description=f"[Click here to jump to the message]({self.message.jump_url})",
            color=discord.Color.blue()
        )
        view_embed.add_field(name="Channel", value=self.message.channel.mention, inline=True)
        view_embed.add_field(name="Author", value=self.message.author.mention, inline=True)
        
        if self.message.content:
            preview = self.message.content[:500] + "..." if len(self.message.content) > 500 else self.message.content
            view_embed.add_field(name="Content", value=preview, inline=False)
        
        await interaction.response.send_message(embed=view_embed, ephemeral=True)


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

