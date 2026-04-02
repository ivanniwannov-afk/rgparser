"""Preservation property tests for Database State Management operations.

These tests verify that normal Database State Management operations work correctly
on UNFIXED code and must continue to work after the fix is implemented.

**IMPORTANT**: These tests should PASS on unfixed code to establish baseline behavior.

**Validates: Requirements 3.3, 3.4, 3.5**
"""

import asyncio
import tempfile
import os
from datetime import datetime, timedelta, timezone
from hypothesis import given, strategies as st, settings, HealthCheck
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.userbot.userbot_pool_manager import UserbotPoolManager, UserbotStatus
from src.ingestion.join_logic import JoinLogic, safe_join_chat
from database import init_database, get_connection
import database


@pytest.fixture(scope="function")
def test_db():
    """Create a temporary test database."""
    test_db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    test_db_file.close()
    
    # Monkey patch the DATABASE_FILE
    original_db = database.DATABASE_FILE
    database.DATABASE_FILE = test_db_file.name
    
    # Initialize database synchronously
    asyncio.run(init_database())
    
    yield test_db_file.name
    
    # Cleanup
    database.DATABASE_FILE = original_db
    try:
        os.unlink(test_db_file.name)
    except:
        pass


# Property 1: Successful Userbot Start Preservation
@pytest.mark.asyncio
@settings(max_examples=30, deadline=5000, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    num_userbots=st.integers(min_value=1, max_value=10)
)
async def test_property_1_successful_userbot_start_marked_active(test_db, num_userbots):
    """Property 1: Successful Userbot Start Preservation
    
    **Validates: Requirements 3.3**
    
    For all userbots that start successfully, the system SHALL mark them as 'active'
    and they SHALL be available for task assignments. This behavior must be preserved.
    
    **Expected on UNFIXED code**: PASS (confirms baseline behavior)
    """
    pool_manager = UserbotPoolManager()
    
    # Create temporary session files and add userbots
    session_files = []
    userbot_ids = []
    
    try:
        for i in range(num_userbots):
            # Create session file
            session_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{i}.session")
            session_file.close()
            session_files.append(session_file.name)
            
            # Add userbot to pool
            userbot_id = await pool_manager.add_userbot(session_file.name)
            userbot_ids.append(userbot_id)
            
            # Verify userbot is marked as 'active' in database
            async with get_connection() as db:
                cursor = await db.execute(
                    "SELECT status FROM userbots WHERE id = ?",
                    (userbot_id,)
                )
                row = await cursor.fetchone()
                status = row[0]
                
                assert status == UserbotStatus.ACTIVE.value, (
                    f"Userbot {userbot_id} should be marked 'active' after successful start, "
                    f"but got '{status}'"
                )
        
        # Verify all userbots are available for task assignments
        available = await pool_manager.get_available_userbots()
        available_ids = [ub.id for ub in available]
        
        for userbot_id in userbot_ids:
            assert userbot_id in available_ids, (
                f"Userbot {userbot_id} should be available for task assignments after successful start"
            )
        
        assert len(available) == num_userbots, (
            f"Expected {num_userbots} available userbots, got {len(available)}"
        )
    
    finally:
        # Cleanup session files
        for session_file in session_files:
            try:
                os.unlink(session_file)
            except:
                pass


