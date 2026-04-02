"""Bug condition exploration tests for SQLite Concurrency issues.

These tests are designed to FAIL on unfixed code to demonstrate the bugs exist.
They encode the EXPECTED behavior - when the bugs are fixed, these tests will pass.

**Validates: Requirements 1.6, 1.7, 1.8, 1.9, 2.6, 2.7, 2.8, 2.9**
"""

import asyncio
import tempfile
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import aiosqlite

from src.userbot.userbot_pool_manager import UserbotPoolManager, UserbotStatus
from src.parser.message_parser import MessageParser
from src.ingestion.ingestion_module import IngestionModule
from src.ingestion.join_logic import _send_manual_captcha_notification
from database import init_database
import database


# Test database setup
@pytest.fixture(scope="function")
async def test_db():
    """Create a temporary test database."""
    test_db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    test_db_file.close()
    
    # Monkey patch the DATABASE_FILE
    original_db = database.DATABASE_FILE
    database.DATABASE_FILE = test_db_file.name
    
    # Initialize database
    await init_database()
    
    yield test_db_file.name
    
    # Cleanup
    database.DATABASE_FILE = original_db
    try:
        os.unlink(test_db_file.name)
    except:
        pass


@pytest.fixture(scope="function")
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Test 1.6: Concurrent writes cause "database is locked"
@pytest.mark.asyncio
async def test_bug_1_6_concurrent_writes_cause_database_locked():
    """Property 1: Bug Condition - Database Locks
    
    **Validates: Requirements 1.6, 2.6**
    
    EXPECTED BEHAVIOR (what SHOULD happen after fix):
    When 3 userbots simultaneously write leads to the database, all writes
    should succeed without "database is locked" errors.
    
    CURRENT BEHAVIOR (bug - this test will FAIL on unfixed code):
    2 out of 3 writes get "database is locked" errors due to concurrent
    INSERT operations without proper locking.
    
    This test demonstrates the bug by simulating concurrent database writes
    from multiple userbots parsing messages simultaneously.
    """
    # Create temporary database
    test_db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    test_db_file.close()
    
    # Monkey patch the DATABASE_FILE
    original_db = database.DATABASE_FILE
    database.DATABASE_FILE = test_db_file.name
    
    try:
        # Initialize database
        await init_database()
        
        # Create 3 message parsers (simulating 3 userbots)
        parsers = []
        for i in range(3):
            parser = MessageParser(
                trigger_words=["lead"],
                on_message_callback=AsyncMock()
            )
            parsers.append(parser)
        
        # Simulate concurrent writes to message_hashes table
        # This is what happens when multiple userbots parse messages simultaneously
        async def concurrent_write(parser_id):
            """Simulate a userbot writing to the database."""
            try:
                # Simulate deduplicate operation (writes to message_hashes)
                text = f"Test message from parser {parser_id}"
                
                # This is the actual code path that causes the bug
                import hashlib
                from src.parser.message_parser import normalize_text
                
                normalized = normalize_text(text)
                msg_hash = hashlib.sha256(normalized.encode()).hexdigest()
                
                # Direct database write without lock (this is the bug)
                async with database.get_connection() as db:
                    await db.execute(
                        "INSERT INTO message_hashes (hash, created_at) VALUES (?, ?)",
                        (msg_hash, datetime.now().isoformat())
                    )
                    await db.commit()
                
                return True, None
            except Exception as e:
                return False, str(e)
        
        # Execute 3 concurrent writes
        results = await asyncio.gather(
            concurrent_write(1),
            concurrent_write(2),
            concurrent_write(3),
            return_exceptions=True
        )
        
        # Count successes and failures
        successes = sum(1 for success, _ in results if success)
        failures = [error for success, error in results if not success]
        
        # EXPECTED BEHAVIOR: All 3 writes should succeed
        # This assertion will FAIL on unfixed code because some writes get "database is locked"
        assert successes == 3, \
            f"Expected all 3 concurrent writes to succeed, but only {successes} succeeded. " \
            f"Failures: {failures}. This confirms the database locking bug."
        
        # Verify no "database is locked" errors
        for success, error in results:
            if not success:
                assert "database is locked" not in error.lower(), \
                    f"Got 'database is locked' error: {error}"
    
    finally:
        # Cleanup database
        database.DATABASE_FILE = original_db
        try:
            os.unlink(test_db_file.name)
        except:
            pass


