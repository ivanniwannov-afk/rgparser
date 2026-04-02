"""Preservation property tests for SQLite operations.

These tests verify that normal SQLite operations work correctly on UNFIXED code
and must continue to work after the concurrency fixes are implemented.

**IMPORTANT**: These tests should PASS on unfixed code to establish baseline behavior.

**Validates: Requirements 3.6, 3.7, 3.8, 3.9**
"""

import asyncio
import tempfile
import os
import hashlib
from datetime import datetime, timedelta, timezone
from hypothesis import given, strategies as st, settings, HealthCheck
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.userbot.userbot_pool_manager import UserbotPoolManager, UserbotStatus
from src.ingestion.ingestion_module import IngestionModule
from src.parser.message_parser import MessageParser, normalize_text
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


# Property 1: Single Userbot Writing Leads Preservation
@pytest.mark.asyncio
@settings(max_examples=20, deadline=10000, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    num_messages=st.integers(min_value=1, max_value=10),
    message_text=st.text(min_size=10, max_size=100)
)
async def test_property_1_single_userbot_writes_leads_without_errors(test_db, num_messages, message_text):
    """Property 1: Single Userbot Writing Leads Preservation
    
    **Validates: Requirements 3.6**
    
    For all single-threaded write operations by one userbot, the system SHALL
    complete writes without "database is locked" errors. This behavior must be preserved.
    
    **Expected on UNFIXED code**: PASS (confirms baseline behavior)
    """
    # Create a mock callback
    messages_received = []
    
    async def on_message_callback(message):
        messages_received.append(message)
    
    # Patch the DATABASE_FILE in message_parser module
    import src.parser.message_parser as mp
    original_db = mp.DATABASE_FILE
    mp.DATABASE_FILE = test_db
    
    try:
        # Create message parser
        parser = MessageParser(trigger_words=["test"], on_message_callback=on_message_callback)
        
        # Subscribe to a test chat
        test_chat_id = 123456789
        await parser.subscribe_to_chat(test_chat_id)
        
        # Write message hashes sequentially (single-threaded)
        written_hashes = []
        for i in range(num_messages):
            text = f"{message_text}_{i}"
            
            # Deduplicate should write to database without errors
            # Note: We don't check if it's duplicate because the hash might exist from previous runs
            # The key is that the operation completes without "database is locked" error
            try:
                is_duplicate = await parser.deduplicate(text)
                # Operation succeeded without database lock error
            except Exception as e:
                if "database is locked" in str(e):
                    pytest.fail(f"Database locked error on single-threaded write: {e}")
                raise
            
            # Verify hash was written to database
            normalized = normalize_text(text)
            msg_hash = hashlib.sha256(normalized.encode()).hexdigest()
            written_hashes.append(msg_hash)
            
            async with get_connection() as db:
                cursor = await db.execute(
                    "SELECT hash FROM message_hashes WHERE hash = ?",
                    (msg_hash,)
                )
                row = await cursor.fetchone()
                
                assert row is not None, (
                    f"Message hash should be written to database"
                )
                assert row[0] == msg_hash, (
                    f"Hash should match: expected {msg_hash}, got {row[0]}"
                )
    finally:
        mp.DATABASE_FILE = original_db


# Property 2: First-Time Userbot Insert Preservation
@pytest.mark.asyncio
@settings(max_examples=20, deadline=10000, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    num_userbots=st.integers(min_value=1, max_value=5)
)
async def test_property_2_first_time_userbot_insert_without_errors(test_db, num_userbots):
    """Property 2: First-Time Userbot Insert Preservation
    
    **Validates: Requirements 3.7**
    
    For all first-time system startup operations inserting userbots, the system SHALL
    create records without IntegrityError. This behavior must be preserved.
    
    **Expected on UNFIXED code**: PASS (confirms baseline behavior)
    """
    pool_manager = UserbotPoolManager()
    
    session_files = []
    userbot_ids = []
    
    try:
        # First-time insert: create new userbots
        for i in range(num_userbots):
            # Create unique session file
            session_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_first_{i}.session")
            session_file.close()
            session_files.append(session_file.name)
            
            # Add userbot (first-time insert)
            userbot_id = await pool_manager.add_userbot(session_file.name)
            userbot_ids.append(userbot_id)
            
            # Verify userbot was created
            async with get_connection() as db:
                cursor = await db.execute(
                    "SELECT id, session_file, status FROM userbots WHERE id = ?",
                    (userbot_id,)
                )
                row = await cursor.fetchone()
                
                assert row is not None, (
                    f"Userbot {userbot_id} should exist in database"
                )
                assert row[0] == userbot_id, (
                    f"Userbot ID should match: expected {userbot_id}, got {row[0]}"
                )
                assert row[1] == session_file.name, (
                    f"Session file should match: expected {session_file.name}, got {row[1]}"
                )
                assert row[2] == UserbotStatus.ACTIVE.value, (
                    f"Status should be 'active', got {row[2]}"
                )
        
        # Verify all userbots were created
        assert len(userbot_ids) == num_userbots, (
            f"Expected {num_userbots} userbots, got {len(userbot_ids)}"
        )
    
    finally:
        # Cleanup session files
        for session_file in session_files:
            try:
                os.unlink(session_file)
            except:
                pass


