"""Property-based tests for Ingestion Module.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2**
"""

import asyncio
import tempfile
import os
from datetime import datetime, timedelta, timezone
from hypothesis import given, strategies as st, settings, assume
import pytest
import aiosqlite

from src.ingestion.ingestion_module import IngestionModule, ValidationResult
from database import DATABASE_FILE, init_database


# Test database setup
@pytest.fixture(scope="function")
async def test_db():
    """Create a temporary test database."""
    # Use a temporary database file
    original_db = DATABASE_FILE
    test_db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    test_db_file.close()
    
    # Monkey patch the DATABASE_FILE
    import database
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


# Strategies for generating chat links
@st.composite
def valid_chat_link(draw):
    """Generate a valid Telegram chat link."""
    protocol = draw(st.sampled_from(["", "http://", "https://"]))
    prefix = draw(st.sampled_from(["t.me/", "@"]))
    
    # Valid username: alphanumeric and underscore, 1-32 chars
    username = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_"),
        min_size=1,
        max_size=32
    ))
    
    # Ensure username doesn't start with underscore (Telegram rule)
    assume(username and username[0] != '_')
    
    return f"{protocol}{prefix}{username}"


@st.composite
def invalid_chat_link(draw):
    """Generate an invalid Telegram chat link."""
    invalid_type = draw(st.sampled_from([
        "empty",
        "spaces_only",
        "invalid_chars",
        "no_prefix",
        "invalid_protocol",
        "too_short_username"
    ]))
    
    if invalid_type == "empty":
        return ""
    elif invalid_type == "spaces_only":
        return "   "
    elif invalid_type == "invalid_chars":
        # Include special characters that aren't allowed
        return f"t.me/{draw(st.text(alphabet='!@#$%^&*()', min_size=1, max_size=10))}"
    elif invalid_type == "no_prefix":
        return draw(st.text(min_size=1, max_size=20))
    elif invalid_type == "invalid_protocol":
        return f"ftp://t.me/{draw(st.text(alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')), min_size=1))}"
    else:  # too_short_username
        return "t.me/"


# Property 1: Chat Link Validation
@settings(max_examples=100)
@given(link=valid_chat_link())
def test_property_1_valid_links_accepted(link):
    """Property 1: Chat Link Validation - Valid Links
    
    **Validates: Requirements 1.2**
    
    For any string matching the format ^(https?://)?(t.me/|@)[\w\d_]+$,
    the system must accept it as a valid chat link.
    """
    module = IngestionModule()
    assert module.validate_chat_link(link) is True


@settings(max_examples=100)
@given(link=invalid_chat_link())
def test_property_1_invalid_links_rejected(link):
    """Property 1: Chat Link Validation - Invalid Links
    
    **Validates: Requirements 1.2**
    
    For any string NOT matching the format ^(https?://)?(t.me/|@)[\w\d_]+$,
    the system must reject it as an invalid chat link.
    """
    module = IngestionModule()
    assert module.validate_chat_link(link) is False