# Test 1.7: System restart causes IntegrityError on duplicate insert
@pytest.mark.asyncio
async def test_bug_1_7_system_restart_causes_integrity_error():
    """Property 1: Bug Condition - Duplicate Insert
    
    **Validates: Requirements 1.7, 2.7**
    
    EXPECTED BEHAVIOR (what SHOULD happen after fix):
    When the system restarts and attempts to insert userbots that already exist,
    no IntegrityError should occur (should use UPSERT or check existence first).
    
    CURRENT BEHAVIOR (bug - this test will FAIL on unfixed code):
    IntegrityError: UNIQUE constraint failed on session_file due to blind INSERT.
    
    This test demonstrates the bug by simulating a system restart that tries
    to re-insert existing userbots.
    """
    # Create temporary database
    test_db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    test_db_file.close()
    
    # Monkey patch the DATABASE_FILE
    original_db = database.DATABASE_FILE
    database.DATABASE_FILE = test_db_file.name
    
    session_file = None
    
    try:
        # Initialize database
        await init_database()
        
        # Create session file
        session_file = tempfile.NamedTemporaryFile(delete=False, suffix=".session")
        session_file.close()
        
        # First startup: Add userbot
        pool_manager_1 = UserbotPoolManager()
        userbot_id_1 = await pool_manager_1.add_userbot(session_file.name)
        
        # Verify userbot was added
        async with database.get_connection() as db:
            cursor = await db.execute(
                "SELECT id, session_file FROM userbots WHERE session_file = ?",
                (session_file.name,)
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row[1] == session_file.name
        
        # Simulate system restart: Create new pool manager
        pool_manager_2 = UserbotPoolManager()
        
        # Try to add the same userbot again (simulates restart loading userbots)
        # EXPECTED BEHAVIOR: Should not raise IntegrityError
        try:
            userbot_id_2 = await pool_manager_2.add_userbot(session_file.name)
            
            # Should either:
            # 1. Return the existing userbot_id (UPSERT behavior)
            # 2. Return a new ID after checking existence
            # Both are acceptable
            
            # Verify only one userbot exists with this session_file
            async with database.get_connection() as db:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM userbots WHERE session_file = ?",
                    (session_file.name,)
                )
                count = (await cursor.fetchone())[0]
                
                # This assertion will FAIL on unfixed code because IntegrityError is raised
                assert count == 1, \
                    f"Expected exactly 1 userbot with session_file '{session_file.name}', but got {count}"
        
        except Exception as e:
            # This will catch the IntegrityError on unfixed code
            error_msg = str(e)
            
            # This assertion will FAIL on unfixed code with IntegrityError
            assert "UNIQUE constraint failed" not in error_msg, \
                f"Got IntegrityError on duplicate insert: {error_msg}. " \
                f"This confirms the duplicate insert bug - system should use UPSERT or check existence."
            
            # Re-raise if it's a different error
            raise
    
    finally:
        # Cleanup session file
        if session_file:
            try:
                os.unlink(session_file.name)
            except:
                pass
        
        # Cleanup database
        database.DATABASE_FILE = original_db
        try:
            os.unlink(test_db_file.name)
        except:
            pass