# Property 3: Sequential Task Creation Linkage Preservation
@pytest.mark.asyncio
@settings(max_examples=20, deadline=15000, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    num_chats=st.integers(min_value=1, max_value=5)
)
async def test_property_3_sequential_task_creation_links_correctly(test_db, num_chats):
    """Property 3: Sequential Task Creation Linkage Preservation
    
    **Validates: Requirements 3.8**
    
    For all sequential task creation operations, the system SHALL correctly link
    tasks to their corresponding chats. This behavior must be preserved.
    
    **Expected on UNFIXED code**: PASS (confirms baseline behavior)
    """
    # Create ingestion module
    ingestion = IngestionModule(join_delay_min=5, join_delay_max=10, daily_join_limit=10)
    
    # Create a userbot
    pool_manager = UserbotPoolManager()
    session_file = tempfile.NamedTemporaryFile(delete=False, suffix=".session")
    session_file.close()
    
    try:
        userbot_id = await pool_manager.add_userbot(session_file.name)
        
        # Create chats and distribute them
        chat_ids = []
        for i in range(num_chats):
            import time
            timestamp_suffix = int(time.time() * 1000000)
            chat_link = f"t.me/test_chat_{timestamp_suffix}_{i}"
            
            async with get_connection() as db:
                cursor = await db.execute(
                    """INSERT INTO chats (chat_link, status)
                       VALUES (?, 'pending')""",
                    (chat_link,)
                )
                chat_id = cursor.lastrowid
                chat_ids.append(chat_id)
                await db.commit()
        
        # Distribute chats to userbot
        distribution = await ingestion.distribute_chats(chat_ids)
        
        # Enqueue join tasks sequentially
        await ingestion.enqueue_join_tasks(distribution)
        
        # Verify each task is correctly linked to its chat
        for chat_id in chat_ids:
            async with get_connection() as db:
                cursor = await db.execute(
                    """SELECT id, userbot_id, chat_id, status
                       FROM join_tasks
                       WHERE chat_id = ?
                       ORDER BY id DESC
                       LIMIT 1""",
                    (chat_id,)
                )
                row = await cursor.fetchone()
                
                assert row is not None, (
                    f"Task for chat {chat_id} should exist"
                )
                
                task_id = row[0]
                task_userbot_id = row[1]
                task_chat_id = row[2]
                task_status = row[3]
                
                assert task_chat_id == chat_id, (
                    f"Task should be linked to chat {chat_id}, but got {task_chat_id}"
                )
                # Verify task is assigned to one of the available userbots
                # (in this case, we only have one userbot, so it should be assigned to it)
                assert task_userbot_id in distribution, (
                    f"Task should be assigned to an available userbot, but got {task_userbot_id}"
                )
                assert task_status == 'pending', (
                    f"Task status should be 'pending', got {task_status}"
                )
    
    finally:
        try:
            os.unlink(session_file.name)
        except:
            pass


