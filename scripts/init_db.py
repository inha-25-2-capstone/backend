#!/usr/bin/env python3
"""
Initialize database for the Political News Aggregation system

This script:
1. Runs database migrations using Alembic
2. Seeds initial data (press organizations)
3. Verifies the setup

Usage:
    python scripts/init_db.py [--reset]

Options:
    --reset     WARNING: Drop all tables and recreate from scratch
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

# Import database models
from src.models.database import get_db_connection, PressRepository


def run_migrations() -> bool:
    """Run database migrations"""
    print("=" * 60)
    print("Running database migrations...")
    print("=" * 60)

    result = subprocess.run(
        ["python", "scripts/migrate.py", "up"],
        cwd=PROJECT_ROOT,
        check=False
    )

    if result.returncode != 0:
        print("❌ Migration failed!")
        return False

    print("✅ Migrations completed successfully")
    return True


def seed_press_data() -> bool:
    """Seed initial press organization data"""
    print("\n" + "=" * 60)
    print("Seeding press organization data...")
    print("=" * 60)

    press_data = [
        ("001", "연합뉴스"),
        ("023", "조선일보"),
        ("020", "동아일보"),
        ("052", "YTN"),
        ("028", "한겨레"),
        ("032", "경향신문"),
    ]

    try:
        for press_id, press_name in press_data:
            # get_or_create returns the press_id and handles the logic internally
            PressRepository.get_or_create(press_id, press_name)
            print(f"✅ Ensured: {press_name}")

        print(f"\n📊 Summary: {len(press_data)} press organizations ready")
        return True

    except Exception as e:
        print(f"❌ Error seeding press data: {e}")
        return False


def verify_setup() -> bool:
    """Verify database setup"""
    print("\n" + "=" * 60)
    print("Verifying database setup...")
    print("=" * 60)

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Check pgvector extension
            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_extension WHERE extname = 'vector'
                )
            """)
            has_pgvector = cursor.fetchone()[0]

            if has_pgvector:
                print("✅ pgvector extension installed")
            else:
                print("⚠️  pgvector extension not found")

            # Check tables
            cursor.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """)
            tables = [row[0] for row in cursor.fetchall()]

            expected_tables = [
                'alembic_version',
                'article',
                'press',
                'recommended_article',
                'stance_analysis',
                'topic',
                'topic_article_mapping'
            ]

            print(f"\n📋 Found {len(tables)} tables:")
            for table in tables:
                status = "✅" if table in expected_tables else "❓"
                print(f"  {status} {table}")

            missing = set(expected_tables) - set(tables)
            if missing:
                print(f"\n⚠️  Missing tables: {', '.join(missing)}")
                return False

            # Check press data
            cursor.execute("SELECT COUNT(*) FROM press")
            press_count = cursor.fetchone()[0]
            print(f"\n📰 Press organizations: {press_count}")

            cursor.close()
            return True

    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False


def reset_database() -> bool:
    """Reset database (drop all tables)"""
    print("=" * 60)
    print("⚠️  RESETTING DATABASE")
    print("=" * 60)

    result = subprocess.run(
        ["python", "scripts/migrate.py", "reset"],
        cwd=PROJECT_ROOT,
        check=False
    )

    if result.returncode != 0:
        print("❌ Reset failed!")
        return False

    print("✅ Database reset completed")
    return True


def main():
    """Main entry point"""
    print("\n🚀 Database Initialization Script")
    print("=" * 60)

    # Check for reset flag
    if "--reset" in sys.argv:
        if not reset_database():
            return 1

    # Run migrations
    if not run_migrations():
        return 1

    # Seed press data
    if not seed_press_data():
        print("⚠️  Warning: Press data seeding failed, but migrations succeeded")
        print("   You can manually seed data later")

    # Verify setup
    if not verify_setup():
        print("\n⚠️  Warning: Verification found issues")
        return 1

    print("\n" + "=" * 60)
    print("✅ Database initialization completed successfully!")
    print("=" * 60)
    print("\nYou can now:")
    print("  • Run the 30min pipeline: python scripts/run_scraper_with_pipeline.py")
    print("  • Start Celery worker: celery -A src.workers.celery_app worker --loglevel=info")
    print("  • Start the API server: uvicorn src.api.main:app --reload")
    print()

    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
