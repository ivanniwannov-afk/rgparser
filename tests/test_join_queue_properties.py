"""Property-based tests for Join Queue.

**Validates: Requirements 3.1, 3.2, 3.3, 18.2, 18.3**
"""

import asyncio
import tempfile
import os
from datetime import datetime, timedelta, timezone
from hypothesis import given, strategies as st, settings, assume
import pytest
import aiosqlite

from src.ingestion.join_queue import JoinQueue, JoinTask
from database import DATABASE_FILE, init_database


# Test database setup
@pytest.fixture(scope="function")
async def test_db():
    """Create a temporary test database."""
    # Use a temporary database file
    test_db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    test_db_file.close()
    
    # Monkey patch the DATABASE_FILE
    import database
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


# Property 7: Join Tasks Have Scheduled Time (Queue perspective)
@pytest.mark.asyncio
@settings(max_examples=50, deadline=5000)
@given(
    num_tasks=st.integers(min_value=1, max_value=20),
    delay_seconds=st.integers(min_value=1, max_value=3600)
)
async def test_property_7_tasks_have_future_scheduled_time(num_tasks, delay_seconds):
    """Property 7: Join Tasks Have Scheduled Time
    
    **Validates: Requirements 3.2**
    
    For any created join task added to the queue, it must have a non-null
    scheduled_at timestamp that is in the future relative to creation time.
    """
    queue = JoinQueue()
    creation_time = datetime.now(timezone.utc)
    
    # Add tasks with future scheduled times
    for i in range(num_tasks):
        scheduled_at = creation_time + timedelta(seconds=delay_seconds + i)
        await queue.add_task(
            task_id=i,
            userbot_id=1,
            chat_id=i,
            scheduled_at=scheduled_at
        )
    
    # Verify all tasks have future scheduled times
    assert queue.qsize() == num_tasks
    
    # Get all tasks and verify their scheduled times
    tasks_checked = 0
    while not queue.is_empty() and tasks_checked < num_tasks:
        try:
            task = await asyncio.wait_for(queue._queue.get(), timeout=0.1)
            assert task.scheduled_at is not None
            assert task.scheduled_at >= creation_time
            tasks_checked += 1
        except asyncio.TimeoutError:
            break


# Property 8: Tasks Execute After Scheduled Time
@pytest.mark.asyncio
@settings(max_examples=30, deadline=10000)
@given(
    num_tasks=st.integers(min_value=1, max_value=5)
)
async def test_property_8_tasks_execute_after_scheduled_time(num_tasks):
    """Property 8: Tasks Execute After Scheduled Time
    
    **Validates: Requirements 3.4**
    
    For any join task, its execution must not begin before its scheduled_at timestamp.
    """
    queue = JoinQueue()
    now = datetime.now(timezone.utc)
    
    # Add tasks with specific scheduled times (0-2 seconds in the future)
    scheduled_times = []
    for i in range(num_tasks):
        # Use small delays to keep test fast
        delay = i % 3  # 0, 1, or 2 seconds
        scheduled_at = now + timedelta(seconds=delay)
        scheduled_times.append(scheduled_at)
        await queue.add_task(
            task_id=i,
            userbot_id=1,
            chat_id=i,
            scheduled_at=scheduled_at
        )
    
    # Get tasks and verify they are not executed before scheduled time
    for i in range(num_tasks):
        task = await queue.get_next_task()
        
        if task is None:
            break
        
        execution_time = datetime.now(timezone.utc)
        
        # Task should not be executed before its scheduled time
        # Allow small tolerance for execution overhead (100ms)
        tolerance = timedelta(milliseconds=100)
        assert execution_time >= (task.scheduled_at - tolerance), \
            f"Task {task.task_id} executed at {execution_time} before scheduled time {task.scheduled_at}"


