"""Property-based tests for Userbot Pool Manager.

**Validates: Requirements 12.3, 13.2, 16.1, 16.2, 16.3, 16.4**
"""

import asyncio
import tempfile
import os
from datetime import datetime, timedelta, timezone
from hypothesis import given, strategies as st, settings
import pytest

from src.userbot.userbot_pool_manager import (
    UserbotPoolManager,
    UserbotStatus,
    RateLimiter
)
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



# Property 23: Valid Session Adds Active Userbot
@pytest.mark.asyncio
@settings(max_examples=30, deadline=5000)
@given(
    session_filename=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), min_codepoint=65, max_codepoint=122),
        min_size=5,
        max_size=20
    ).map(lambda s: f"{s}.session")
)
async def test_property_23_valid_session_adds_active_userbot(session_filename):
    """Property 23: Valid Session Adds Active Userbot
    
    **Validates: Requirements 12.3**
    
    For any valid Telegram session file, adding it to the system must result
    in a new userbot with status "active" in the pool.
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
        
        # Create a temporary session file
        session_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".session",
            prefix=session_filename.replace(".session", "")
        )
        session_file.close()
        
        try:
            # Create pool manager
            pool_manager = UserbotPoolManager()
            
            # Add userbot
            userbot_id = await pool_manager.add_userbot(session_file.name)
            
            # Verify userbot was added with active status
            assert userbot_id > 0
            
            # Check in database
            async with database.get_connection() as db:
                cursor = await db.execute(
                    "SELECT status FROM userbots WHERE id = ?",
                    (userbot_id,)
                )
                row = await cursor.fetchone()
                assert row is not None
                assert row[0] == UserbotStatus.ACTIVE.value
            
            # Check in pool
            available = await pool_manager.get_available_userbots()
            assert any(ub.id == userbot_id for ub in available)
        
        finally:
            # Cleanup session file
            try:
                os.unlink(session_file.name)
            except:
                pass
    
    finally:
        # Cleanup database
        database.DATABASE_FILE = original_db
        try:
            os.unlink(test_db_file.name)
        except:
            pass



# Property 24: Unresponsive Userbot Marked Unavailable
@pytest.mark.asyncio
@settings(max_examples=30, deadline=10000)
@given(
    num_userbots=st.integers(min_value=1, max_value=5)
)
async def test_property_24_unresponsive_userbot_marked_unavailable(num_userbots):
    """Property 24: Unresponsive Userbot Marked Unavailable
    
    **Validates: Requirements 13.2**
    
    For any userbot that fails health check, its status must be updated
    to "unavailable".
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
        
        # Create pool manager with short health check interval
        pool_manager = UserbotPoolManager(health_check_interval=1)
        
        # Add userbots
        userbot_ids = []
        for i in range(num_userbots):
            session_file = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=".session",
                prefix=f"test_userbot_{i}_"
            )
            session_file.close()
            session_files.append(session_file.name)
            
            userbot_id = await pool_manager.add_userbot(session_file.name)
            userbot_ids.append(userbot_id)
        
        # Mock health check to fail for first userbot
        original_check = pool_manager._check_userbot_health
        
        async def mock_health_check(userbot_id):
            if userbot_id == userbot_ids[0]:
                return False  # Simulate failure
            return await original_check(userbot_id)
        
        pool_manager._check_userbot_health = mock_health_check
        
        # Run one health check cycle
        await pool_manager.start_health_check()
        await asyncio.sleep(2)  # Wait for health check to run
        await pool_manager.stop_health_check()
        
        # Verify first userbot is marked unavailable
        async with database.get_connection() as db:
            cursor = await db.execute(
                "SELECT status FROM userbots WHERE id = ?",
                (userbot_ids[0],)
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == UserbotStatus.UNAVAILABLE.value
        
        # Verify other userbots remain active
        for userbot_id in userbot_ids[1:]:
            async with database.get_connection() as db:
                cursor = await db.execute(
                    "SELECT status FROM userbots WHERE id = ?",
                    (userbot_id,)
                )
                row = await cursor.fetchone()
                assert row is not None
                assert row[0] == UserbotStatus.ACTIVE.value
    
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



# Property 29: FloodWait Suspends Userbot
@pytest.mark.asyncio
@settings(max_examples=30, deadline=5000)
@given(
    suspend_duration=st.integers(min_value=10, max_value=3600)
)
async def test_property_29_floodwait_suspends_userbot(suspend_duration):
    """Property 29: FloodWait Suspends Userbot
    
    **Validates: Requirements 16.1**
    
    For any FloodWait error received from Telegram API, the affected userbot
    must be suspended for the duration specified in the error.
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
        
        # Mark userbot as unavailable due to FloodWait
        before_time = datetime.now(timezone.utc)
        await pool_manager.mark_unavailable(userbot_id, "floodwait", suspend_duration)
        after_time = datetime.now(timezone.utc)
        
        # Verify userbot status is unavailable
        async with database.get_connection() as db:
            cursor = await db.execute(
                "SELECT status, unavailable_until FROM userbots WHERE id = ?",
                (userbot_id,)
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == UserbotStatus.UNAVAILABLE.value
            
            # Verify unavailable_until is set correctly
            unavailable_until = datetime.fromisoformat(row[1])
            expected_min = before_time + timedelta(seconds=suspend_duration)
            expected_max = after_time + timedelta(seconds=suspend_duration)
            
            assert expected_min <= unavailable_until <= expected_max
        
        # Verify userbot is not in available list
        available = await pool_manager.get_available_userbots()
        assert not any(ub.id == userbot_id for ub in available)
    
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



# Property 31: FloodWait Triggers Task Redistribution
@pytest.mark.asyncio
@settings(max_examples=20, deadline=5000)
@given(
    num_pending_tasks=st.integers(min_value=1, max_value=10)
)
async def test_property_31_floodwait_triggers_task_redistribution(num_pending_tasks):
    """Property 31: FloodWait Triggers Task Redistribution
    
    **Validates: Requirements 16.3**
    
    For any userbot suspended due to FloodWait, its pending tasks must be
    redistributed to other available userbots.
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
        
        # Create pool manager
        pool_manager = UserbotPoolManager()
        
        # Add two userbots
        for i in range(2):
            session_file = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=".session",
                prefix=f"userbot_{i}_"
            )
            session_file.close()
            session_files.append(session_file.name)
            await pool_manager.add_userbot(session_file.name)
        
        # Get userbot IDs
        async with database.get_connection() as db:
            cursor = await db.execute("SELECT id FROM userbots ORDER BY id")
            userbot_ids = [row[0] for row in await cursor.fetchall()]
        
        assert len(userbot_ids) >= 2
        suspended_userbot_id = userbot_ids[0]
        
        # Create pending tasks for first userbot
        async with database.get_connection() as db:
            for i in range(num_pending_tasks):
                # Create chat
                cursor = await db.execute(
                    """INSERT INTO chats (chat_link, status, assigned_userbot_id)
                       VALUES (?, 'pending', ?)""",
                    (f"t.me/chat_{i}", suspended_userbot_id)
                )
                chat_id = cursor.lastrowid
                
                # Create join task
                scheduled_at = datetime.now(timezone.utc) + timedelta(seconds=300 + i * 60)
                await db.execute(
                    """INSERT INTO join_tasks (userbot_id, chat_id, scheduled_at, status, created_at)
                       VALUES (?, ?, ?, 'pending', CURRENT_TIMESTAMP)""",
                    (suspended_userbot_id, chat_id, scheduled_at.isoformat())
                )
            
            await db.commit()
        
        # Mark first userbot as unavailable and redistribute tasks
        await pool_manager.mark_unavailable(suspended_userbot_id, "floodwait", 300)
        await pool_manager.redistribute_tasks(suspended_userbot_id)
        
        # Verify tasks were redistributed
        async with database.get_connection() as db:
            # Check that no pending tasks remain for suspended userbot
            cursor = await db.execute(
                """SELECT COUNT(*) FROM join_tasks 
                   WHERE userbot_id = ? AND status = 'pending'""",
                (suspended_userbot_id,)
            )
            count = (await cursor.fetchone())[0]
            assert count == 0
            
            # Check that tasks were reassigned to other userbots
            cursor = await db.execute(
                """SELECT COUNT(*) FROM join_tasks 
                   WHERE userbot_id != ? AND status = 'pending'""",
                (suspended_userbot_id,)
            )
            redistributed_count = (await cursor.fetchone())[0]
            assert redistributed_count == num_pending_tasks
    
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