# Property 2: Successful Join Updates Chat Status Preservation
@pytest.mark.asyncio
@settings(max_examples=20, deadline=20000, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    num_joins=st.integers(min_value=1, max_value=5)
)
async def test_property_2_successful_join_updates_chat_status(test_db, num_joins):
    """Property 2: Successful Join Updates Chat Status Preservation
    
    **Validates: Requirements 3.4**
    
    For all successful join operations, the system SHALL update chat status to 'active'
    and SHALL save chat_id, chat_title, and joined_at metadata.
    This behavior must be preserved.
    
    **Expected on UNFIXED code**: PASS (confirms baseline behavior)
    """
    # Create mock pool manager
    pool_manager = AsyncMock(spec=UserbotPoolManager)
    pool_manager.increment_joins_today = AsyncMock()
    pool_manager.mark_unavailable = AsyncMock()
    pool_manager.redistribute_tasks = AsyncMock()
    
    for i in range(num_joins):
        # Create mock client and chat
        mock_client = AsyncMock()
        mock_chat = MagicMock()
        mock_chat.id = 123456789 + i
        mock_chat.title = f"Test Chat {i}"
        
        # Mock successful join
        mock_client.join_chat = AsyncMock(return_value=mock_chat)
        
        # Mock get_chat_history to return NO antibot protection
        async def mock_get_chat_history(chat_id, limit):
            return
            yield  # Make it an async generator
        
        mock_client.get_chat_history = mock_get_chat_history
        
        # Create chat in database with unique link
        import time
        timestamp_suffix = int(time.time() * 1000000)
        chat_link = f"t.me/test_chat_{timestamp_suffix}_{i}"
        
        async with get_connection() as db:
            cursor = await db.execute(
                """INSERT INTO chats (chat_link, status)
                   VALUES (?, 'pending')""",
                (chat_link,)
            )
            chat_db_id = cursor.lastrowid
            await db.commit()
        
        # Record time before join
        before_join = datetime.now(timezone.utc)
        
        # Execute join
        success, error_message = await safe_join_chat(
            client=mock_client,
            chat_link=chat_link,
            chat_db_id=chat_db_id,
            userbot_id=1,
            pool_manager=pool_manager,
            delivery_bot_token=None,
            operator_chat_id=None
        )
        
        # Record time after join
        after_join = datetime.now(timezone.utc)
        
        # Verify join succeeded
        assert success is True, f"Join {i} should succeed"
        assert error_message is None, f"Join {i} should have no error message"
        
        # Verify chat status updated to 'active'
        async with get_connection() as db:
            cursor = await db.execute(
                """SELECT status, chat_id, chat_title, joined_at 
                   FROM chats WHERE id = ?""",
                (chat_db_id,)
            )
            row = await cursor.fetchone()
            
            status = row[0]
            chat_id_telegram = row[1]
            chat_title = row[2]
            joined_at_str = row[3]
            
            # Verify status is 'active'
            assert status == 'active', (
                f"Chat {i} status should be 'active' after successful join, but got '{status}'"
            )
            
            # Verify chat_id is saved
            assert chat_id_telegram == mock_chat.id, (
                f"Chat {i} chat_id should be {mock_chat.id}, but got {chat_id_telegram}"
            )
            
            # Verify chat_title is saved
            assert chat_title == mock_chat.title, (
                f"Chat {i} chat_title should be '{mock_chat.title}', but got '{chat_title}'"
            )
            
            # Verify joined_at is saved and within reasonable time range
            assert joined_at_str is not None, (
                f"Chat {i} joined_at should be set after successful join"
            )
            
            joined_at = datetime.fromisoformat(joined_at_str)
            assert before_join <= joined_at <= after_join, (
                f"Chat {i} joined_at should be between {before_join} and {after_join}, "
                f"but got {joined_at}"
            )


