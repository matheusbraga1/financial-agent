#!/usr/bin/env python3
"""
Migration script: SQLite to PostgreSQL

This script migrates data from SQLite databases to PostgreSQL with:
- Data validation
- Progress tracking
- Error handling and rollback
- Integrity checks
"""

import sys
import os
import logging
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
import sqlite3
import psycopg2
from psycopg2.extras import execute_batch
import json

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('migration.log')
    ]
)
logger = logging.getLogger(__name__)


class MigrationStats:
    """Track migration statistics."""

    def __init__(self):
        self.tables = {}
        self.errors = []
        self.start_time = datetime.now()

    def record_table(self, table_name: str, migrated: int, skipped: int = 0):
        self.tables[table_name] = {
            "migrated": migrated,
            "skipped": skipped,
            "total": migrated + skipped
        }

    def record_error(self, context: str, error: Exception):
        self.errors.append({
            "context": context,
            "error": str(error),
            "timestamp": datetime.now()
        })

    def print_summary(self):
        duration = (datetime.now() - self.start_time).total_seconds()

        print("\n" + "=" * 80)
        print("MIGRATION SUMMARY")
        print("=" * 80)
        print(f"Duration: {duration:.2f} seconds")
        print(f"\nMigrated Records:")

        total_migrated = 0
        total_skipped = 0

        for table, stats in self.tables.items():
            print(f"  {table:.<30} {stats['migrated']:>6} migrated, {stats['skipped']:>4} skipped")
            total_migrated += stats['migrated']
            total_skipped += stats['skipped']

        print(f"  {'TOTAL':.<30} {total_migrated:>6} migrated, {total_skipped:>4} skipped")

        if self.errors:
            print(f"\n⚠️  Errors encountered: {len(self.errors)}")
            for error in self.errors[:5]:  # Show first 5 errors
                print(f"  - {error['context']}: {error['error']}")
            if len(self.errors) > 5:
                print(f"  ... and {len(self.errors) - 5} more (see migration.log)")
        else:
            print("\n✅ No errors!")

        print("=" * 80)


