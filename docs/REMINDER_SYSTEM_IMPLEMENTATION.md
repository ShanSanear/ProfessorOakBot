# Graphics Monitor Reminder System Implementation

## Overview

The graphics_monitor cog now includes an automatic reminder system that posts reminders for graphics messages before they go "in effect".

## Key Features

### 1. Reminder Rules

- **48-Hour Rule**: Reminders are only sent if the message was posted more than 48 hours before its "in effect" time
- **Timing**: Reminders are posted the day before at the configured time (default: 09:00 Poland timezone)
- **Format**: Reminders use Discord's reply feature to quote the original message
- **Visual Indicator**: Original messages get a ⏰ (clock) emoji reaction when a reminder is sent

### 2. "In Effect" Time Definition

- **Date ranges** (e.g., `25.12-31.12`): Start date at 00:00
- **Time ranges** (e.g., `04.10 14:00-17:00`): Start time (14:00 in this example)
- **Month names** (e.g., `January`): First day of the month at 00:00

### 3. Database Changes

Added three new columns to `MonitoredGraphic` table:

- `in_effect_date`: When the graphic goes "in effect" (start time)
- `reminder_scheduled_time`: When the reminder should be sent
- `reminder_sent`: Boolean flag indicating if reminder was already sent
- `reminder_message_id`: ID of the reminder message (for cleanup)

### 4. Configuration

New environment variables in `stack.env`:

```env
REMINDER_TIMEZONE=Europe/Warsaw        # Timezone for reminder posting
REMINDER_TIME_HOUR=9                   # Hour to post reminders (24h format)
REMINDER_TIME_MINUTE=0                 # Minute to post reminders
REMINDER_TEXT=przypominajka            # Text to post as reminder
```

All have sensible defaults if not specified.

### 5. Automatic Behavior

#### When Messages Are Posted

- System parses the date/time from message content
- Calculates "in effect" time
- Applies 48-hour rule to determine if reminder is needed
- Schedules reminder if applicable

#### When Messages Are Edited

- Re-parses the date/time information
- Recalculates reminder scheduling
- Updates database accordingly
- If edited message no longer has valid date: removes from monitoring and deletes any unsent reminder

#### When Messages Are Deleted

- Cancels any pending reminders
- Removes from monitoring database

#### When Monitoring Is Removed

- Deletes the reminder message (if it was already sent)
- Removes all tracking data

### 6. Edge Case Handling

#### Bot Restart After Scheduled Time

If the bot is offline when a reminder should be sent and comes back online after the scheduled time but before the "in effect" time, the reminder is sent immediately.

#### Expired Graphics

When graphics expire and moderator approves deletion, both the original message AND the reminder message (if it exists) are deleted.

#### Manual Addition

When using `/graphics add-graphics-monitor`, the 48-hour rule is calculated from the time the command is executed, not the original message creation time.

### 7. Background Tasks

Two hourly tasks run independently:

1. **check_and_send_reminders**: Checks for reminders that need to be sent
2. **check_expired_graphics**: Checks for expired graphics (existing functionality)

Both tasks:

- Run hourly
- Start when bot is ready (handles startup case)
- Log their activity

### 8. User-Visible Changes

#### `/graphics list-monitored-graphics`

Now shows reminder information:

- "Reminder: None" - if no reminder scheduled (<48h rule)
- "Reminder: YYYY-MM-DD HH:MM UTC" - if scheduled but not yet sent
- "Reminder: Sent ✅" - if reminder was already posted

#### `/graphics add-graphics-monitor`

Response now includes reminder scheduling information.

## Testing Checklist

When testing the reminder system, verify:

1. ✅ Messages posted <48h before effect time: no reminder
2. ✅ Messages posted >48h before effect time: reminder scheduled
3. ✅ Reminders posted at configured time
4. ✅ Reminders use reply/quote format
5. ✅ Clock emoji added to original message
6. ✅ Reminder deleted when original message removed
7. ✅ Reminder updated when message edited (if not yet sent)
8. ✅ Late reminders sent on bot restart
9. ✅ Reminder deleted when graphic expires

## Database Migration

⚠️ **Important**: The database schema has changed. When deploying this update:

1. The bot will automatically create the new columns via SQLAlchemy
2. Existing monitored graphics will have `NULL` values for new columns
3. Those existing graphics won't have reminders unless manually re-added or edited

To manually migrate existing data, you could run SQL like:

```sql
ALTER TABLE monitored_graphics ADD COLUMN in_effect_date DATETIME;
ALTER TABLE monitored_graphics ADD COLUMN reminder_scheduled_time DATETIME;
ALTER TABLE monitored_graphics ADD COLUMN reminder_sent BOOLEAN DEFAULT 0;
ALTER TABLE monitored_graphics ADD COLUMN reminder_message_id BIGINT;
```

However, SQLAlchemy should handle this automatically on next startup.