# Property 32: Automatic Userbot Resumption
@pytest.mark.asyncio
@settings(max_examples=20, deadline=10000)
@given(
    suspend_duration=st.integers(min_value=1, max_value=3)
)
async def test_property_32_automatic_userbot_resumption(suspend_duration):
    """Property 32: Automatic Userbot Resumption
    
    **Validates: Requirements 16.4**
    
    For any userbot suspended due to FloodWait, its status must automatically
    return to "active" after the suspension duration expires.
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
        
        # Mark userbot as unavailable
        await pool_manager.mark_unavailable(userbot_id, "floodwait", suspend_duration)
        
        # Verify userbot is unavailable
        available = await pool_manager.get_available_userbots()
        assert not any(ub.id == userbot_id for ub in available)
        
        # Wait for suspension to expire
        await asyncio.sleep(suspend_duration + 0.5)
        
        # Check available userbots again
        available = await pool_manager.get_available_userbots()
        
        # Userbot should be automatically reactivated
        assert any(ub.id == userbot_id for ub in available)
        
        # Verify status in database
        async with database.get_connection() as db:
            cursor = await db.execute(
                "SELECT status, unavailable_until FROM userbots WHERE id = ?",
                (userbot_id,)
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == UserbotStatus.ACTIVE.value
            assert row[1] is None
    
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



# Property 30: Telegram API Rate Limiting
@pytest.mark.asyncio
@settings(max_examples=20, deadline=15000)
@given(
    num_requests=st.integers(min_value=25, max_value=50)
)
async def test_property_30_telegram_api_rate_limiting(num_requests):
    """Property 30: Telegram API Rate Limiting
    
    **Validates: Requirements 16.2**
    
    For any one-second time window, a single userbot must not make more than
    20 requests to Telegram API.
    
    Note: Token bucket allows initial burst of 20 requests, then enforces
    20 req/s rate for subsequent requests.
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
        
        # Track request times
        request_times = []
        start_time = asyncio.get_event_loop().time()
        
        # Make requests
        for i in range(num_requests):
            await pool_manager.acquire_rate_limit(userbot_id)
            request_times.append(asyncio.get_event_loop().time())
        
        end_time = asyncio.get_event_loop().time()
        total_duration = end_time - start_time
        
        # Token bucket behavior:
        # - First 20 requests use initial tokens (instant)
        # - Remaining requests wait for token refill at 20 tokens/sec
        # Expected time: (num_requests - 20) / 20 seconds
        
        if num_requests > 20:
            # Calculate expected time for requests beyond the initial burst
            extra_requests = num_requests - 20
            min_expected_duration = (extra_requests / 20.0) - 0.1  # Small tolerance
            
            assert total_duration >= min_expected_duration, \
                f"Rate limiting not working: {num_requests} requests completed in {total_duration}s (expected >= {min_expected_duration}s)"
            
            # Verify sustained rate (after initial burst) doesn't exceed 20 req/s
            # Calculate rate for requests 21 onwards
            if len(request_times) > 20:
                burst_end_time = request_times[19]  # 20th request (index 19)
                sustained_duration = end_time - burst_end_time
                sustained_requests = num_requests - 20
                
                if sustained_duration > 0:
                    sustained_rate = sustained_requests / sustained_duration
                    # Allow small tolerance for timing precision
                    assert sustained_rate <= 21.0, \
                        f"Sustained rate {sustained_rate:.2f} req/s exceeds limit of 20 req/s"
    
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


