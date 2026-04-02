"""Bug condition exploration tests for Database State Management issues.

These tests are designed to FAIL on unfixed code to demonstrate the bugs exist.
They encode the EXPECTED behavior - when the bugs are fixed, these tests will pass.

**Validates: Requirements 1.3, 1.4, 1.5, 2.3, 2.4, 2.5**
"""

import asyncio
import tempfile
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.userbot.userbot_pool_manager import UserbotPoolManager, UserbotStatus
from src.ingestion.join_logic import JoinLogic, safe_join_chat
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


# Test 1.3: Dead bot continues receiving assignments
@pytest.mark.asyncio
async def test_bug_1_3_dead_bot_continues_receiving_assignments():
    """Property 1: Bug Condition - Dead Bots
    
    **Validates: Requirements 1.3, 2.3**
    
    EXPECTED BEHAVIOR (what SHOULD happen after fix):
    When userbot client fails to start (returns None), the userbot status
    should be updated to 'banned' or 'error', and it should NOT receive
    new task assignments.
    
    CURRENT BEHAVIOR (bug - this test will FAIL on unfixed code):
    The userbot status stays 'active' and continues receiving task assignments
    even though the client is dead.
    
    This test demonstrates the bug by showing that a dead bot (client start
    failure) continues to be marked as available and receives assignments.
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
        
        # Create pool manager
        pool_manager = UserbotPoolManager()
        
        # Create session file and add userbot
        session_file = tempfile.NamedTemporaryFile(delete=False, suffix=".session")
        session_file.close()
        
        userbot_id = await pool_manager.add_userbot(session_file.name)
        
        # Verify userbot is initially active
        async with database.get_connection() as db:
            cursor = await db.execute(
                "SELECT status FROM userbots WHERE id = ?",
                (userbot_id,)
            )
            row = await cursor.fetchone()
            assert row[0] == UserbotStatus.ACTIVE.value
        
        # Mock get_client to simulate client start failure (returns None)
        # This simulates a banned or corrupted session
        async def mock_get_client(uid):
            if uid == userbot_id:
                return None  # Simulate client start failure
            return MagicMock()
        
        pool_manager.get_client = mock_get_client
        
        # Try to get client (simulates what happens during task execution)
        client = await pool_manager.get_client(userbot_id)
        assert client is None  # Client failed to start
        
        # EXPECTED BEHAVIOR: Userbot should be marked as 'banned' or 'error'
        async with database.get_connection() as db:
            cursor = await db.execute(
                "SELECT status FROM userbots WHERE id = ?",
                (userbot_id,)
            )
            row = await cursor.fetchone()
            status = row[0]
            
            # This assertion will FAIL on unfixed code because status stays 'active'
            assert status in (UserbotStatus.BANNED.value, 'error'), \
                f"Expected userbot to be marked 'banned' or 'error' after client start failure, but got '{status}'"
        
        # EXPECTED BEHAVIOR: Dead bot should NOT be in available list
        available = await pool_manager.get_available_userbots()
        
        # This assertion will FAIL on unfixed code because dead bot is still available
        assert not any(ub.id == userbot_id for ub in available), \
            "Expected dead bot (client start failed) to NOT be available for task assignments"
    
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


# Test 1.4: Chat stuck with assigned bot after join failure
@pytest.mark.asyncio
async def test_bug_1_4_chat_stuck_with_assigned_bot_after_join_failure():
    """Property 1: Bug Condition - Stuck Chats
    
    **Validates: Requirements 1.4, 2.4**
    
    EXPECTED BEHAVIOR (what SHOULD happen after fix):
    When a join task fails (e.g., ChannelPrivate error), the assigned_userbot_id
    should be reset to NULL, and the chat should be able to be reassigned to
    another bot.
    
    CURRENT BEHAVIOR (bug - this test will FAIL on unfixed code):
    The assigned_userbot_id is NOT reset, and the chat gets stuck in 'pending'
    status with an assigned bot, preventing reassignment.
    
    This test demonstrates the bug by showing that after a join failure,
    the chat remains assigned to the bot.
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
        
        # Create pool manager
        pool_manager = UserbotPoolManager()
        
        # Create session file and add userbot
        session_file = tempfile.NamedTemporaryFile(delete=False, suffix=".session")
        session_file.close()
        
        userbot_id = await pool_manager.add_userbot(session_file.name)
        
        # Create a chat and assign it to the userbot
        async with database.get_connection() as db:
            cursor = await db.execute(
                """INSERT INTO chats (chat_link, status, assigned_userbot_id)
                   VALUES (?, 'pending', ?)""",
                ("t.me/test_private_chat", userbot_id)
            )
            chat_id = cursor.lastrowid
            await db.commit()
        
        # Verify chat is assigned to userbot
        async with database.get_connection() as db:
            cursor = await db.execute(
                "SELECT assigned_userbot_id FROM chats WHERE id = ?",
                (chat_id,)
            )
            row = await cursor.fetchone()
            assert row[0] == userbot_id
        
        # Mock Pyrogram client to simulate ChannelPrivate error
        from pyrogram.errors import ChannelPrivate
        
        mock_client = MagicMock()
        mock_client.join_chat = AsyncMock(side_effect=ChannelPrivate())
        
        # Call safe_join_chat which should handle the error
        success, error_msg = await safe_join_chat(
            client=mock_client,
            chat_link="t.me/test_private_chat",
            chat_db_id=chat_id,
            userbot_id=userbot_id,
            pool_manager=pool_manager,
            delivery_bot_token=None,
            operator_chat_id=None
        )
        
        # Verify join failed
        assert not success
        assert "ChannelPrivate" in error_msg
        
        # EXPECTED BEHAVIOR: assigned_userbot_id should be reset to NULL
        async with database.get_connection() as db:
            cursor = await db.execute(
                "SELECT assigned_userbot_id, status FROM chats WHERE id = ?",
                (chat_id,)
            )
            row = await cursor.fetchone()
            assigned_userbot_id = row[0]
            status = row[1]
            
            # This assertion will FAIL on unfixed code because assigned_userbot_id is NOT reset
            assert assigned_userbot_id is None, \
                f"Expected assigned_userbot_id to be NULL after join failure, but got {assigned_userbot_id}"
            
            # Verify chat status is updated to error
            assert status == 'error', \
                f"Expected chat status to be 'error' after join failure, but got '{status}'"
        
        # EXPECTED BEHAVIOR: Chat should be reassignable to another bot
        # (This is implicit - if assigned_userbot_id is NULL, the chat can be reassigned)
    
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


