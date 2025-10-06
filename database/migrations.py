"""
Database migration helper using Alembic.
"""
import logging
from pathlib import Path
from alembic.config import Config
from alembic import command

logger = logging.getLogger("discord")


def run_migrations():
    """
    Run all pending database migrations automatically.
    This should be called on bot startup.
    """
    try:
        # Get the alembic.ini path
        alembic_ini_path = Path(__file__).parent.parent / "alembic.ini"
        
        if not alembic_ini_path.exists():
            logger.error(f"Alembic configuration not found at {alembic_ini_path}")
            return False
        
        # Create Alembic config
        alembic_cfg = Config(str(alembic_ini_path))
        
        # Run migrations to latest version
        logger.info("Running database migrations...")
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error running database migrations: {e}", exc_info=True)
        return False