# Property 2: Saved Chats Have Pending Status
@pytest.mark.asyncio
@settings(max_examples=50, deadline=5000)
@given(links=st.lists(valid_chat_link(), min_size=1, max_size=10, unique=True))
async def test_property_2_saved_chats_pending_status(links):
    """Property 2: Saved Chats Have Pending Status
    
    **Validates: Requirements 1.4**
    
    For any list of valid chat links, after saving to the database,
    all chats must have status "pending".
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
        
        # Create module and accept chat list
        module = IngestionModule()
        result = await module.accept_chat_list(links)
        
        # Verify all links were accepted
        assert result.is_valid
        assert len(result.valid_chats) == len(links)
        
        # Check database for pending status
        async with database.get_connection() as db:
            cursor = await db.execute(
                "SELECT chat_link, status FROM chats WHERE chat_link IN ({})".format(
                    ','.join('?' * len(links))
                ),
                links
            )
            rows = await cursor.fetchall()
            
            # All chats must have pending status
            assert len(rows) == len(links)
            for chat_link, status in rows:
                assert status == "pending", f"Chat {chat_link} has status {status}, expected 'pending'"
    
    finally:
        # Cleanup
        database.DATABASE_FILE = original_db
        try:
            os.unlink(test_db_file.name)
        except:
            pass


# Property 3: All Chats Are Distributed
@pytest.mark.asyncio
@settings(max_examples=30, deadline=5000)
@given(
    num_chats=st.integers(min_value=1, max_value=20),
    num_userbots=st.integers(min_value=1, max_value=5)
)
async def test_property_3_all_chats_distributed(num_chats, num_userbots):
    """Property 3: All Chats Are Distributed
    
    **Validates: Requirements 2.1**
    
    For any non-empty list of chats and non-empty pool of available userbots,
    after distribution every chat must be assigned to exactly one userbot.
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
        
        # Create userbots
        async with database.get_connection() as db:
            userbot_ids = []
            for i in range(num_userbots):
                cursor = await db.execute(
                    """INSERT INTO userbots (session_file, status, joins_today, joins_reset_at)
                       VALUES (?, 'active', 0, ?)""",
                    (f"session_{i}.session", (datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
                )
                userbot_ids.append(cursor.lastrowid)
            
            # Create chats
            chat_ids = []
            for i in range(num_chats):
                cursor = await db.execute(
                    """INSERT INTO chats (chat_link, status)
                       VALUES (?, 'pending')""",
                    (f"t.me/chat_{i}",)
                )
                chat_ids.append(cursor.lastrowid)
            
            await db.commit()
        
        # Distribute chats
        module = IngestionModule()
        distribution = await module.distribute_chats(chat_ids)
        
        # Verify all chats are distributed
        distributed_chats = []
        for userbot_id, assigned_chats in distribution.items():
            distributed_chats.extend(assigned_chats)
        
        # Check that we distributed as many as possible (limited by daily limit)
        max_possible = min(num_chats, num_userbots * module.daily_join_limit)
        assert len(distributed_chats) == max_possible
        
        # Check each chat is assigned exactly once
        assert len(distributed_chats) == len(set(distributed_chats))
        
        # Verify in database
        async with database.get_connection() as db:
            for chat_id in distributed_chats:
                cursor = await db.execute(
                    "SELECT assigned_userbot_id FROM chats WHERE id = ?",
                    (chat_id,)
                )
                row = await cursor.fetchone()
                assert row is not None
                assert row[0] is not None, f"Chat {chat_id} was not assigned to any userbot"
    
    finally:
        # Cleanup
        database.DATABASE_FILE = original_db
        try:
            os.unlink(test_db_file.name)
        except:
            pass


# Property 4: Load Balancing
@pytest.mark.asyncio
@settings(max_examples=30, deadline=5000)
@given(
    num_chats=st.integers(min_value=2, max_value=20),
    num_userbots=st.integers(min_value=2, max_value=5)
)
async def test_property_4_load_balancing(num_chats, num_userbots):
    """Property 4: Load Balancing
    
    **Validates: Requirements 2.2**
    
    For any distribution of chats among userbots, the difference between
    the maximum and minimum number of chats assigned to any two userbots
    should not exceed 1 (when possible).
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
        
        # Create userbots
        async with database.get_connection() as db:
            userbot_ids = []
            for i in range(num_userbots):
                cursor = await db.execute(
                    """INSERT INTO userbots (session_file, status, joins_today, joins_reset_at)
                       VALUES (?, 'active', 0, ?)""",
                    (f"session_{i}.session", (datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
                )
                userbot_ids.append(cursor.lastrowid)
            
            # Create chats
            chat_ids = []
            for i in range(num_chats):
                cursor = await db.execute(
                    """INSERT INTO chats (chat_link, status)
                       VALUES (?, 'pending')""",
                    (f"t.me/chat_{i}",)
                )
                chat_ids.append(cursor.lastrowid)
            
            await db.commit()
        
        # Distribute chats
        module = IngestionModule()
        distribution = await module.distribute_chats(chat_ids)
        
        # Get assignment counts
        if distribution:
            assignment_counts = [len(chats) for chats in distribution.values()]
            
            # Check load balance (max - min <= 1)
            if len(assignment_counts) > 1:
                max_count = max(assignment_counts)
                min_count = min(assignment_counts)
                assert max_count - min_count <= 1, \
                    f"Load imbalance: max={max_count}, min={min_count}, diff={max_count - min_count}"
    
    finally:
        # Cleanup
        database.DATABASE_FILE = original_db
        try:
            os.unlink(test_db_file.name)
        except:
            pass


# Property 5: Daily Join Limit Enforcement
@pytest.mark.asyncio
@settings(max_examples=20, deadline=5000)
@given(
    num_chats=st.integers(min_value=15, max_value=30),
    daily_limit=st.integers(min_value=5, max_value=10)
)
async def test_property_5_daily_join_limit(num_chats, daily_limit):
    """Property 5: Daily Join Limit Enforcement
    
    **Validates: Requirements 2.3, 2.4**
    
    For any userbot, the number of join tasks assigned to it within
    a 24-hour period must not exceed the configured daily limit.
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
        
        # Create userbots
        async with database.get_connection() as db:
            userbot_ids = []
            for i in range(3):  # 3 userbots
                cursor = await db.execute(
                    """INSERT INTO userbots (session_file, status, joins_today, joins_reset_at)
                       VALUES (?, 'active', 0, ?)""",
                    (f"session_{i}.session", (datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
                )
                userbot_ids.append(cursor.lastrowid)
            
            # Create chats
            chat_ids = []
            for i in range(num_chats):
                cursor = await db.execute(
                    """INSERT INTO chats (chat_link, status)
                       VALUES (?, 'pending')""",
                    (f"t.me/chat_{i}",)
                )
                chat_ids.append(cursor.lastrowid)
            
            await db.commit()
        
        # Distribute chats with custom daily limit
        module = IngestionModule(daily_join_limit=daily_limit)
        distribution = await module.distribute_chats(chat_ids)
        
        # Verify no userbot exceeds daily limit
        for userbot_id, assigned_chats in distribution.items():
            assert len(assigned_chats) <= daily_limit, \
                f"Userbot {userbot_id} assigned {len(assigned_chats)} chats, exceeds limit {daily_limit}"
    
    finally:
        # Cleanup
        database.DATABASE_FILE = original_db
        try:
            os.unlink(test_db_file.name)
        except:
            pass



# Property 6: Join Task Delay Range
@pytest.mark.asyncio
@settings(max_examples=30, deadline=5000)
@given(
    num_chats=st.integers(min_value=2, max_value=10),
    delay_min=st.integers(min_value=60, max_value=300),
    delay_max=st.integers(min_value=301, max_value=1800)
)
async def test_property_6_join_task_delay_range(num_chats, delay_min, delay_max):
    """Property 6: Join Task Delay Range
    
    **Validates: Requirements 3.1**
    
    For any two consecutive join tasks assigned to the same userbot,
    the difference between their scheduled times must be between
    join_delay_min and join_delay_max seconds.
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
        
        # Create one userbot
        async with database.get_connection() as db:
            cursor = await db.execute(
                """INSERT INTO userbots (session_file, status, joins_today, joins_reset_at)
                   VALUES (?, 'active', 0, ?)""",
                ("session_0.session", (datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
            )
            userbot_id = cursor.lastrowid
            
            # Create chats
            chat_ids = []
            for i in range(num_chats):
                cursor = await db.execute(
                    """INSERT INTO chats (chat_link, status, assigned_userbot_id)
                       VALUES (?, 'pending', ?)""",
                    (f"t.me/chat_{i}", userbot_id)
                )
                chat_ids.append(cursor.lastrowid)
            
            await db.commit()
        
        # Create join tasks with custom delays
        module = IngestionModule(join_delay_min=delay_min, join_delay_max=delay_max)
        distribution = {userbot_id: chat_ids}
        await module.enqueue_join_tasks(distribution)
        
        # Verify delays are within range
        async with database.get_connection() as db:
            cursor = await db.execute(
                """SELECT scheduled_at FROM join_tasks
                   WHERE userbot_id = ?
                   ORDER BY scheduled_at ASC""",
                (userbot_id,)
            )
            rows = await cursor.fetchall()
            
            scheduled_times = [datetime.fromisoformat(row[0]) for row in rows]
            
            # Check consecutive delays
            for i in range(1, len(scheduled_times)):
                delay = (scheduled_times[i] - scheduled_times[i-1]).total_seconds()
                assert delay_min <= delay <= delay_max, \
                    f"Delay {delay}s not in range [{delay_min}, {delay_max}]"
    
    finally:
        # Cleanup
        database.DATABASE_FILE = original_db
        try:
            os.unlink(test_db_file.name)
        except:
            pass


# Property 7: Join Tasks Have Scheduled Time
@pytest.mark.asyncio
@settings(max_examples=30, deadline=5000)
@given(num_chats=st.integers(min_value=1, max_value=10))
async def test_property_7_join_tasks_have_scheduled_time(num_chats):
    """Property 7: Join Tasks Have Scheduled Time
    
    **Validates: Requirements 3.2**
    
    For any created join task, it must have a non-null scheduled_at
    timestamp that is in the future relative to creation time.
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
        
        # Record creation time
        creation_time = datetime.now(timezone.utc)
        
        # Create one userbot
        async with database.get_connection() as db:
            cursor = await db.execute(
                """INSERT INTO userbots (session_file, status, joins_today, joins_reset_at)
                   VALUES (?, 'active', 0, ?)""",
                ("session_0.session", (datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
            )
            userbot_id = cursor.lastrowid
            
            # Create chats
            chat_ids = []
            for i in range(num_chats):
                cursor = await db.execute(
                    """INSERT INTO chats (chat_link, status, assigned_userbot_id)
                       VALUES (?, 'pending', ?)""",
                    (f"t.me/chat_{i}", userbot_id)
                )
                chat_ids.append(cursor.lastrowid)
            
            await db.commit()
        
        # Create join tasks
        module = IngestionModule()
        distribution = {userbot_id: chat_ids}
        await module.enqueue_join_tasks(distribution)
        
        # Verify all tasks have future scheduled times
        async with database.get_connection() as db:
            cursor = await db.execute(
                """SELECT id, scheduled_at FROM join_tasks
                   WHERE userbot_id = ?""",
                (userbot_id,)
            )
            rows = await cursor.fetchall()
            
            assert len(rows) == num_chats
            
            for task_id, scheduled_at in rows:
                assert scheduled_at is not None, f"Task {task_id} has null scheduled_at"
                
                scheduled_time = datetime.fromisoformat(scheduled_at)
                assert scheduled_time > creation_time, \
                    f"Task {task_id} scheduled_at {scheduled_time} is not in the future"
    
    finally:
        # Cleanup
        database.DATABASE_FILE = original_db
        try:
            os.unlink(test_db_file.name)
        except:
            pass


# Additional edge case tests
def test_validate_chat_link_edge_cases():
    """Test edge cases for chat link validation."""
    module = IngestionModule()
    
    # None and empty
    assert module.validate_chat_link(None) is False
    assert module.validate_chat_link("") is False
    
    # Whitespace
    assert module.validate_chat_link("   ") is False
    
    # Valid formats
    assert module.validate_chat_link("t.me/testchat") is True
    assert module.validate_chat_link("@testchat") is True
    assert module.validate_chat_link("http://t.me/testchat") is True
    assert module.validate_chat_link("https://t.me/testchat") is True
    
    # Invalid formats
    assert module.validate_chat_link("t.me/") is False
    assert module.validate_chat_link("t.me/ ") is False
    assert module.validate_chat_link("ftp://t.me/test") is False
    assert module.validate_chat_link("t.me/test chat") is False
    assert module.validate_chat_link("t.me/test@chat") is False


@pytest.mark.asyncio
async def test_accept_chat_list_empty():
    """Test accepting an empty chat list."""
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
        
        module = IngestionModule()
        result = await module.accept_chat_list([])
        
        assert result.is_valid
        assert len(result.valid_chats) == 0
        assert len(result.invalid_chats) == 0
    
    finally:
        # Cleanup
        database.DATABASE_FILE = original_db
        try:
            os.unlink(test_db_file.name)
        except:
            pass


@pytest.mark.asyncio
async def test_distribute_chats_empty():
    """Test distributing an empty chat list."""
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
        
        module = IngestionModule()
        distribution = await module.distribute_chats([])
        
        assert distribution == {}
    
    finally:
        # Cleanup
        database.DATABASE_FILE = original_db
        try:
            os.unlink(test_db_file.name)
        except:
            pass


@pytest.mark.asyncio
async def test_distribute_chats_no_userbots():
    """Test distributing chats when no userbots are available."""
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
        
        # Create a chat without any userbots
        async with database.get_connection() as db:
            cursor = await db.execute(
                """INSERT INTO chats (chat_link, status)
                   VALUES (?, 'pending')""",
                ("t.me/test",)
            )
            chat_id = cursor.lastrowid
            await db.commit()
        
        module = IngestionModule()
        
        # Should raise ValueError
        with pytest.raises(ValueError, match="No available userbots"):
            await module.distribute_chats([chat_id])
    
    finally:
        # Cleanup
        database.DATABASE_FILE = original_db
        try:
            os.unlink(test_db_file.name)
        except:
            pass
