"""Test to verify that load_pending_tasks() correctly parses scheduled_at from database.

This test validates that the scheduled_at timestamp is:
1. Correctly parsed from ISO format string in the database
2. Converted to a timezone-aware datetime object
3. Properly used for task scheduling and comparison
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
import aiosqlite
from pathlib import Path
import os
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.join_queue import JoinQueue, JoinTask


TEST_DB = "test_scheduled_parsing.db"


async def init_test_database():
    """Initialize test database."""
    db_path = Path(TEST_DB)
    if db_path.exists():
        db_path.unlink()
    
    async with aiosqlite.connect(TEST_DB) as db:
        # Enable WAL mode
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
        
        await db.commit()


def get_test_connection():
    """Get a test database connection."""
    return aiosqlite.connect(TEST_DB)


@pytest.fixture
async def clean_database():
    """Create a clean test database."""
    await init_test_database()
    
    # Monkey-patch the database module to use test database
    import database
    original_get_connection = database.get_connection
    database.get_connection = get_test_connection
    
    yield
    
    # Restore original function
    database.get_connection = original_get_connection
    
    # Cleanup
    db_path = Path(TEST_DB)
    if db_path.exists():
        db_path.unlink()


@pytest.mark.asyncio
async def test_scheduled_at_parsing_iso_format(clean_database):
    """Test that scheduled_at is correctly parsed from ISO format in database."""
    # Create a test scheduled time (5 minutes ago - overdue task)
    scheduled_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    scheduled_str = scheduled_time.isoformat()
    
    # Insert a test task directly into database
    async with get_test_connection() as db:
        # Create a test userbot
        cursor = await db.execute(
            """INSERT INTO userbots (session_file, status, joins_reset_at)
               VALUES (?, ?, ?)""",
            ("test_session.session", "active", datetime.now(timezone.utc).isoformat())
        )
        userbot_id = cursor.lastrowid
        
        # Create a test chat
        cursor = await db.execute(
            """INSERT INTO chats (chat_link, status)
               VALUES (?, ?)""",
            ("https://t.me/testchat", "pending")
        )
        chat_id = cursor.lastrowid
        
        # Create a pending join task with specific scheduled_at
        await db.execute(
            """INSERT INTO join_tasks (userbot_id, chat_id, scheduled_at, status)
               VALUES (?, ?, ?, ?)""",
            (userbot_id, chat_id, scheduled_str, "pending")
        )
        await db.commit()
    
    # Load tasks using JoinQueue
    queue = JoinQueue()
    loaded_count = await queue.load_pending_tasks()
    
    # Verify task was loaded
    assert loaded_count == 1, f"Expected 1 task to be loaded, got {loaded_count}"
    
    # Get the task from queue
    task = await asyncio.wait_for(queue.get_next_task(), timeout=2.0)
    
    # Verify task is not None
    assert task is not None, "Expected task to be returned, got None"
    
    # Verify scheduled_at is a datetime object
    assert isinstance(task.scheduled_at, datetime), \
        f"Expected scheduled_at to be datetime, got {type(task.scheduled_at)}"
    
    # Verify scheduled_at is timezone-aware
    assert task.scheduled_at.tzinfo is not None, \
        "Expected scheduled_at to be timezone-aware"
    assert task.scheduled_at.tzinfo == timezone.utc, \
        f"Expected timezone to be UTC, got {task.scheduled_at.tzinfo}"
    
    # Verify the parsed time matches the original (within 1 second tolerance)
    time_diff = abs((task.scheduled_at - scheduled_time).total_seconds())
    assert time_diff < 1.0, \
        f"Parsed time differs from original by {time_diff} seconds"
    
    # Verify task is recognized as overdue
    now = datetime.now(timezone.utc)
    assert task.scheduled_at <= now, \
        f"Task should be overdue: scheduled_at={task.scheduled_at}, now={now}"


@pytest.mark.asyncio
async def test_scheduled_at_parsing_multiple_tasks(clean_database):
    """Test parsing of multiple tasks with different scheduled times."""
    now = datetime.now(timezone.utc)
    
    # Create tasks with different scheduled times
    tasks_data = [
        (now - timedelta(minutes=10), "overdue_10min"),  # Overdue by 10 minutes
        (now - timedelta(minutes=5), "overdue_5min"),    # Overdue by 5 minutes
        (now - timedelta(seconds=30), "overdue_30sec"),  # Overdue by 30 seconds
    ]
    
    # Insert tasks into database
    async with get_test_connection() as db:
        # Create a test userbot
        cursor = await db.execute(
            """INSERT INTO userbots (session_file, status, joins_reset_at)
               VALUES (?, ?, ?)""",
            ("test_session_multi.session", "active", now.isoformat())
        )
        userbot_id = cursor.lastrowid
        
        # Create test chats and tasks
        for scheduled_time, chat_name in tasks_data:
            cursor = await db.execute(
                """INSERT INTO chats (chat_link, status)
                   VALUES (?, ?)""",
                (f"https://t.me/{chat_name}", "pending")
            )
            chat_id = cursor.lastrowid
            
            await db.execute(
                """INSERT INTO join_tasks (userbot_id, chat_id, scheduled_at, status)
                   VALUES (?, ?, ?, ?)""",
                (userbot_id, chat_id, scheduled_time.isoformat(), "pending")
            )
        
        await db.commit()
    
    # Load tasks
    queue = JoinQueue()
    loaded_count = await queue.load_pending_tasks()
    
    # Verify all tasks were loaded
    assert loaded_count == 3, f"Expected 3 tasks to be loaded, got {loaded_count}"
    
    # Get tasks and verify they are returned in correct order (earliest first)
    previous_scheduled_at = None
    for i in range(3):
        task = await asyncio.wait_for(queue.get_next_task(), timeout=2.0)
        assert task is not None, f"Expected task {i+1} to be returned"
        
        # Verify timezone-aware
        assert task.scheduled_at.tzinfo is not None, \
            f"Task {i+1} scheduled_at should be timezone-aware"
        
        # Verify order (should be ascending by scheduled_at)
        if previous_scheduled_at is not None:
            assert task.scheduled_at >= previous_scheduled_at, \
                f"Tasks should be ordered by scheduled_at"
        
        previous_scheduled_at = task.scheduled_at


@pytest.mark.asyncio
async def test_scheduled_at_parsing_naive_datetime_handling(clean_database):
    """Test that naive datetime (without timezone) is handled correctly."""
    # Create a naive datetime string (no timezone info)
    scheduled_time_naive = datetime.now() - timedelta(minutes=5)
    scheduled_str_naive = scheduled_time_naive.isoformat()  # No timezone
    
    # Insert task with naive datetime
    async with get_test_connection() as db:
        cursor = await db.execute(
            """INSERT INTO userbots (session_file, status, joins_reset_at)
               VALUES (?, ?, ?)""",
            ("test_session_naive.session", "active", datetime.now(timezone.utc).isoformat())
        )
        userbot_id = cursor.lastrowid
        
        cursor = await db.execute(
            """INSERT INTO chats (chat_link, status)
               VALUES (?, ?)""",
            ("https://t.me/testchat", "pending")
        )
        chat_id = cursor.lastrowid
        
        await db.execute(
            """INSERT INTO join_tasks (userbot_id, chat_id, scheduled_at, status)
               VALUES (?, ?, ?, ?)""",
            (userbot_id, chat_id, scheduled_str_naive, "pending")
        )
        await db.commit()
    
    # Load tasks
    queue = JoinQueue()
    loaded_count = await queue.load_pending_tasks()
    
    assert loaded_count == 1, f"Expected 1 task to be loaded, got {loaded_count}"
    
    # Get task
    task = await asyncio.wait_for(queue.get_next_task(), timeout=2.0)
    
    # Verify task has timezone info (should be added by JoinTask.__post_init__)
    assert task is not None, "Expected task to be returned"
    assert task.scheduled_at.tzinfo is not None, \
        "JoinTask should add timezone to naive datetime"
    assert task.scheduled_at.tzinfo == timezone.utc, \
        "Default timezone should be UTC"


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
