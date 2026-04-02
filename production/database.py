"""Database initialization and management for Telegram Lead Monitoring System."""

import asyncio
import aiosqlite
from pathlib import Path


DATABASE_FILE = "telegram_leads.db"

# Shared write lock for preventing concurrent database writes
_db_write_lock = asyncio.Lock()


def get_write_lock() -> asyncio.Lock:
    """Get the shared database write lock.
    
    This lock should be used to wrap all database write operations
    to prevent "database is locked" errors from concurrent writes.
    
    Returns:
        The shared asyncio.Lock instance
    """
    return _db_write_lock


async def init_database() -> None:
    """Initialize SQLite database with WAL mode and create all tables."""
    db_path = Path(DATABASE_FILE)
    
    async with aiosqlite.connect(DATABASE_FILE) as db:
        # Enable WAL mode for better concurrency
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        
        # Create userbots table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS userbots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_file TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL CHECK(status IN ('active', 'unavailable', 'banned', 'inactive')),
                unavailable_until TIMESTAMP NULL,
                joins_today INTEGER DEFAULT 0,
                joins_reset_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create chats table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_link TEXT NOT NULL UNIQUE,
                chat_id BIGINT NULL,
                chat_title TEXT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending', 'active', 'error', 'awaiting_approval', 'manual_required')),
                assigned_userbot_id INTEGER NULL REFERENCES userbots(id),
                error_message TEXT NULL,
                joined_at TIMESTAMP NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create join_tasks table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS join_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                userbot_id INTEGER NOT NULL REFERENCES userbots(id),
                chat_id INTEGER NOT NULL REFERENCES chats(id),
                scheduled_at TIMESTAMP NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending', 'processing', 'completed', 'failed')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP NULL
            )
        """)
        
        # Create message_hashes table for deduplication
        await db.execute("""
            CREATE TABLE IF NOT EXISTS message_hashes (
                hash TEXT PRIMARY KEY,
                created_at TIMESTAMP NOT NULL
            )
        """)
        
        # Create index for message_hashes cleanup
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_message_hashes_created_at 
            ON message_hashes(created_at)
        """)
        
        # Create spam_database table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS spam_database (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create index for spam_database
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_spam_created_at 
            ON spam_database(created_at DESC)
        """)
        
        # Create blocklist table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS blocklist (
                user_id BIGINT PRIMARY KEY,
                username TEXT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create activity_logs table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                component TEXT NOT NULL,
                level TEXT NOT NULL CHECK(level IN ('INFO', 'WARNING', 'ERROR')),
                message TEXT NOT NULL,
                metadata JSON NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create index for activity_logs
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_logs_component_created 
            ON activity_logs(component, created_at)
        """)
        
        await db.commit()


def get_connection() -> aiosqlite.Connection:
    """Get a database connection."""
    return aiosqlite.connect(DATABASE_FILE)


if __name__ == "__main__":
    import asyncio
    asyncio.run(init_database())
    print(f"Database initialized: {DATABASE_FILE}")