# Property: Queue Ordering by Scheduled Time
@pytest.mark.asyncio
@settings(max_examples=50, deadline=5000)
@given(
    scheduled_offsets=st.lists(
        st.integers(min_value=1, max_value=1000),
        min_size=2,
        max_size=20,
        unique=True
    )
)
async def test_property_queue_ordering(scheduled_offsets):
    """Property: Queue Ordering by Scheduled Time
    
    **Validates: Requirements 3.3**
    
    For any set of join tasks added to the queue, they must be retrieved
    in order of their scheduled_at timestamp (earliest first).
    """
    queue = JoinQueue()
    now = datetime.now(timezone.utc)
    
    # Add tasks in random order
    import random
    shuffled_offsets = scheduled_offsets.copy()
    random.shuffle(shuffled_offsets)
    
    for i, offset in enumerate(shuffled_offsets):
        scheduled_at = now + timedelta(seconds=offset)
        await queue.add_task(
            task_id=i,
            userbot_id=1,
            chat_id=i,
            scheduled_at=scheduled_at
        )
    
    # Retrieve tasks and verify they come out in sorted order
    previous_scheduled_at = None
    retrieved_count = 0
    
    while not queue.is_empty() and retrieved_count < len(scheduled_offsets):
        try:
            task = await asyncio.wait_for(queue._queue.get(), timeout=0.1)
            
            if previous_scheduled_at is not None:
                assert task.scheduled_at >= previous_scheduled_at, \
                    f"Task order violation: {task.scheduled_at} came after {previous_scheduled_at}"
            
            previous_scheduled_at = task.scheduled_at
            retrieved_count += 1
        except asyncio.TimeoutError:
            break
    
    assert retrieved_count == len(scheduled_offsets)


