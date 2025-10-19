#!/usr/bin/env python3
"""
Database migration helper script using Alembic

This script provides a simple interface for running database migrations.
It ensures proper environment configuration and provides helpful feedback.

Usage:
    python scripts/migrate.py           # Run all pending migrations (upgrade to head)
    python scripts/migrate.py up        # Same as above (upgrade to head)
    python scripts/migrate.py down      # Downgrade one revision
    python scripts/migrate.py history   # Show migration history
    python scripts/migrate.py current   # Show current revision
    python scripts/migrate.py reset     # WARNING: Reset database (downgrade to base)
"""

import os
import sys
import subprocess
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()


def run_alembic_command(args: list[str]) -> int:
    """Run an alembic command with proper error handling"""
    cmd = ["alembic"] + args
    print(f"Running: {' '.join(cmd)}")
    print("-" * 60)

    try:
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=False
        )
        return result.returncode
    except Exception as e:
        print(f"Error running migration: {e}")
        return 1


def get_database_url() -> str:
    """Get database URL for display purposes"""
    db_url = os.getenv('DATABASE_URL')
    if db_url:
        # Mask password for security
        if '@' in db_url:
            parts = db_url.split('@')
            if '://' in parts[0]:
                protocol, credentials = parts[0].split('://')
                if ':' in credentials:
                    user, _ = credentials.split(':', 1)
                    return f"{protocol}://{user}:****@{parts[1]}"
        return db_url

    db_user = os.getenv('DB_USER', 'postgres')
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = os.getenv('DB_PORT', '5432')
    db_name = os.getenv('DB_NAME', 'politics_news_dev')

    return f"postgresql://{db_user}:****@{db_host}:{db_port}/{db_name}"


def main():
    """Main entry point"""
    # Check environment
    db_url_display = get_database_url()
    print(f"Database: {db_url_display}")
    print(f"Environment: {os.getenv('ENVIRONMENT', 'development')}")
    print()

    # Parse command
    command = sys.argv[1] if len(sys.argv) > 1 else "up"

    if command in ["up", "upgrade"]:
        print("Upgrading database to latest version...")
        return run_alembic_command(["upgrade", "head"])

    elif command in ["down", "downgrade"]:
        print("Downgrading database by one revision...")
        return run_alembic_command(["downgrade", "-1"])

    elif command == "history":
        print("Migration history:")
        return run_alembic_command(["history", "--verbose"])

    elif command == "current":
        print("Current database revision:")
        return run_alembic_command(["current", "--verbose"])

    elif command == "reset":
        response = input(
            "⚠️  WARNING: This will DROP ALL TABLES in the database!\n"
            "This action cannot be undone.\n"
            f"Database: {db_url_display}\n"
            "Type 'YES' to confirm: "
        )
        if response == "YES":
            print("Resetting database to base (no tables)...")
            return run_alembic_command(["downgrade", "base"])
        else:
            print("Reset cancelled.")
            return 0

    elif command in ["help", "-h", "--help"]:
        print(__doc__)
        return 0

    else:
        print(f"Unknown command: {command}")
        print("Run 'python scripts/migrate.py help' for usage information.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