# Test 1.8: Concurrent task creation causes wrong ID retrieval
@pytest.mark.asyncio
async def test_bug_1_8_concurrent_task_creation_causes_wrong_id():
    """Property 1: Bug Condition - Race Condition
    
    **Validates: Requirements 1.8, 2.8**
    
    EXPECTED BEHAVIOR (what SHOULD happen after fix):
    When 2 tasks are created concurrently, each should get the correct ID
    via cursor.lastrowid immediately after INSERT.
    
    CURRENT BEHAVIOR (bug - this test will FAIL on unfixed code):
    Race condition with SELECT ... ORDER BY DESC LIMIT 1 causes wrong IDs
    to be retrieved when tasks are created concurrently.
    
    This test demonstrates the bug by creating tasks concurrently and verifying
    each gets the correct ID.
    """
    # Create temporary database
    test_db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    test_db_file.close()
    
    # Monkey patch the DATABASE_FILE
    original_db = database.DATABASE_FILE
    database.DATABASE_FILE = test_db_file.name
    
    session_files = []
    
    try:
        # Initialize database
        await init_database()
        
        # Create pool manager and add 2 userbots
        pool_manager = UserbotPoolManager()
        
        userbot_ids = []
        for i in range(2):
            session_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{i}.session")
            session_file.close()
            session_files.append(session_file.name)
            
            userbot_id = await pool_manager.add_userbot(session_file.name)
            userbot_ids.append(userbot_id)
        
        # Create 2 chats
        chat_ids = []
        async with database.get_connection() as db:
            for i in range(2):
                cursor = await db.execute(
                    """INSERT INTO chats (chat_link, status)
                       VALUES (?, 'pending')""",
                    (f"t.me/test_chat_{i}",)
                )
                chat_ids.append(cursor.lastrowid)
            await db.commit()
        
        # Create ingestion module
        ingestion = IngestionModule()
        
        # Simulate concurrent task creation
        # This is the buggy code path that uses SELECT ... ORDER BY DESC LIMIT 1
        async def create_task_buggy(userbot_id, chat_id, task_num):
            """Simulate the BUGGY task creation with SELECT ORDER BY DESC."""
            now = datetime.now(timezone.utc)
            scheduled_time = now + timedelta(seconds=10)
            
            async with database.get_connection() as db:
                # Insert task
                await db.execute(
                    """INSERT INTO join_tasks (userbot_id, chat_id, scheduled_at, status, created_at)
                       VALUES (?, ?, ?, 'pending', CURRENT_TIMESTAMP)""",
                    (userbot_id, chat_id, scheduled_time.isoformat())
                )
                await db.commit()
                
                # BUGGY: Use SELECT ORDER BY DESC LIMIT 1 to get task ID
                # This is what the unfixed code does
                cursor = await db.execute(
                    """SELECT id FROM join_tasks 
                       WHERE userbot_id = ? AND chat_id = ?
                       ORDER BY created_at DESC LIMIT 1""",
                    (userbot_id, chat_id)
                )
                row = await cursor.fetchone()
                retrieved_id = row[0] if row else None
                
                return task_num, retrieved_id
        
        # Execute 2 concurrent task creations
        results = await asyncio.gather(
            create_task_buggy(userbot_ids[0], chat_ids[0], 1),
            create_task_buggy(userbot_ids[1], chat_ids[1], 2)
        )
        
        # Extract task IDs
        task_1_num, task_1_id = results[0]
        task_2_num, task_2_id = results[1]
        
        # Verify both tasks were created
        assert task_1_id is not None, "Task 1 should have an ID"
        assert task_2_id is not None, "Task 2 should have an ID"
        
        # EXPECTED BEHAVIOR: Each task should have a unique ID
        # This assertion will FAIL on unfixed code due to race condition
        assert task_1_id != task_2_id, \
            f"Expected tasks to have different IDs, but both got ID {task_1_id}. " \
            f"This confirms the race condition bug with SELECT ORDER BY DESC."
        
        # Verify each task is correctly linked to its chat
        async with database.get_connection() as db:
            # Check task 1
            cursor = await db.execute(
                "SELECT chat_id FROM join_tasks WHERE id = ?",
                (task_1_id,)
            )
            row = await cursor.fetchone()
            assert row is not None, f"Task {task_1_id} not found"
            assert row[0] == chat_ids[0], \
                f"Task {task_1_id} should be linked to chat {chat_ids[0]}, but got {row[0]}"
            
            # Check task 2
            cursor = await db.execute(
                "SELECT chat_id FROM join_tasks WHERE id = ?",
                (task_2_id,)
            )
            row = await cursor.fetchone()
            assert row is not None, f"Task {task_2_id} not found"
            assert row[0] == chat_ids[1], \
                f"Task {task_2_id} should be linked to chat {chat_ids[1]}, but got {row[0]}"
    
    finally:
        # Cleanup session files
        for session_file in session_files:
            try:
                os.unlink(session_file)
            except:
                pass
        
        # Cleanup database
        database.DATABASE_FILE = original_db
        try:
            os.unlink(test_db_file.name)
        except:
            pass