# Edge case tests
@pytest.mark.asyncio
async def test_add_userbot_invalid_session():
    """Test adding userbot with non-existent session file."""
    # Create temporary database
    test_db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    test_db_file.close()
    
    # Monkey patch the DATABASE_FILE
    original_db = database.DATABASE_FILE
    database.DATABASE_FILE = test_db_file.name
    
    try:
        # Initialize database
        await init_database()
        
        pool_manager = UserbotPoolManager()
        
        # Try to add userbot with non-existent session file
        with pytest.raises(ValueError, match="Session file not found"):
            await pool_manager.add_userbot("nonexistent.session")
    
    finally:
        # Cleanup database
        database.DATABASE_FILE = original_db
        try:
            os.unlink(test_db_file.name)
        except:
            pass


@pytest.mark.asyncio
async def test_remove_userbot():
    """Test removing a userbot from the pool."""
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
        
        pool_manager = UserbotPoolManager()
        
        # Create session file and add userbot
        session_file = tempfile.NamedTemporaryFile(delete=False, suffix=".session")
        session_file.close()
        
        userbot_id = await pool_manager.add_userbot(session_file.name)
        
        # Verify userbot is available
        available = await pool_manager.get_available_userbots()
        assert any(ub.id == userbot_id for ub in available)
        
        # Remove userbot
        await pool_manager.remove_userbot(userbot_id)
        
        # Verify userbot is no longer available
        available = await pool_manager.get_available_userbots()
        assert not any(ub.id == userbot_id for ub in available)
        
        # Verify status in database
        async with database.get_connection() as db:
            cursor = await db.execute(
                "SELECT status FROM userbots WHERE id = ?",
                (userbot_id,)
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == UserbotStatus.INACTIVE.value
    
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


@pytest.mark.asyncio
async def test_daily_join_limit():
    """Test that userbots at daily join limit are not available."""
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
        
        pool_manager = UserbotPoolManager()
        
        # Create session file and add userbot
        session_file = tempfile.NamedTemporaryFile(delete=False, suffix=".session")
        session_file.close()
        
        userbot_id = await pool_manager.add_userbot(session_file.name)
        
        # Increment joins to daily limit
        for _ in range(10):
            await pool_manager.increment_joins_today(userbot_id)
        
        # Verify userbot is not available
        available = await pool_manager.get_available_userbots()
        assert not any(ub.id == userbot_id for ub in available)
    
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
