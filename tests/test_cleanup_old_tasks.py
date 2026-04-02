"""Test for cleanup_old_tasks functionality.

This test verifies that old pending tasks are properly marked as failed
to prevent accumulation in the database.

**Validates: Requirements 2.1**
"""

import asyncio
import tempfile
import os
from datetime import datetime, timedelta, timezone
import pytest
import aiosqlite

from src.ingestion.join_queue import JoinQueue
from database import init_database


@pytest.mark.asyncio
async def test_cleanup_old_tasks():
    """Test that cleanup_old_tasks marks old pending tasks as failed."""
    # Create temporary database
    test_db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    test_db_file.close()
    
    # Monkey patch the DATABASE_FILE
    import database
    original_db = database.DATABASE_FILE
    database.DATABASE_FILE = test_db_file.name
    
    try:
        # Initialize database
        await init_database()
        
        # Create userbot and tasks in database
        async with database.get_connection() as db:
            cursor = await db.execute(
                """INSERT INTO userbots (session_file, status, joins_today, joins_reset_at)
                   VALUES (?, 'active', 0, ?)""",
                ("session_test_cleanup.session", (datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
            )
            userbot_id = cursor.lastrowid
            
            # Create old tasks (created 2 hours ago)
            old_created_at = datetime.now(timezone.utc) - timedelta(hours=2)
            old_scheduled_at = old_created_at + timedelta(seconds=60)
            
            for i in range(3):
                cursor = await db.execute(
                    """INSERT INTO chats (chat_link, status, assigned_userbot_id)
                       VALUES (?, 'pending', ?)""",
                    (f"t.me/old_chat_cleanup_{i}", userbot_id)
                )
                chat_id = cursor.lastrowid
                
                await db.execute(
                    """INSERT INTO join_tasks (userbot_id, chat_id, scheduled_at, status, created_at)
                       VALUES (?, ?, ?, 'pending', ?)""",
                    (userbot_id, chat_id, old_scheduled_at.isoformat(), old_created_at.isoformat())
                )
            
            # Create recent tasks (created 30 minutes ago)
            recent_created_at = datetime.now(timezone.utc) - timedelta(minutes=30)
            recent_scheduled_at = recent_created_at + timedelta(seconds=60)
            
            for i in range(2):
                cursor = await db.execute(
                    """INSERT INTO chats (chat_link, status, assigned_userbot_id)
                       VALUES (?, 'pending', ?)""",
                    (f"t.me/recent_chat_cleanup_{i}", userbot_id)
                )
                chat_id = cursor.lastrowid
                
                await db.execute(
                    """INSERT INTO join_tasks (userbot_id, chat_id, scheduled_at, status, created_at)
                       VALUES (?, ?, ?, 'pending', ?)""",
                    (userbot_id, chat_id, recent_scheduled_at.isoformat(), recent_created_at.isoformat())
                )
            
            await db.commit()
        
        # Verify initial state: 5 pending tasks
        async with database.get_connection() as db:
            cursor = await db.execute("SELECT COUNT(*) FROM join_tasks WHERE status = 'pending'")
            count = (await cursor.fetchone())[0]
            assert count == 5, f"Expected 5 pending tasks, got {count}"
        
        # Run cleanup
        queue = JoinQueue()
        cleaned_count = await queue.cleanup_old_tasks()
        
        # Verify 3 old tasks were marked as failed
        assert cleaned_count == 3, f"Expected 3 tasks cleaned, got {cleaned_count}"
        
        # Verify database state
        async with database.get_connection() as db:
            # Check pending tasks (should be 2 recent ones)
            cursor = await db.execute("SELECT COUNT(*) FROM join_tasks WHERE status = 'pending'")
            pending_count = (await cursor.fetchone())[0]
            assert pending_count == 2, f"Expected 2 pending tasks, got {pending_count}"
            
            # Check failed tasks (should be 3 old ones)
            cursor = await db.execute("SELECT COUNT(*) FROM join_tasks WHERE status = 'failed'")
            failed_count = (await cursor.fetchone())[0]
            assert failed_count == 3, f"Expected 3 failed tasks, got {failed_count}"
    
    finally:
        # Cleanup
        database.DATABASE_FILE = original_db
        try:
            os.unlink(test_db_file.name)
        except:
            pass


@pytest.mark.asyncio
async def test_load_pending_tasks_loads_all_tasks():
    """Test that load_pending_tasks loads ALL pending tasks regardless of creation time.
    
    This is the FIXED behavior - load_pending_tasks() now loads all pending tasks
    including old ones. The cleanup_old_tasks() method is responsible for marking
    truly old tasks as failed before loading.
    """
    # Create temporary database
    test_db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    test_db_file.close()
    
    # Monkey patch the DATABASE_FILE
    import database
    original_db = database.DATABASE_FILE
    database.DATABASE_FILE = test_db_file.name
    
    try:
        # Initialize database
        await init_database()
        
        # Create userbot and tasks in database
        async with database.get_connection() as db:
            cursor = await db.execute(
                """INSERT INTO userbots (session_file, status, joins_today, joins_reset_at)
                   VALUES (?, 'active', 0, ?)""",
                ("session_test_filter.session", (datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
            )
            userbot_id = cursor.lastrowid
            
            # Create old tasks (created 2 hours ago)
            old_created_at = datetime.now(timezone.utc) - timedelta(hours=2)
            old_scheduled_at = old_created_at + timedelta(seconds=60)
            
            for i in range(3):
                cursor = await db.execute(
                    """INSERT INTO chats (chat_link, status, assigned_userbot_id)
                       VALUES (?, 'pending', ?)""",
                    (f"t.me/old_chat_filter_{i}", userbot_id)
                )
                chat_id = cursor.lastrowid
                
                await db.execute(
                    """INSERT INTO join_tasks (userbot_id, chat_id, scheduled_at, status, created_at)
                       VALUES (?, ?, ?, 'pending', ?)""",
                    (userbot_id, chat_id, old_scheduled_at.isoformat(), old_created_at.isoformat())
                )
            
            # Create recent tasks (created 30 minutes ago)
            recent_created_at = datetime.now(timezone.utc) - timedelta(minutes=30)
            recent_scheduled_at = recent_created_at + timedelta(seconds=60)
            
            for i in range(2):
                cursor = await db.execute(
                    """INSERT INTO chats (chat_link, status, assigned_userbot_id)
                       VALUES (?, 'pending', ?)""",
                    (f"t.me/recent_chat_filter_{i}", userbot_id)
                )
                chat_id = cursor.lastrowid
                
                await db.execute(
                    """INSERT INTO join_tasks (userbot_id, chat_id, scheduled_at, status, created_at)
                       VALUES (?, ?, ?, 'pending', ?)""",
                    (userbot_id, chat_id, recent_scheduled_at.isoformat(), recent_created_at.isoformat())
                )
            
            await db.commit()
        
        # Load pending tasks
        queue = JoinQueue()
        loaded_count = await queue.load_pending_tasks()
        
        # Should load ALL 5 pending tasks (3 old + 2 recent)
        assert loaded_count == 5, f"Expected 5 tasks loaded, got {loaded_count}"
        assert queue.qsize() == 5, f"Expected queue size 5, got {queue.qsize()}"
    
    finally:
        # Cleanup
        database.DATABASE_FILE = original_db
        try:
            os.unlink(test_db_file.name)
        except:
            pass


@pytest.mark.asyncio
async def test_cleanup_and_load_workflow():
    """Test the complete workflow: cleanup old tasks, then load recent ones."""
    # Create temporary database
    test_db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    test_db_file.close()
    
    # Monkey patch the DATABASE_FILE
    import database
    original_db = database.DATABASE_FILE
    database.DATABASE_FILE = test_db_file.name
    
    try:
        # Initialize database
        await init_database()
        
        # Create userbot and tasks in database
        async with database.get_connection() as db:
            cursor = await db.execute(
                """INSERT INTO userbots (session_file, status, joins_today, joins_reset_at)
                   VALUES (?, 'active', 0, ?)""",
                ("session_test_workflow.session", (datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
            )
            userbot_id = cursor.lastrowid
            
            # Create old tasks (created 2 hours ago)
            old_created_at = datetime.now(timezone.utc) - timedelta(hours=2)
            old_scheduled_at = old_created_at + timedelta(seconds=60)
            
            for i in range(5):
                cursor = await db.execute(
                    """INSERT INTO chats (chat_link, status, assigned_userbot_id)
                       VALUES (?, 'pending', ?)""",
                    (f"t.me/old_chat_workflow_{i}", userbot_id)
                )
                chat_id = cursor.lastrowid
                
                await db.execute(
                    """INSERT INTO join_tasks (userbot_id, chat_id, scheduled_at, status, created_at)
                       VALUES (?, ?, ?, 'pending', ?)""",
                    (userbot_id, chat_id, old_scheduled_at.isoformat(), old_created_at.isoformat())
                )
            
            # Create recent tasks (created 30 minutes ago)
            recent_created_at = datetime.now(timezone.utc) - timedelta(minutes=30)
            recent_scheduled_at = recent_created_at + timedelta(seconds=60)
            
            for i in range(3):
                cursor = await db.execute(
                    """INSERT INTO chats (chat_link, status, assigned_userbot_id)
                       VALUES (?, 'pending', ?)""",
                    (f"t.me/recent_chat_workflow_{i}", userbot_id)
                )
                chat_id = cursor.lastrowid
                
                await db.execute(
                    """INSERT INTO join_tasks (userbot_id, chat_id, scheduled_at, status, created_at)
                       VALUES (?, ?, ?, 'pending', ?)""",
                    (userbot_id, chat_id, recent_scheduled_at.isoformat(), recent_created_at.isoformat())
                )
            
            await db.commit()
        
        # Simulate system startup workflow
        queue = JoinQueue()
        
        # Step 1: Cleanup old tasks
        cleaned_count = await queue.cleanup_old_tasks()
        assert cleaned_count == 5, f"Expected 5 tasks cleaned, got {cleaned_count}"
        
        # Step 2: Load recent tasks
        loaded_count = await queue.load_pending_tasks()
        assert loaded_count == 3, f"Expected 3 tasks loaded, got {loaded_count}"
        
        # Verify final state
        async with database.get_connection() as db:
            cursor = await db.execute("SELECT COUNT(*) FROM join_tasks WHERE status = 'pending'")
            pending_count = (await cursor.fetchone())[0]
            assert pending_count == 3, f"Expected 3 pending tasks, got {pending_count}"
            
            cursor = await db.execute("SELECT COUNT(*) FROM join_tasks WHERE status = 'failed'")
            failed_count = (await cursor.fetchone())[0]
            assert failed_count == 5, f"Expected 5 failed tasks, got {failed_count}"
        
        assert queue.qsize() == 3, f"Expected queue size 3, got {queue.qsize()}"
    
    finally:
        # Cleanup
        database.DATABASE_FILE = original_db
        try:
            os.unlink(test_db_file.name)
        except:
            pass
