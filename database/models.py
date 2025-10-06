"""
Shared database models for ProfessorOakBot.
All models use a single declarative base for Alembic migration support.
"""
import datetime
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Boolean
from sqlalchemy.orm import declarative_base

# Single shared Base for all models
Base = declarative_base()


# OnlyAttachments models
class OnlyAttachmentsChannel(Base):
    """Channels where only attachments are allowed"""
    __tablename__ = "only_attachments_channels"
    
    id = Column(Integer, primary_key=True)
    guild_id = Column(Integer, nullable=False)
    channel_id = Column(Integer, unique=False, nullable=False)
    enabled = Column(Boolean, default=True)


# Graphics Monitor models
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
    in_effect_date = Column(DateTime, nullable=True)  # When the graphic goes "in effect" (start time)
    
    # Reminder tracking
    reminder_scheduled_time = Column(DateTime, nullable=True)  # When reminder should be sent
    reminder_sent = Column(Boolean, default=False)  # Whether reminder was already sent
    reminder_message_id = Column(BigInteger, nullable=True)  # ID of the reminder message
    
    # Status tracking
    pending_approval = Column(Boolean, default=False)
    approval_message_id = Column(BigInteger, nullable=True)  # DM message with buttons
    marked_no_date = Column(Boolean, default=False)  # X reaction added for no date format
    
    added_at = Column(DateTime, default=datetime.datetime.now(datetime.timezone.utc))