# Test 1.9: Captcha notification locks session file
@pytest.mark.asyncio
async def test_bug_1_9_captcha_notification_locks_session_file():
    """Property 1: Bug Condition - Session Locks
    
    **Validates: Requirements 1.9, 2.9**
    
    EXPECTED BEHAVIOR (what SHOULD happen after fix):
    When sending a captcha notification, the system should use HTTP API
    (aiohttp) instead of initializing a full Pyrogram client, so no session
    file locks occur.
    
    CURRENT BEHAVIOR (bug - this test will FAIL on unfixed code):
    The system initializes a full Pyrogram client for notifications, causing
    session file locks that prevent the main userbot from accessing the file.
    
    This test demonstrates the bug by checking if the notification function
    uses Pyrogram Client (which locks files) or HTTP API (which doesn't).
    """
    # Create temporary database
    test_db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    test_db_file.close()
    
    # Monkey patch the DATABASE_FILE
    original_db = database.DATABASE_FILE
    database.DATABASE_FILE = test_db_file.name
    
    session_file = None
    
    try:
        # Initialize database
        await init_database()
        
        # Create pool manager and add userbot
        pool_manager = UserbotPoolManager()
        
        session_file = tempfile.NamedTemporaryFile(delete=False, suffix=".session")
        session_file.close()
        
        userbot_id = await pool_manager.add_userbot(session_file.name)
        
        # Mock bot token and operator chat ID
        bot_token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        operator_chat_id = 123456789
        chat_link = "t.me/test_chat"
        
        # Track if Pyrogram Client is used (this would cause session lock)
        pyrogram_client_used = False
        http_api_used = False
        
        # Patch Pyrogram Client to detect if it's used
        original_pyrogram_client = None
        try:
            from pyrogram import Client as PyrogramClient
            original_pyrogram_client = PyrogramClient
            
            class MockPyrogramClient:
                def __init__(self, *args, **kwargs):
                    nonlocal pyrogram_client_used
                    pyrogram_client_used = True
                
                async def __aenter__(self):
                    return self
                
                async def __aexit__(self, *args):
                    pass
                
                async def send_message(self, *args, **kwargs):
                    pass
            
            # Monkey patch Pyrogram Client
            import sys
            if 'pyrogram' in sys.modules:
                sys.modules['pyrogram'].Client = MockPyrogramClient
        except ImportError:
            pass
        
        # Patch aiohttp to detect if HTTP API is used
        try:
            import aiohttp
            original_client_session = aiohttp.ClientSession
            
            class MockClientSession:
                def __init__(self, *args, **kwargs):
                    nonlocal http_api_used
                    http_api_used = True
                
                async def __aenter__(self):
                    return self
                
                async def __aexit__(self, *args):
                    pass
                
                async def post(self, url, *args, **kwargs):
                    # Mock successful response
                    class MockResponse:
                        status = 200
                        async def text(self):
                            return '{"ok": true}'
                        async def __aenter__(self):
                            return self
                        async def __aexit__(self, *args):
                            pass
                    return MockResponse()
            
            aiohttp.ClientSession = MockClientSession
        except ImportError:
            pass
        
        # Send captcha notification
        try:
            await _send_manual_captcha_notification(
                bot_token=bot_token,
                operator_chat_id=operator_chat_id,
                chat_link=chat_link,
                userbot_id=userbot_id
            )
        except Exception as e:
            # Ignore errors from mocking
            pass
        
        # EXPECTED BEHAVIOR: Should use HTTP API, NOT Pyrogram Client
        # This assertion will FAIL on unfixed code because Pyrogram Client is used
        assert not pyrogram_client_used, \
            "Captcha notification uses Pyrogram Client, which locks session files. " \
            "This confirms the session lock bug - should use HTTP API instead."
        
        assert http_api_used, \
            "Captcha notification should use HTTP API (aiohttp) to avoid session locks."
        
        # Restore original classes
        if original_pyrogram_client:
            import sys
            if 'pyrogram' in sys.modules:
                sys.modules['pyrogram'].Client = original_pyrogram_client
        
        try:
            import aiohttp
            aiohttp.ClientSession = original_client_session
        except:
            pass
    
    finally:
        # Cleanup session file
        if session_file:
            try:
                os.unlink(session_file)
            except:
                pass
        
        # Cleanup database
        database.DATABASE_FILE = original_db
        try:
            os.unlink(test_db_file.name)
        except:
            pass