# Property 3: Successful Client Retrieval Proceeds with Join Preservation
@pytest.mark.asyncio
@settings(max_examples=20, deadline=20000, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    num_joins=st.integers(min_value=1, max_value=5)
)
async def test_property_3_successful_client_get_proceeds_with_join(test_db, num_joins):
    """Property 3: Successful Client Retrieval Proceeds with Join Preservation
    
    **Validates: Requirements 3.5**
    
    For all cases where client retrieval succeeds in execute_join(), the system
    SHALL proceed with the join operation. This behavior must be preserved.
    
    **Expected on UNFIXED code**: PASS (confirms baseline behavior)
    """
    pool_manager = UserbotPoolManager()
    
    # Create session file and add userbot
    session_file = tempfile.NamedTemporaryFile(delete=False, suffix=".session")
    session_file.close()
    
    try:
        userbot_id = await pool_manager.add_userbot(session_file.name)
        
        for i in range(num_joins):
            # Create chat in database with unique link
            import time
            timestamp_suffix = int(time.time() * 1000000)
            chat_link = f"t.me/test_chat_{timestamp_suffix}_{i}"
            
            async with get_connection() as db:
                cursor = await db.execute(
                    """INSERT INTO chats (chat_link, status, assigned_userbot_id)
                       VALUES (?, 'pending', ?)""",
                    (chat_link, userbot_id)
                )
                chat_id = cursor.lastrowid
                await db.commit()
            
            # Mock get_client to return a valid client
            mock_client = AsyncMock()
            mock_chat = MagicMock()
            mock_chat.id = 123456789 + i
            mock_chat.title = f"Test Chat {i}"
            
            # Mock successful join
            mock_client.join_chat = AsyncMock(return_value=mock_chat)
            
            # Mock get_chat_history to return NO antibot protection
            async def mock_get_chat_history(chat_id, limit):
                return
                yield  # Make it an async generator
            
            mock_client.get_chat_history = mock_get_chat_history
            
            # Mock pool_manager.get_client to return valid client
            async def mock_get_client(uid):
                if uid == userbot_id:
                    return mock_client
                return None
            
            pool_manager.get_client = mock_get_client
            pool_manager.increment_joins_today = AsyncMock()
            
            # Create JoinLogic and execute join
            join_logic = JoinLogic(pool_manager)
            success = await join_logic.execute_join(userbot_id, chat_id)
            
            # Verify join succeeded (client was retrieved and join proceeded)
            assert success is True, (
                f"Join {i} should succeed when client retrieval succeeds"
            )
            
            # Verify join_chat was called (join operation proceeded)
            mock_client.join_chat.assert_called_once()
            
            # Verify chat status updated to 'active'
            async with get_connection() as db:
                cursor = await db.execute(
                    "SELECT status FROM chats WHERE id = ?",
                    (chat_id,)
                )
                row = await cursor.fetchone()
                status = row[0]
                
                assert status == 'active', (
                    f"Chat {i} status should be 'active' after successful join, but got '{status}'"
                )
    
    finally:
        # Cleanup session file
        try:
            os.unlink(session_file.name)
        except:
            pass


# Concrete test cases for easier debugging

@pytest.mark.asyncio
async def test_concrete_successful_userbot_start(test_db):
    """Concrete test: Successful userbot start is marked active.
    
    **Validates: Requirements 3.3**
    """
    pool_manager = UserbotPoolManager()
    
    # Create session file
    session_file = tempfile.NamedTemporaryFile(delete=False, suffix=".session")
    session_file.close()
    
    try:
        # Add userbot
        userbot_id = await pool_manager.add_userbot(session_file.name)
        
        # Verify status is 'active'
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT status FROM userbots WHERE id = ?",
                (userbot_id,)
            )
            row = await cursor.fetchone()
            status = row[0]
            
            assert status == UserbotStatus.ACTIVE.value
        
        # Verify userbot is available for assignments
        available = await pool_manager.get_available_userbots()
        available_ids = [ub.id for ub in available]
        
        assert userbot_id in available_ids
    
    finally:
        try:
            os.unlink(session_file.name)
        except:
            pass


