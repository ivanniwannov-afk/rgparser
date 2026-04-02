"""Standalone script to verify that load_pending_tasks() correctly parses scheduled_at.

This script validates that the scheduled_at timestamp is:
1. Correctly parsed from ISO format string in the database
2. Converted to a timezone-aware datetime object
3. Properly used for task scheduling and comparison
"""

import asyncio
from datetime import datetime, timezone, timedelta
import aiosqlite
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.ingestion.join_queue import JoinQueue, JoinTask


TEST_DB = "test_scheduled_parsing_verify.db"


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
    
    print(f"✓ Test database initialized: {TEST_DB}")


def get_test_connection():
    """Get a test database connection."""
    return aiosqlite.connect(TEST_DB)


async def test_iso_format_parsing():
    """Test that scheduled_at is correctly parsed from ISO format."""
    print("\n=== Test 1: ISO Format Parsing ===")
    
    # Create a test scheduled time (5 minutes ago - overdue task)
    scheduled_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    scheduled_str = scheduled_time.isoformat()
    
    print(f"Creating task with scheduled_at: {scheduled_str}")
    
    # Insert a test task
    async with get_test_connection() as db:
        cursor = await db.execute(
            """INSERT INTO userbots (session_file, status, joins_reset_at)
               VALUES (?, ?, ?)""",
            ("test_session_1.session", "active", datetime.now(timezone.utc).isoformat())
        )
        userbot_id = cursor.lastrowid
        
        cursor = await db.execute(
            """INSERT INTO chats (chat_link, status)
               VALUES (?, ?)""",
            ("https://t.me/testchat1", "pending")
        )
        chat_id = cursor.lastrowid
        
        await db.execute(
            """INSERT INTO join_tasks (userbot_id, chat_id, scheduled_at, status)
               VALUES (?, ?, ?, ?)""",
            (userbot_id, chat_id, scheduled_str, "pending")
        )
        await db.commit()
    
    # Monkey-patch database module
    import database
    original_get_connection = database.get_connection
    database.get_connection = get_test_connection
    
    try:
        # Load tasks using JoinQueue
        queue = JoinQueue()
        loaded_count = await queue.load_pending_tasks()
        
        print(f"✓ Loaded {loaded_count} task(s)")
        assert loaded_count == 1, f"Expected 1 task, got {loaded_count}"
        
        # Get the task
        task = await asyncio.wait_for(queue.get_next_task(), timeout=2.0)
        
        # Verify task
        assert task is not None, "Task should not be None"
        print(f"✓ Task retrieved: task_id={task.task_id}")
        
        # Verify scheduled_at is datetime
        assert isinstance(task.scheduled_at, datetime), \
            f"scheduled_at should be datetime, got {type(task.scheduled_at)}"
        print(f"✓ scheduled_at is datetime object")
        
        # Verify timezone-aware
        assert task.scheduled_at.tzinfo is not None, "scheduled_at should be timezone-aware"
        assert task.scheduled_at.tzinfo == timezone.utc, "timezone should be UTC"
        print(f"✓ scheduled_at is timezone-aware (UTC)")
        
        # Verify parsed time matches original
        time_diff = abs((task.scheduled_at - scheduled_time).total_seconds())
        assert time_diff < 1.0, f"Time difference too large: {time_diff}s"
        print(f"✓ Parsed time matches original (diff: {time_diff:.3f}s)")
        
        # Verify task is overdue
        now = datetime.now(timezone.utc)
        assert task.scheduled_at <= now, "Task should be overdue"
        overdue_seconds = (now - task.scheduled_at).total_seconds()
        print(f"✓ Task is overdue by {overdue_seconds:.0f} seconds")
        
        print("\n✅ Test 1 PASSED: ISO format parsing works correctly")
        
    finally:
        # Restore original function
        database.get_connection = original_get_connection


async def test_naive_datetime_handling():
    """Test that naive datetime (without timezone) is handled correctly."""
    print("\n=== Test 2: Naive Datetime Handling ===")
    
    # Create a naive datetime string (no timezone info)
    scheduled_time_naive = datetime.now() - timedelta(minutes=3)
    scheduled_str_naive = scheduled_time_naive.isoformat()
    
    print(f"Creating task with naive datetime: {scheduled_str_naive}")
    
    # Insert task
    async with get_test_connection() as db:
        cursor = await db.execute(
            """INSERT INTO userbots (session_file, status, joins_reset_at)
               VALUES (?, ?, ?)""",
            ("test_session_2.session", "active", datetime.now(timezone.utc).isoformat())
        )
        userbot_id = cursor.lastrowid
        
        cursor = await db.execute(
            """INSERT INTO chats (chat_link, status)
               VALUES (?, ?)""",
            ("https://t.me/testchat2", "pending")
        )
        chat_id = cursor.lastrowid
        
        await db.execute(
            """INSERT INTO join_tasks (userbot_id, chat_id, scheduled_at, status)
               VALUES (?, ?, ?, ?)""",
            (userbot_id, chat_id, scheduled_str_naive, "pending")
        )
        await db.commit()
    
    # Monkey-patch database module
    import database
    original_get_connection = database.get_connection
    database.get_connection = get_test_connection
    
    try:
        # Load tasks
        queue = JoinQueue()
        loaded_count = await queue.load_pending_tasks()
        
        print(f"✓ Loaded {loaded_count} task(s)")
        
        # Get task
        task = await asyncio.wait_for(queue.get_next_task(), timeout=2.0)
        
        # Verify timezone was added
        assert task is not None, "Task should not be None"
        assert task.scheduled_at.tzinfo is not None, \
            "JoinTask should add timezone to naive datetime"
        assert task.scheduled_at.tzinfo == timezone.utc, \
            "Default timezone should be UTC"
        
        print(f"✓ Naive datetime converted to timezone-aware (UTC)")
        print("\n✅ Test 2 PASSED: Naive datetime handling works correctly")
        
    finally:
        # Restore original function
        database.get_connection = original_get_connection


async def main():
    """Run all tests."""
    print("=" * 60)
    print("VERIFICATION: scheduled_at Parsing in load_pending_tasks()")
    print("=" * 60)
    
    try:
        # Initialize test database
        await init_test_database()
        
        # Run tests
        await test_iso_format_parsing()
        await test_naive_datetime_handling()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        print("\nConclusion:")
        print("- load_pending_tasks() correctly parses scheduled_at from database")
        print("- datetime.fromisoformat() works correctly for ISO format strings")
        print("- JoinTask.__post_init__() adds UTC timezone to naive datetimes")
        print("- Parsed datetime objects are properly timezone-aware")
        print("- Overdue tasks are correctly identified and returned immediately")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # Cleanup
        db_path = Path(TEST_DB)
        if db_path.exists():
            db_path.unlink()
            print(f"\n✓ Cleaned up test database: {TEST_DB}")
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
