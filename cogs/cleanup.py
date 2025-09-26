import asyncio
import datetime
import json
import logging
import os
from pathlib import Path

import discord
from discord import app_commands, Interaction, TextChannel
from discord.ext import commands, tasks

logger = logging.getLogger("discord")

class CleanupTask:
    def __init__(self, cog, interaction: Interaction, channel: TextChannel, before: datetime.datetime, backup: bool):
        self.cog = cog
        self.interaction = interaction
        self.channel = channel
        self.before = before
        self.backup = backup
        self.backup_file = None
        self.state = "running"  # running, paused, cancelled
        self.deleted_count = 0
        self.task = tasks.loop(seconds=2)(self._run) # Run every 2 seconds to avoid rate limits
        self.task.start()

    async def _run(self):
        if self.state == "paused":
            return
        if self.state == "cancelled":
            await self._cleanup_and_notify("Cancelled")
            return

        try:
            # Separate messages into old and new
            messages_to_bulk_delete = []
            messages_to_single_delete = []
            fourteen_days_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=14)

            async for msg in self.channel.history(limit=100, before=self.before, oldest_first=True):
                if msg.created_at < fourteen_days_ago:
                    messages_to_single_delete.append(msg)
                else:
                    messages_to_bulk_delete.append(msg)
            
            messages_to_delete = messages_to_bulk_delete + messages_to_single_delete

            if not messages_to_delete:
                await self._cleanup_and_notify("Completed")
                return

            if self.backup:
                await self._backup_messages(messages_to_delete)

            # Bulk delete is more efficient for recent messages
            if messages_to_bulk_delete:
                await self.channel.delete_messages(messages_to_bulk_delete)
                self.deleted_count += len(messages_to_bulk_delete)
                logger.info(f"Bulk deleted {len(messages_to_bulk_delete)} messages from {self.channel.name}. Total: {self.deleted_count}")

            # Delete older messages one by one
            for msg in messages_to_single_delete:
                if self.state != "running": # Check state before each deletion
                    break
                await msg.delete()
                self.deleted_count += 1
                logger.info(f"Individually deleted message {msg.id} from {self.channel.name}. Total: {self.deleted_count}")
                await asyncio.sleep(1) # Be nice to the API

        except discord.errors.NotFound: # Channel or messages might be gone
            logger.warning(f"Channel or messages not found in {self.channel.name}. Stopping cleanup.")
            await self._cleanup_and_notify("Error: Channel or messages not found")
        except discord.errors.Forbidden:
            logger.error(f"Missing permissions to delete messages in {self.channel.name}. Stopping cleanup.")
            await self._cleanup_and_notify("Error: Missing permissions")
        except Exception as e:
            logger.error(f"An error occurred during cleanup in {self.channel.name}: {e}")
            await self._cleanup_and_notify(f"Error: {e}")

    async def _backup_messages(self, messages):
        if not self.backup_file:
            backup_dir = Path("backups")
            backup_dir.mkdir(exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.backup_file = backup_dir / f"{self.channel.guild.id}_{self.channel.id}_{timestamp}.jsonl"

        with open(self.backup_file, 'a', encoding='utf-8') as f:
            for msg in messages:
                msg_dict = {
                    'id': msg.id,
                    'author_id': msg.author.id,
                    'author_name': msg.author.name,
                    'content': msg.content,
                    'attachments': [att.url for att in msg.attachments],
                    'timestamp': msg.created_at.isoformat()
                }
                f.write(json.dumps(msg_dict, ensure_ascii=False) + '\n')

    async def _cleanup_and_notify(self, status: str):
        self.task.cancel()
        del self.cog.active_cleanups[self.channel.id]
        
        final_message = f"Cleanup for channel <#{self.channel.id}>: **{status}**.\nDeleted a total of {self.deleted_count} messages."
        if self.backup and self.backup_file:
            final_message += f"\nMessages backed up to `{self.backup_file}`."
        
        await self.interaction.followup.send(final_message, ephemeral=True)
        logger.info(f"Cleanup task for channel {self.channel.id} finished with status: {status}")

    def get_status(self):
        return f"**Channel**: <#{self.channel.id}>\n**Status**: {self.state}\n**Deleted so far**: {self.deleted_count}"

@app_commands.default_permissions(administrator=True)
class CleanupCog(commands.GroupCog, group_name="cleanup"):
    def __init__(self, bot):
        self.bot = bot
        self.active_cleanups = {} # Key: channel_id, Value: CleanupTask

    @app_commands.command(name="start", description="Start cleaning up messages in a channel.")
    @app_commands.describe(
        channel="The channel to clean up (defaults to current channel).",
        before_date="Delete messages before this date and time (YYYY-MM-DD or YYYY-MM-DD HH:MM). Defaults to 2 hours ago.",
        backup="Backup messages to a local file (defaults to True)."
    )
    async def start(self, interaction: Interaction, channel: TextChannel = None, before_date: str = None, backup: bool = True):
        channel = channel or interaction.channel
        
        if channel.id in self.active_cleanups:
            await interaction.response.send_message(f"A cleanup task is already running for <#{channel.id}>.", ephemeral=True)
            return

        if before_date:
            try:
                # First, try to parse as a full datetime
                before_dt = datetime.datetime.strptime(before_date, "%Y-%m-%d %H:%M").replace(tzinfo=datetime.timezone.utc)
            except ValueError:
                try:
                    # If that fails, try to parse as just a date
                    before_dt = datetime.datetime.strptime(before_date, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
                except ValueError:
                    await interaction.response.send_message("Invalid date format. Please use YYYY-MM-DD or YYYY-MM-DD HH:MM.", ephemeral=True)
                    return
        else:
            before_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)

        await interaction.response.send_message(f"Starting cleanup for <#{channel.id}>. I'll let you know when it's done.", ephemeral=True)
        
        cleanup_task = CleanupTask(self, interaction, channel, before_dt, backup)
        self.active_cleanups[channel.id] = cleanup_task

    @app_commands.command(name="pause", description="Pause the cleanup task for a channel.")
    @app_commands.describe(channel="The channel where the cleanup is running (defaults to current channel).")
    async def pause(self, interaction: Interaction, channel: TextChannel = None):
        channel = channel or interaction.channel
        if channel.id in self.active_cleanups:
            task = self.active_cleanups[channel.id]
            task.state = "paused"
            logger.info(f"Paused cleanup for channel {channel.id}")
            await interaction.response.send_message(f"Cleanup for <#{channel.id}> has been paused.", ephemeral=True)
        else:
            await interaction.response.send_message("No active cleanup task found for this channel.", ephemeral=True)

    @app_commands.command(name="resume", description="Resume a paused cleanup task for a channel.")
    @app_commands.describe(channel="The channel where the cleanup is paused (defaults to current channel).")
    async def resume(self, interaction: Interaction, channel: TextChannel = None):
        channel = channel or interaction.channel
        if channel.id in self.active_cleanups:
            task = self.active_cleanups[channel.id]
            if task.state == "paused":
                task.state = "running"
                logger.info(f"Resumed cleanup for channel {channel.id}")
                await interaction.response.send_message(f"Cleanup for <#{channel.id}> has been resumed.", ephemeral=True)
            else:
                await interaction.response.send_message(f"Cleanup for <#{channel.id}> is not paused.", ephemeral=True)
        else:
            await interaction.response.send_message("No active cleanup task found for this channel.", ephemeral=True)

    @app_commands.command(name="cancel", description="Cancel the cleanup task for a channel.")
    @app_commands.describe(channel="The channel where the cleanup is running (defaults to current channel).")
    async def cancel(self, interaction: Interaction, channel: TextChannel = None):
        channel = channel or interaction.channel
        if channel.id in self.active_cleanups:
            task = self.active_cleanups[channel.id]
            task.state = "cancelled"
            logger.info(f"Cancelled cleanup for channel {channel.id}")
            # The task will send its own final notification.
            await interaction.response.send_message(f"Cancelling cleanup for <#{channel.id}>...", ephemeral=True)
        else:
            await interaction.response.send_message("No active cleanup task found for this channel.", ephemeral=True)

    @app_commands.command(name="status", description="Check the status of cleanup tasks.")
    async def status(self, interaction: Interaction):
        if not self.active_cleanups:
            await interaction.response.send_message("No cleanup tasks are currently active.", ephemeral=True)
            return
        
        embed = discord.Embed(title="Active Cleanup Tasks", color=discord.Color.blue())
        for task in self.active_cleanups.values():
            embed.add_field(name=f"#{task.channel.name}", value=task.get_status(), inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