@pytest.mark.asyncio
async def test_concrete_successful_join_updates_status(test_db):
    """Concrete test: Successful join updates chat status to active with metadata.
    
    **Validates: Requirements 3.4**
    """
    # Create mock pool manager
    pool_manager = AsyncMock(spec=UserbotPoolManager)
    pool_manager.increment_joins_today = AsyncMock()
    
    # Create mock client and chat
    mock_client = AsyncMock()
    mock_chat = MagicMock()
    mock_chat.id = 987654321
    mock_chat.title = "Concrete Test Chat"
    
    # Mock successful join
    mock_client.join_chat = AsyncMock(return_value=mock_chat)
    
    # Mock get_chat_history to return NO antibot protection
    async def mock_get_chat_history(chat_id, limit):
        return
        yield  # Make it an async generator
    
    mock_client.get_chat_history = mock_get_chat_history
    
    # Create chat in database
    async with get_connection() as db:
        cursor = await db.execute(
            """INSERT INTO chats (chat_link, status)
               VALUES (?, 'pending')""",
            ("t.me/concrete_test_chat",)
        )
        chat_db_id = cursor.lastrowid
        await db.commit()
    
    # Execute join
    before_join = datetime.now(timezone.utc)
    
    success, error_message = await safe_join_chat(
        client=mock_client,
        chat_link="t.me/concrete_test_chat",
        chat_db_id=chat_db_id,
        userbot_id=1,
        pool_manager=pool_manager,
        delivery_bot_token=None,
        operator_chat_id=None
    )
    
    after_join = datetime.now(timezone.utc)
    
    # Verify join succeeded
    assert success is True
    assert error_message is None
    
    # Verify chat status and metadata
    async with get_connection() as db:
        cursor = await db.execute(
            """SELECT status, chat_id, chat_title, joined_at 
               FROM chats WHERE id = ?""",
            (chat_db_id,)
        )
        row = await cursor.fetchone()
        
        status = row[0]
        chat_id_telegram = row[1]
        chat_title = row[2]
        joined_at_str = row[3]
        
        assert status == 'active'
        assert chat_id_telegram == 987654321
        assert chat_title == "Concrete Test Chat"
        assert joined_at_str is not None
        
        joined_at = datetime.fromisoformat(joined_at_str)
        assert before_join <= joined_at <= after_join


@pytest.mark.asyncio
async def test_concrete_successful_client_get_proceeds(test_db):
    """Concrete test: Successful client retrieval proceeds with join.
    
    **Validates: Requirements 3.5**
    """
    pool_manager = UserbotPoolManager()
    
    # Create session file and add userbot
    session_file = tempfile.NamedTemporaryFile(delete=False, suffix=".session")
    session_file.close()
    
    try:
        userbot_id = await pool_manager.add_userbot(session_file.name)
        
        # Create chat in database
        async with get_connection() as db:
            cursor = await db.execute(
                """INSERT INTO chats (chat_link, status, assigned_userbot_id)
                   VALUES (?, 'pending', ?)""",
                ("t.me/concrete_test_chat", userbot_id)
            )
            chat_id = cursor.lastrowid
            await db.commit()
        
        # Mock get_client to return a valid client
        mock_client = AsyncMock()
        mock_chat = MagicMock()
        mock_chat.id = 111222333
        mock_chat.title = "Concrete Test Chat"
        
        # Mock successful join
        mock_client.join_chat = AsyncMock(return_value=mock_chat)
        
        # Mock get_chat_history to return NO antibot protection
        async def mock_get_chat_history(chat_id, limit):
            return
            yield  # Make it an async generator
        
        mock_client.get_chat_history = mock_get_chat_history
        
        # Mock pool_manager.get_client to return valid client
        async def mock_get_client(uid):
            if uid == userbot_id:
                return mock_client
            return None
        
        pool_manager.get_client = mock_get_client
        pool_manager.increment_joins_today = AsyncMock()
        
        # Create JoinLogic and execute join
        join_logic = JoinLogic(pool_manager)
        success = await join_logic.execute_join(userbot_id, chat_id)
        
        # Verify join succeeded
        assert success is True
        
        # Verify join_chat was called (join operation proceeded)
        mock_client.join_chat.assert_called_once()
        
        # Verify chat status updated to 'active'
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT status FROM chats WHERE id = ?",
                (chat_id,)
            )
            row = await cursor.fetchone()
            status = row[0]
            
            assert status == 'active'
    
    finally:
        try:
            os.unlink(session_file.name)
        except:
            pass