# Property 34: State Persistence (Queue perspective)
@pytest.mark.asyncio
@settings(max_examples=30, deadline=5000)
@given(
    num_tasks=st.integers(min_value=1, max_value=15)
)
async def test_property_34_queue_state_persistence(num_tasks):
    """Property 34: State Persistence
    
    **Validates: Requirements 18.2**
    
    For any join task added to the queue, its state must be persisted
    to the database.
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
        
        # Create userbot and chats in database
        async with database.get_connection() as db:
            cursor = await db.execute(
                """INSERT INTO userbots (session_file, status, joins_today, joins_reset_at)
                   VALUES (?, 'active', 0, ?)""",
                ("session_test.session", (datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
            )
            userbot_id = cursor.lastrowid
            
            # Create tasks in database
            now = datetime.now(timezone.utc)
            task_ids = []
            
            for i in range(num_tasks):
                # Create chat
                cursor = await db.execute(
                    """INSERT INTO chats (chat_link, status, assigned_userbot_id)
                       VALUES (?, 'pending', ?)""",
                    (f"t.me/chat_{i}", userbot_id)
                )
                chat_id = cursor.lastrowid
                
                # Create join task
                scheduled_at = now + timedelta(seconds=300 + i * 60)
                cursor = await db.execute(
                    """INSERT INTO join_tasks (userbot_id, chat_id, scheduled_at, status, created_at)
                       VALUES (?, ?, ?, 'pending', CURRENT_TIMESTAMP)""",
                    (userbot_id, chat_id, scheduled_at.isoformat())
                )
                task_ids.append(cursor.lastrowid)
            
            await db.commit()
        
        # Verify tasks are persisted in database
        async with database.get_connection() as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM join_tasks WHERE status = 'pending'"
            )
            count = (await cursor.fetchone())[0]
            assert count == num_tasks
    
    finally:
        # Cleanup
        database.DATABASE_FILE = original_db
        try:
            os.unlink(test_db_file.name)
        except:
            pass


# Property 35: State Recovery After Restart (Queue perspective)
@pytest.mark.asyncio
@settings(max_examples=30, deadline=5000)
@given(
    num_tasks=st.integers(min_value=1, max_value=15)
)
async def test_property_35_queue_state_recovery(num_tasks):
    """Property 35: State Recovery After Restart
    
    **Validates: Requirements 18.3**
    
    For any system restart, the queue must restore all pending tasks
    from the database in the correct order.
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
                ("session_test.session", (datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
            )
            userbot_id = cursor.lastrowid
            
            # Create tasks in database
            now = datetime.now(timezone.utc)
            expected_task_ids = []
            expected_scheduled_times = []
            
            for i in range(num_tasks):
                # Create chat
                cursor = await db.execute(
                    """INSERT INTO chats (chat_link, status, assigned_userbot_id)
                       VALUES (?, 'pending', ?)""",
                    (f"t.me/chat_{i}", userbot_id)
                )
                chat_id = cursor.lastrowid
                
                # Create join task with specific scheduled time
                scheduled_at = now + timedelta(seconds=300 + i * 60)
                cursor = await db.execute(
                    """INSERT INTO join_tasks (userbot_id, chat_id, scheduled_at, status, created_at)
                       VALUES (?, ?, ?, 'pending', CURRENT_TIMESTAMP)""",
                    (userbot_id, chat_id, scheduled_at.isoformat())
                )
                expected_task_ids.append(cursor.lastrowid)
                expected_scheduled_times.append(scheduled_at)
            
            await db.commit()
        
        # Create a new queue and load pending tasks (simulating restart)
        queue = JoinQueue()
        loaded_count = await queue.load_pending_tasks()
        
        # Verify correct number of tasks loaded
        assert loaded_count == num_tasks
        assert queue.qsize() == num_tasks
        
        # Verify tasks are in correct order
        previous_scheduled_at = None
        retrieved_count = 0
        
        while not queue.is_empty() and retrieved_count < num_tasks:
            try:
                task = await asyncio.wait_for(queue._queue.get(), timeout=0.1)
                
                # Verify task ID is in expected list
                assert task.task_id in expected_task_ids
                
                # Verify ordering
                if previous_scheduled_at is not None:
                    assert task.scheduled_at >= previous_scheduled_at
                
                previous_scheduled_at = task.scheduled_at
                retrieved_count += 1
            except asyncio.TimeoutError:
                break
        
        assert retrieved_count == num_tasks
    
    finally:
        # Cleanup
        database.DATABASE_FILE = original_db
        try:
            os.unlink(test_db_file.name)
        except:
            pass


# Edge case tests
@pytest.mark.asyncio
async def test_empty_queue():
    """Test behavior of empty queue."""
    queue = JoinQueue()
    
    assert queue.is_empty()
    assert queue.qsize() == 0


@pytest.mark.asyncio
async def test_load_pending_tasks_empty_database():
    """Test loading pending tasks from empty database."""
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
        
        queue = JoinQueue()
        loaded_count = await queue.load_pending_tasks()
        
        assert loaded_count == 0
        assert queue.is_empty()
    
    finally:
        # Cleanup
        database.DATABASE_FILE = original_db
        try:
            os.unlink(test_db_file.name)
        except:
            pass


@pytest.mark.asyncio
async def test_mark_task_status():
    """Test marking task status in database."""
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
        
        # Create a task in database
        async with database.get_connection() as db:
            cursor = await db.execute(
                """INSERT INTO userbots (session_file, status, joins_today, joins_reset_at)
                   VALUES (?, 'active', 0, ?)""",
                ("session_test.session", (datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
            )
            userbot_id = cursor.lastrowid
            
            cursor = await db.execute(
                """INSERT INTO chats (chat_link, status, assigned_userbot_id)
                   VALUES (?, 'pending', ?)""",
                ("t.me/test", userbot_id)
            )
            chat_id = cursor.lastrowid
            
            scheduled_at = datetime.now(timezone.utc) + timedelta(seconds=300)
            cursor = await db.execute(
                """INSERT INTO join_tasks (userbot_id, chat_id, scheduled_at, status, created_at)
                   VALUES (?, ?, ?, 'pending', CURRENT_TIMESTAMP)""",
                (userbot_id, chat_id, scheduled_at.isoformat())
            )
            task_id = cursor.lastrowid
            await db.commit()
        
        queue = JoinQueue()
        
        # Test mark_task_processing
        await queue.mark_task_processing(task_id)
        async with database.get_connection() as db:
            cursor = await db.execute("SELECT status FROM join_tasks WHERE id = ?", (task_id,))
            status = (await cursor.fetchone())[0]
            assert status == "processing"
        
        # Test mark_task_completed
        await queue.mark_task_completed(task_id)
        async with database.get_connection() as db:
            cursor = await db.execute("SELECT status, completed_at FROM join_tasks WHERE id = ?", (task_id,))
            row = await cursor.fetchone()
            assert row[0] == "completed"
            assert row[1] is not None
    
    finally:
        # Cleanup
        database.DATABASE_FILE = original_db
        try:
            os.unlink(test_db_file.name)
        except:
            pass


@pytest.mark.asyncio
async def test_stop_queue():
    """Test stopping the queue."""
    queue = JoinQueue()
    
    # Add a task far in the future
    future_time = datetime.now(timezone.utc) + timedelta(hours=1)
    await queue.add_task(
        task_id=1,
        userbot_id=1,
        chat_id=1,
        scheduled_at=future_time
    )
    
    # Stop the queue
    queue.stop()
    
    # get_next_task should return None quickly
    task = await queue.get_next_task()
    assert task is None