class SQLiteToPostgresMigration:
    """Handle migration from SQLite to PostgreSQL."""

    def __init__(
        self,
        sqlite_db_dir: str,
        pg_config: Dict[str, Any],
        batch_size: int = 1000
    ):
        """
        Initialize migration.

        Args:
            sqlite_db_dir: Directory containing SQLite database files
            pg_config: PostgreSQL connection config
            batch_size: Number of records to insert per batch
        """
        self.sqlite_db_dir = Path(sqlite_db_dir)
        self.pg_config = pg_config
        self.batch_size = batch_size
        self.stats = MigrationStats()

        # Database file paths
        self.users_db = self.sqlite_db_dir / "users.db"
        self.chat_db = self.sqlite_db_dir / "chat_history.db"

        # Validate SQLite databases exist
        if not self.users_db.exists():
            raise FileNotFoundError(f"Users database not found: {self.users_db}")
        if not self.chat_db.exists():
            raise FileNotFoundError(f"Chat history database not found: {self.chat_db}")

    def connect_sqlite(self, db_path: Path) -> sqlite3.Connection:
        """Connect to SQLite database."""
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def connect_postgres(self) -> psycopg2.extensions.connection:
        """Connect to PostgreSQL database."""
        return psycopg2.connect(**self.pg_config)

    def migrate_users(self):
        """Migrate users table."""
        logger.info("Migrating users table...")

        sqlite_conn = self.connect_sqlite(self.users_db)
        pg_conn = self.connect_postgres()

        try:
            # Read from SQLite
            sqlite_cur = sqlite_conn.cursor()
            sqlite_cur.execute("""
                SELECT id, username, email, hashed_password, is_active, is_admin, created_at, updated_at
                FROM users
                ORDER BY id
            """)
            users = sqlite_cur.fetchall()

            # Write to PostgreSQL
            pg_cur = pg_conn.cursor()

            migrated = 0
            for user in users:
                try:
                    pg_cur.execute("""
                        INSERT INTO users (id, username, email, hashed_password, is_active, is_admin, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (username) DO NOTHING
                    """, (
                        user['id'],
                        user['username'],
                        user['email'],
                        user['hashed_password'],
                        bool(user['is_active']),
                        bool(user['is_admin']),
                        user['created_at'],
                        user['updated_at']
                    ))
                    migrated += 1
                except Exception as e:
                    self.stats.record_error(f"User {user['username']}", e)
                    logger.error(f"Failed to migrate user {user['username']}: {e}")

            # Update sequence
            pg_cur.execute("SELECT setval('users_id_seq', COALESCE((SELECT MAX(id) FROM users), 1))")

            pg_conn.commit()
            self.stats.record_table("users", migrated, len(users) - migrated)
            logger.info(f"✅ Migrated {migrated}/{len(users)} users")

        except Exception as e:
            pg_conn.rollback()
            logger.error(f"Users migration failed: {e}")
            raise
        finally:
            sqlite_conn.close()
            pg_conn.close()

    def migrate_refresh_tokens(self):
        """Migrate refresh_tokens table."""
        logger.info("Migrating refresh_tokens table...")

        sqlite_conn = self.connect_sqlite(self.users_db)
        pg_conn = self.connect_postgres()

        try:
            # Read from SQLite
            sqlite_cur = sqlite_conn.cursor()
            sqlite_cur.execute("""
                SELECT id, user_id, token, expires_at, created_at
                FROM refresh_tokens
                ORDER BY id
            """)
            tokens = sqlite_cur.fetchall()

            # Write to PostgreSQL
            pg_cur = pg_conn.cursor()

            migrated = 0
            for token in tokens:
                try:
                    pg_cur.execute("""
                        INSERT INTO refresh_tokens (id, user_id, token, expires_at, created_at)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (token) DO NOTHING
                    """, (
                        token['id'],
                        token['user_id'],
                        token['token'],
                        token['expires_at'],
                        token['created_at']
                    ))
                    migrated += 1
                except Exception as e:
                    self.stats.record_error(f"Token {token['id']}", e)
                    logger.error(f"Failed to migrate token {token['id']}: {e}")

            # Update sequence
            pg_cur.execute("SELECT setval('refresh_tokens_id_seq', COALESCE((SELECT MAX(id) FROM refresh_tokens), 1))")

            pg_conn.commit()
            self.stats.record_table("refresh_tokens", migrated, len(tokens) - migrated)
            logger.info(f"✅ Migrated {migrated}/{len(tokens)} refresh tokens")

        except Exception as e:
            pg_conn.rollback()
            logger.error(f"Refresh tokens migration failed: {e}")
            raise
        finally:
            sqlite_conn.close()
            pg_conn.close()

    def migrate_conversations(self):
        """Migrate conversations table."""
        logger.info("Migrating conversations table...")

        sqlite_conn = self.connect_sqlite(self.chat_db)
        pg_conn = self.connect_postgres()

        try:
            # Read from SQLite
            sqlite_cur = sqlite_conn.cursor()
            sqlite_cur.execute("""
                SELECT session_id, user_id, created_at
                FROM conversations
                ORDER BY created_at
            """)
            conversations = sqlite_cur.fetchall()

            # Write to PostgreSQL
            pg_cur = pg_conn.cursor()

            migrated = 0
            for conv in conversations:
                try:
                    # Convert user_id to integer if present and not empty
                    user_id = None
                    if conv['user_id'] and str(conv['user_id']).strip():
                        try:
                            user_id = int(conv['user_id'])
                        except ValueError:
                            logger.warning(f"Invalid user_id '{conv['user_id']}' for session {conv['session_id']}")

                    pg_cur.execute("""
                        INSERT INTO conversations (session_id, user_id, created_at, updated_at)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (session_id) DO NOTHING
                    """, (
                        conv['session_id'],
                        user_id,
                        conv['created_at'],
                        conv['created_at']  # Use created_at as initial updated_at
                    ))
                    migrated += 1
                except Exception as e:
                    self.stats.record_error(f"Conversation {conv['session_id']}", e)
                    logger.error(f"Failed to migrate conversation {conv['session_id']}: {e}")

            pg_conn.commit()
            self.stats.record_table("conversations", migrated, len(conversations) - migrated)
            logger.info(f"✅ Migrated {migrated}/{len(conversations)} conversations")

        except Exception as e:
            pg_conn.rollback()
            logger.error(f"Conversations migration failed: {e}")
            raise
        finally:
            sqlite_conn.close()
            pg_conn.close()

    def migrate_messages(self):
        """Migrate messages table."""
        logger.info("Migrating messages table...")

        sqlite_conn = self.connect_sqlite(self.chat_db)
        pg_conn = self.connect_postgres()

        try:
            # Read from SQLite
            sqlite_cur = sqlite_conn.cursor()
            sqlite_cur.execute("""
                SELECT id, session_id, role, content, answer, sources_json, model_used, confidence, timestamp
                FROM messages
                ORDER BY id
            """)
            messages = sqlite_cur.fetchall()

            # Write to PostgreSQL in batches
            pg_cur = pg_conn.cursor()

            batch = []
            migrated = 0
            skipped = 0

            for msg in messages:
                try:
                    # Parse sources_json if present
                    sources_json = None
                    if msg['sources_json']:
                        try:
                            sources_json = json.loads(msg['sources_json'])
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON in sources for message {msg['id']}")

                    batch.append((
                        msg['id'],
                        msg['session_id'],
                        msg['role'],
                        msg['content'],
                        msg['answer'],
                        psycopg2.extras.Json(sources_json) if sources_json else None,
                        msg['model_used'],
                        msg['confidence'],
                        msg['timestamp']
                    ))

                    # Insert batch when full
                    if len(batch) >= self.batch_size:
                        execute_batch(pg_cur, """
                            INSERT INTO messages (id, session_id, role, content, answer, sources_json, model_used, confidence, timestamp)
                            VALUES (%s, %s, %s::message_role, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (id) DO NOTHING
                        """, batch)
                        migrated += len(batch)
                        logger.info(f"  Migrated {migrated}/{len(messages)} messages...")
                        batch = []
                        pg_conn.commit()

                except Exception as e:
                    self.stats.record_error(f"Message {msg['id']}", e)
                    logger.error(f"Failed to migrate message {msg['id']}: {e}")
                    skipped += 1

            # Insert remaining batch
            if batch:
                execute_batch(pg_cur, """
                    INSERT INTO messages (id, session_id, role, content, answer, sources_json, model_used, confidence, timestamp)
                    VALUES (%s, %s, %s::message_role, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                """, batch)
                migrated += len(batch)

            # Update sequence
            pg_cur.execute("SELECT setval('messages_id_seq', COALESCE((SELECT MAX(id) FROM messages), 1))")

            pg_conn.commit()
            self.stats.record_table("messages", migrated, skipped)
            logger.info(f"✅ Migrated {migrated}/{len(messages)} messages")

        except Exception as e:
            pg_conn.rollback()
            logger.error(f"Messages migration failed: {e}")
            raise
        finally:
            sqlite_conn.close()
            pg_conn.close()

    def migrate_feedback(self):
        """Migrate feedback table."""
        logger.info("Migrating feedback table...")

        sqlite_conn = self.connect_sqlite(self.chat_db)
        pg_conn = self.connect_postgres()

        try:
            # Read from SQLite
            sqlite_cur = sqlite_conn.cursor()
            sqlite_cur.execute("""
                SELECT id, session_id, message_id, rating, comment, created_at
                FROM feedback
                ORDER BY id
            """)
            feedbacks = sqlite_cur.fetchall()

            # Write to PostgreSQL
            pg_cur = pg_conn.cursor()

            migrated = 0
            for feedback in feedbacks:
                try:
                    # Map rating to enum value
                    rating = feedback['rating'].lower()
                    if rating not in ['positive', 'negative', 'neutral']:
                        rating = 'neutral'

                    pg_cur.execute("""
                        INSERT INTO feedback (id, session_id, message_id, rating, comment, created_at)
                        VALUES (%s, %s, %s, %s::feedback_rating, %s, %s)
                        ON CONFLICT (message_id) DO NOTHING
                    """, (
                        feedback['id'],
                        feedback['session_id'],
                        feedback['message_id'],
                        rating,
                        feedback['comment'],
                        feedback['created_at']
                    ))
                    migrated += 1
                except Exception as e:
                    self.stats.record_error(f"Feedback {feedback['id']}", e)
                    logger.error(f"Failed to migrate feedback {feedback['id']}: {e}")

            # Update sequence
            pg_cur.execute("SELECT setval('feedback_id_seq', COALESCE((SELECT MAX(id) FROM feedback), 1))")

            pg_conn.commit()
            self.stats.record_table("feedback", migrated, len(feedbacks) - migrated)
            logger.info(f"✅ Migrated {migrated}/{len(feedbacks)} feedback records")

        except Exception as e:
            pg_conn.rollback()
            logger.error(f"Feedback migration failed: {e}")
            raise
        finally:
            sqlite_conn.close()
            pg_conn.close()

    def verify_migration(self):
        """Verify migration integrity."""
        logger.info("Verifying migration...")

        sqlite_users_conn = self.connect_sqlite(self.users_db)
        sqlite_chat_conn = self.connect_sqlite(self.chat_db)
        pg_conn = self.connect_postgres()

        try:
            pg_cur = pg_conn.cursor()

            # Verify users count
            sqlite_cur = sqlite_users_conn.cursor()
            sqlite_cur.execute("SELECT COUNT(*) as count FROM users")
            sqlite_users = sqlite_cur.fetchone()['count']

            pg_cur.execute("SELECT COUNT(*) FROM users")
            pg_users = pg_cur.fetchone()[0]

            logger.info(f"Users: SQLite={sqlite_users}, PostgreSQL={pg_users}")

            # Verify messages count
            sqlite_cur = sqlite_chat_conn.cursor()
            sqlite_cur.execute("SELECT COUNT(*) as count FROM messages")
            sqlite_messages = sqlite_cur.fetchone()['count']

            pg_cur.execute("SELECT COUNT(*) FROM messages")
            pg_messages = pg_cur.fetchone()[0]

            logger.info(f"Messages: SQLite={sqlite_messages}, PostgreSQL={pg_messages}")

            if sqlite_users == pg_users and sqlite_messages == pg_messages:
                logger.info("✅ Migration verification passed!")
            else:
                logger.warning("⚠️  Count mismatch detected - review migration.log")

        finally:
            sqlite_users_conn.close()
            sqlite_chat_conn.close()
            pg_conn.close()

    def run(self):
        """Execute full migration."""
        logger.info("=" * 80)
        logger.info("Starting SQLite to PostgreSQL migration...")
        logger.info("=" * 80)

        try:
            # Migrate in order (respecting foreign keys)
            self.migrate_users()
            self.migrate_refresh_tokens()
            self.migrate_conversations()
            self.migrate_messages()
            self.migrate_feedback()

            # Verify migration
            self.verify_migration()

            # Print summary
            self.stats.print_summary()

            logger.info("✅ Migration completed successfully!")
            return True

        except Exception as e:
            logger.error(f"❌ Migration failed: {e}")
            self.stats.print_summary()
            return False


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Migrate from SQLite to PostgreSQL")
    parser.add_argument(
        "--sqlite-dir",
        default="app_data",
        help="Directory containing SQLite databases (default: app_data)"
    )
    parser.add_argument("--pg-host", default="localhost", help="PostgreSQL host")
    parser.add_argument("--pg-port", type=int, default=5432, help="PostgreSQL port")
    parser.add_argument("--pg-database", default="financial_agent", help="PostgreSQL database name")
    parser.add_argument("--pg-user", default="postgres", help="PostgreSQL user")
    parser.add_argument("--pg-password", required=True, help="PostgreSQL password")
    parser.add_argument("--batch-size", type=int, default=1000, help="Batch size for inserts")

    args = parser.parse_args()

    pg_config = {
        "host": args.pg_host,
        "port": args.pg_port,
        "database": args.pg_database,
        "user": args.pg_user,
        "password": args.pg_password,
    }

    migration = SQLiteToPostgresMigration(
        sqlite_db_dir=args.sqlite_dir,
        pg_config=pg_config,
        batch_size=args.batch_size
    )

    success = migration.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
