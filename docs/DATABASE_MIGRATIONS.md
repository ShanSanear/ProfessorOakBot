# Database Migration System

This project uses [Alembic](https://alembic.sqlalchemy.org/) for database schema migrations with SQLite.

## Overview

- **Database**: `database/botdata.db` (SQLite)
- **Models**: All models are defined in `database/models.py` with a shared `Base`
- **Migrations**: Stored in `alembic/versions/`
- **Auto-run**: Migrations run automatically on bot startup

## How It Works

1. **On Bot Startup**: The bot automatically runs all pending migrations before starting
2. **Model Changes**: When you modify models in `database/models.py`, you need to create a new migration
3. **Migration Files**: Generated migration files are committed to git for version control

## Common Tasks

### Creating a New Migration

When you add/modify/remove fields in your database models:

```bash
# Activate virtual environment
.venv\Scripts\Activate.ps1

# Auto-generate migration from model changes
alembic revision --autogenerate -m "Description of changes"
```

This will:
- Compare current models with database schema
- Generate a migration file in `alembic/versions/`
- Show detected changes

### Manually Applying Migrations

Migrations run automatically on bot startup, but you can also run them manually:

```bash
# Activate virtual environment
.venv\Scripts\Activate.ps1

# Upgrade to latest version
alembic upgrade head

# Downgrade one version
alembic downgrade -1

# Show current version
alembic current

# Show migration history
alembic history
```

### Checking Migration Status

```bash
# Show which migrations have been applied
alembic current

# Show all available migrations
alembic history --verbose
```

## Migration Workflow

1. **Modify Models**: Edit `database/models.py` to add/change database schema
2. **Generate Migration**: Run `alembic revision --autogenerate -m "description"`
3. **Review Migration**: Check the generated file in `alembic/versions/`
4. **Test Locally**: Start the bot - migration will run automatically
5. **Commit to Git**: Commit both the model changes and migration file

## Important Notes

- ✅ **DO** commit migration files to git
- ✅ **DO** review auto-generated migrations before committing
- ✅ **DO** test migrations locally before deploying
- ❌ **DON'T** edit applied migrations (create new ones instead)
- ❌ **DON'T** delete migration files that have been applied
- ❌ **DON'T** modify `database/botdata.db` manually

## File Structure

```
ProfessorOakBot/
├── alembic/                    # Alembic configuration
│   ├── versions/              # Migration files (commit to git)
│   │   └── xxxxx_description.py
│   ├── env.py                 # Alembic environment config
│   └── script.py.mako        # Migration template
├── alembic.ini                # Alembic settings
├── database/
│   ├── models.py             # All database models (shared Base)
│   ├── migrations.py         # Auto-migration runner
│   └── botdata.db           # SQLite database (NOT in git)
└── bot.py                    # Runs migrations on startup
```

## Troubleshooting

### Migration fails with "table already exists"

The migration detected a table that already exists. Either:
1. The database is already up to date - skip this migration
2. Manual database changes were made - sync the database state with Alembic

### Migration detects unwanted changes

If Alembic detects changes you didn't make:
1. Check if someone modified the database manually
2. Ensure all models are imported in `database/models.py`
3. Review the auto-generated migration and adjust as needed

### Need to rollback a migration

```bash
# Downgrade to previous version
alembic downgrade -1

# Or downgrade to specific version
alembic downgrade <revision_id>
```

## Advanced: Manual Migrations

If auto-generate doesn't work for complex changes:

```bash
# Create empty migration
alembic revision -m "manual changes"

# Edit the file in alembic/versions/ and add your changes
```

Example manual migration:
```python
def upgrade():
    op.execute("UPDATE table SET column = 'value' WHERE condition")
    
def downgrade():
    op.execute("UPDATE table SET column = 'old_value' WHERE condition")
```

## Database Schema Versioning

Alembic maintains a special table `alembic_version` in your database that tracks which migrations have been applied. This ensures migrations are only run once.