# Test 1.5: Task disappears without chat status update
@pytest.mark.asyncio
async def test_bug_1_5_task_disappears_without_chat_status_update():
    """Property 1: Bug Condition - Ghost Tasks
    
    **Validates: Requirements 1.5, 2.5**
    
    EXPECTED BEHAVIOR (what SHOULD happen after fix):
    When execute_join() fails to get a client (returns False), the chat status
    should be updated to 'error' with an appropriate error message.
    
    CURRENT BEHAVIOR (bug - this test will FAIL on unfixed code):
    The chat status is NOT updated, and the task disappears without a trace,
    leaving the chat in 'pending' status.
    
    This test demonstrates the bug by showing that when client retrieval fails,
    the chat status remains unchanged.
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
        
        # Create pool manager
        pool_manager = UserbotPoolManager()
        
        # Create session file and add userbot
        session_file = tempfile.NamedTemporaryFile(delete=False, suffix=".session")
        session_file.close()
        
        userbot_id = await pool_manager.add_userbot(session_file.name)
        
        # Create a chat
        async with database.get_connection() as db:
            cursor = await db.execute(
                """INSERT INTO chats (chat_link, status, assigned_userbot_id)
                   VALUES (?, 'pending', ?)""",
                ("t.me/test_chat", userbot_id)
            )
            chat_id = cursor.lastrowid
            await db.commit()
        
        # Verify initial chat status
        async with database.get_connection() as db:
            cursor = await db.execute(
                "SELECT status, error_message FROM chats WHERE id = ?",
                (chat_id,)
            )
            row = await cursor.fetchone()
            assert row[0] == 'pending'
            assert row[1] is None
        
        # Mock get_client to return None (simulates client get failure)
        async def mock_get_client(uid):
            return None  # Simulate client get failure
        
        pool_manager.get_client = mock_get_client
        
        # Create JoinLogic and execute join
        join_logic = JoinLogic(pool_manager)
        success = await join_logic.execute_join(userbot_id, chat_id)
        
        # Verify join failed
        assert not success
        
        # EXPECTED BEHAVIOR: Chat status should be updated to 'error'
        async with database.get_connection() as db:
            cursor = await db.execute(
                "SELECT status, error_message FROM chats WHERE id = ?",
                (chat_id,)
            )
            row = await cursor.fetchone()
            status = row[0]
            error_message = row[1]
            
            # This assertion will FAIL on unfixed code because status stays 'pending'
            assert status == 'error', \
                f"Expected chat status to be 'error' after client get failure, but got '{status}'"
            
            # This assertion will FAIL on unfixed code because error_message is NULL
            assert error_message is not None, \
                "Expected error_message to be set after client get failure, but got NULL"
            
            assert "client" in error_message.lower(), \
                f"Expected error_message to mention client failure, but got '{error_message}'"
    
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