# Property 4: Non-Captcha Notification Delivery Preservation
@pytest.mark.asyncio
@settings(max_examples=10, deadline=10000, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    num_logs=st.integers(min_value=1, max_value=10)
)
async def test_property_4_non_captcha_notifications_deliver_successfully(test_db, num_logs):
    """Property 4: Non-Captcha Notification Delivery Preservation
    
    **Validates: Requirements 3.9**
    
    For all non-captcha notification operations (activity logging), the system SHALL
    successfully write to the database through existing mechanisms.
    This behavior must be preserved.
    
    **Expected on UNFIXED code**: PASS (confirms baseline behavior)
    """
    # Write activity logs (non-captcha notifications)
    for i in range(num_logs):
        component = f"TestComponent_{i}"
        level = "INFO"
        message = f"Test message {i}"
        metadata = {"test_key": f"test_value_{i}"}
        
        # Write activity log
        import json
        async with get_connection() as db:
            await db.execute(
                """INSERT INTO activity_logs (component, level, message, metadata, created_at)
                   VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                (component, level, message, json.dumps(metadata))
            )
            await db.commit()
        
        # Verify log was written
        async with get_connection() as db:
            cursor = await db.execute(
                """SELECT component, level, message, metadata
                   FROM activity_logs
                   WHERE component = ? AND message = ?""",
                (component, message)
            )
            row = await cursor.fetchone()
            
            assert row is not None, (
                f"Activity log {i} should be written to database"
            )
            assert row[0] == component, (
                f"Component should match: expected {component}, got {row[0]}"
            )
            assert row[1] == level, (
                f"Level should match: expected {level}, got {row[1]}"
            )
            assert row[2] == message, (
                f"Message should match: expected {message}, got {row[2]}"
            )
            
            stored_metadata = json.loads(row[3])
            assert stored_metadata == metadata, (
                f"Metadata should match: expected {metadata}, got {stored_metadata}"
            )


# Concrete test cases for easier debugging

@pytest.mark.asyncio
async def test_concrete_single_userbot_writes_lead(test_db):
    """Concrete test: Single userbot writes lead without errors.
    
    **Validates: Requirements 3.6**
    """
    # Patch the DATABASE_FILE in message_parser module
    import src.parser.message_parser as mp
    original_db = mp.DATABASE_FILE
    mp.DATABASE_FILE = test_db
    
    try:
        # Create message parser
        async def on_message_callback(message):
            pass
        
        parser = MessageParser(trigger_words=["test"], on_message_callback=on_message_callback)
        
        # Write a message hash with unique text
        import time
        text = f"This is a test message for lead writing {time.time()}"
        
        try:
            is_duplicate = await parser.deduplicate(text)
            # Operation succeeded without database lock error
        except Exception as e:
            if "database is locked" in str(e):
                pytest.fail(f"Database locked error on single-threaded write: {e}")
            raise
        
        # Verify hash was written
        normalized = normalize_text(text)
        msg_hash = hashlib.sha256(normalized.encode()).hexdigest()
        
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT hash FROM message_hashes WHERE hash = ?",
                (msg_hash,)
            )
            row = await cursor.fetchone()
            
            assert row is not None
            assert row[0] == msg_hash
    finally:
        mp.DATABASE_FILE = original_db


@pytest.mark.asyncio
async def test_concrete_first_time_userbot_insert(test_db):
    """Concrete test: First-time userbot insert creates record without errors.
    
    **Validates: Requirements 3.7**
    """
    pool_manager = UserbotPoolManager()
    
    # Create session file
    session_file = tempfile.NamedTemporaryFile(delete=False, suffix=".session")
    session_file.close()
    
    try:
        # First-time insert
        userbot_id = await pool_manager.add_userbot(session_file.name)
        
        # Verify userbot was created
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT id, session_file, status FROM userbots WHERE id = ?",
                (userbot_id,)
            )
            row = await cursor.fetchone()
            
            assert row is not None
            assert row[0] == userbot_id
            assert row[1] == session_file.name
            assert row[2] == UserbotStatus.ACTIVE.value
    
    finally:
        try:
            os.unlink(session_file.name)
        except:
            pass


@pytest.mark.asyncio
async def test_concrete_sequential_task_creation_links(test_db):
    """Concrete test: Sequential task creation links tasks to chats correctly.
    
    **Validates: Requirements 3.8**
    """
    # Create ingestion module
    ingestion = IngestionModule(join_delay_min=5, join_delay_max=10, daily_join_limit=10)
    
    # Create a userbot
    pool_manager = UserbotPoolManager()
    session_file = tempfile.NamedTemporaryFile(delete=False, suffix=".session")
    session_file.close()
    
    try:
        userbot_id = await pool_manager.add_userbot(session_file.name)
        
        # Create a chat
        async with get_connection() as db:
            cursor = await db.execute(
                """INSERT INTO chats (chat_link, status)
                   VALUES (?, 'pending')""",
                ("t.me/test_chat_concrete",)
            )
            chat_id = cursor.lastrowid
            await db.commit()
        
        # Distribute and enqueue
        distribution = await ingestion.distribute_chats([chat_id])
        await ingestion.enqueue_join_tasks(distribution)
        
        # Verify task is linked to chat
        async with get_connection() as db:
            cursor = await db.execute(
                """SELECT id, userbot_id, chat_id, status
                   FROM join_tasks
                   WHERE chat_id = ?""",
                (chat_id,)
            )
            row = await cursor.fetchone()
            
            assert row is not None
            assert row[2] == chat_id  # task_chat_id
            assert row[1] == userbot_id  # task_userbot_id
            assert row[3] == 'pending'  # task_status
    
    finally:
        try:
            os.unlink(session_file.name)
        except:
            pass


@pytest.mark.asyncio
async def test_concrete_non_captcha_notification_delivery(test_db):
    """Concrete test: Non-captcha notification (activity log) delivers successfully.
    
    **Validates: Requirements 3.9**
    """
    import json
    
    # Write activity log
    component = "ConcreteTestComponent"
    level = "INFO"
    message = "Concrete test message"
    metadata = {"key": "value"}
    
    async with get_connection() as db:
        await db.execute(
            """INSERT INTO activity_logs (component, level, message, metadata, created_at)
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (component, level, message, json.dumps(metadata))
        )
        await db.commit()
    
    # Verify log was written
    async with get_connection() as db:
        cursor = await db.execute(
            """SELECT component, level, message, metadata
               FROM activity_logs
               WHERE component = ? AND message = ?""",
            (component, message)
        )
        row = await cursor.fetchone()
        
        assert row is not None
        assert row[0] == component
        assert row[1] == level
        assert row[2] == message
        
        stored_metadata = json.loads(row[3])
        assert stored_metadata == metadata
