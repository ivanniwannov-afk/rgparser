"""Preservation property tests for FloodWait Event Loop Blocking Fix.

These tests verify that non-buggy scenarios work correctly on UNFIXED code
and must continue to work after the fix is implemented.

**IMPORTANT**: These tests should PASS on unfixed code to establish baseline behavior.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
"""

import asyncio
import tempfile
import os
from datetime import datetime, timedelta, timezone
from hypothesis import given, strategies as st, settings, HealthCheck
import pytest

from src.ingestion.join_queue import JoinQueue
from database import init_database, get_connection


@pytest.fixture(scope="function")
def test_db():
    """Create a temporary test database."""
    test_db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    test_db_file.close()
    
    # Monkey patch the DATABASE_FILE
    import database
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


# Property 2.1: Immediate Task Execution Preservation
@pytest.mark.asyncio
@settings(max_examples=30, deadline=5000, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    num_tasks=st.integers(min_value=1, max_value=10),
    past_seconds=st.integers(min_value=0, max_value=60)
)
async def test_property_2_1_immediate_task_execution(test_db, num_tasks, past_seconds):
    """Property 2.1: Immediate Task Execution Preservation
    
    **Validates: Requirements 3.1**
    
    For any task where scheduled_at <= now, the system SHALL return the task
    immediately without waiting. This behavior must be preserved after the fix.
    """
    queue = JoinQueue()
    now = datetime.now(timezone.utc)
    
    # Add tasks with scheduled_at <= now (ready for immediate execution)
    for i in range(num_tasks):
        # Schedule in the past or at current time
        scheduled_at = now - timedelta(seconds=past_seconds)
        await queue.add_task(
            task_id=i,
            userbot_id=1,
            chat_id=i,
            scheduled_at=scheduled_at
        )
    
    # Get all tasks and verify they are returned immediately
    for i in range(num_tasks):
        start_time = datetime.now(timezone.utc)
        
        # Should return immediately (within 1 second)
        task = await asyncio.wait_for(queue.get_next_task(), timeout=1.0)
        
        end_time = datetime.now(timezone.utc)
        elapsed = (end_time - start_time).total_seconds()
        
        assert task is not None, f"Task {i} was None"
        assert elapsed < 1.0, f"Task {i} took {elapsed:.2f}s (expected < 1.0s)"


# Property 2.2: Empty Queue Blocking Preservation
@pytest.mark.asyncio
@settings(max_examples=20, deadline=10000, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    delay_before_add=st.integers(min_value=1, max_value=3)
)
async def test_property_2_2_empty_queue_blocking(test_db, delay_before_add):
    """Property 2.2: Empty Queue Blocking Preservation
    
    **Validates: Requirements 3.2**
    
    When the queue is empty, get_next_task() SHALL block until a task arrives
    or the stop signal is set. This behavior must be preserved after the fix.
    """
    queue = JoinQueue()
    
    # Start worker on empty queue
    worker_task = asyncio.create_task(queue.get_next_task())
    
    # Wait a bit to ensure worker is blocked
    await asyncio.sleep(0.5)
    
    # Verify worker is still waiting (not completed)
    assert not worker_task.done(), "Worker should be blocked on empty queue"
    
    # Add a task after delay
    await asyncio.sleep(delay_before_add)
    
    now = datetime.now(timezone.utc)
    await queue.add_task(
        task_id=1,
        userbot_id=1,
        chat_id=1,
        scheduled_at=now  # Immediate execution
    )
    
    # Worker should now complete and return the task
    task = await asyncio.wait_for(worker_task, timeout=2.0)
    
    assert task is not None
    assert task.task_id == 1


# Property 2.3: Stop Signal Preservation
@pytest.mark.asyncio
@settings(max_examples=20, deadline=5000, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    delay_before_stop=st.integers(min_value=1, max_value=3)
)
async def test_property_2_3_stop_signal(test_db, delay_before_stop):
    """Property 2.3: Stop Signal Preservation
    
    **Validates: Requirements 3.2**
    
    When the stop signal is set, get_next_task() SHALL return None.
    This behavior must be preserved after the fix.
    """
    queue = JoinQueue()
    
    # Add a task far in the future
    now = datetime.now(timezone.utc)
    future_time = now + timedelta(hours=1)
    await queue.add_task(
        task_id=1,
        userbot_id=1,
        chat_id=1,
        scheduled_at=future_time
    )
    
    # Start worker
    worker_task = asyncio.create_task(queue.get_next_task())
    
    # Wait before stopping
    await asyncio.sleep(delay_before_stop)
    
    # Stop the queue
    queue.stop()
    
    # Worker should return None quickly
    task = await asyncio.wait_for(worker_task, timeout=2.0)
    
    assert task is None, "Worker should return None when stopped"


# Property 2.4: Database Status Updates Preservation
@pytest.mark.asyncio
@settings(max_examples=20, deadline=5000, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    num_tasks=st.integers(min_value=1, max_value=5)
)
async def test_property_2_4_database_status_updates(test_db, num_tasks):
    """Property 2.4: Database Status Updates Preservation
    
    **Validates: Requirements 3.3**
    
    Task status transitions (pending -> processing -> completed/failed) SHALL
    update the database correctly. This behavior must be preserved after the fix.
    """
    queue = JoinQueue()
    
    # Create tasks in database
    async with get_connection() as db:
        # Create userbot with unique session file using timestamp
        import time
        session_suffix = int(time.time() * 1000000)  # Microsecond timestamp
        cursor = await db.execute(
            """INSERT INTO userbots (session_file, status, joins_today, joins_reset_at)
               VALUES (?, 'active', 0, ?)""",
            (f"test_{session_suffix}.session", (datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
        )
        userbot_id = cursor.lastrowid
        
        task_ids = []
        for i in range(num_tasks):
            # Create chat with unique link
            cursor = await db.execute(
                """INSERT INTO chats (chat_link, status, assigned_userbot_id)
                   VALUES (?, 'pending', ?)""",
                (f"t.me/chat_{session_suffix}_{i}", userbot_id)
            )
            chat_id = cursor.lastrowid
            
            # Create join task
            now = datetime.now(timezone.utc)
            cursor = await db.execute(
                """INSERT INTO join_tasks (userbot_id, chat_id, scheduled_at, status, created_at)
                   VALUES (?, ?, ?, 'pending', CURRENT_TIMESTAMP)""",
                (userbot_id, chat_id, now.isoformat())
            )
            task_ids.append(cursor.lastrowid)
        
        await db.commit()
    
    # Test status transitions for each task
    for task_id in task_ids:
        # Mark as processing
        await queue.mark_task_processing(task_id)
        
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT status FROM join_tasks WHERE id = ?",
                (task_id,)
            )
            status = (await cursor.fetchone())[0]
            assert status == "processing", f"Task {task_id} status should be 'processing'"
        
        # Mark as completed
        await queue.mark_task_completed(task_id)
        
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT status, completed_at FROM join_tasks WHERE id = ?",
                (task_id,)
            )
            row = await cursor.fetchone()
            assert row[0] == "completed", f"Task {task_id} status should be 'completed'"
            assert row[1] is not None, f"Task {task_id} completed_at should not be None"


# Property 2.5: Queue Ordering Preservation
@pytest.mark.asyncio
@settings(max_examples=30, deadline=5000, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    scheduled_offsets=st.lists(
        st.integers(min_value=1, max_value=100),
        min_size=2,
        max_size=10,
        unique=True
    )
)
async def test_property_2_5_queue_ordering(test_db, scheduled_offsets):
    """Property 2.5: Queue Ordering Preservation
    
    **Validates: Requirements 3.4**
    
    Tasks SHALL be retrieved in order of scheduled_at (earliest first).
    This behavior must be preserved after the fix.
    """
    queue = JoinQueue()
    now = datetime.now(timezone.utc)
    
    # Add tasks in random order
    import random
    shuffled_offsets = scheduled_offsets.copy()
    random.shuffle(shuffled_offsets)
    
    for i, offset in enumerate(shuffled_offsets):
        # All tasks are in the past (immediate execution)
        scheduled_at = now - timedelta(seconds=offset)
        await queue.add_task(
            task_id=i,
            userbot_id=1,
            chat_id=i,
            scheduled_at=scheduled_at
        )
    
    # Retrieve tasks and verify they come out in sorted order (earliest first)
    previous_scheduled_at = None
    retrieved_tasks = []
    
    for _ in range(len(scheduled_offsets)):
        task = await asyncio.wait_for(queue.get_next_task(), timeout=1.0)
        
        assert task is not None
        
        if previous_scheduled_at is not None:
            assert task.scheduled_at >= previous_scheduled_at, \
                f"Task order violation: {task.scheduled_at} came after {previous_scheduled_at}"
        
        previous_scheduled_at = task.scheduled_at
        retrieved_tasks.append(task)
    
    assert len(retrieved_tasks) == len(scheduled_offsets)


# Property 2.6: Load Pending Tasks Preservation
@pytest.mark.asyncio
@settings(max_examples=20, deadline=5000, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    num_tasks=st.integers(min_value=1, max_value=10)
)
async def test_property_2_6_load_pending_tasks(test_db, num_tasks):
    """Property 2.6: Load Pending Tasks Preservation
    
    **Validates: Requirements 3.4**
    
    On system startup, load_pending_tasks() SHALL restore all pending tasks
    from the database in the correct order. This behavior must be preserved.
    """
    # Create tasks in database
    async with get_connection() as db:
        # Create userbot with unique session file using timestamp
        import time
        session_suffix = int(time.time() * 1000000)  # Microsecond timestamp
        cursor = await db.execute(
            """INSERT INTO userbots (session_file, status, joins_today, joins_reset_at)
               VALUES (?, 'active', 0, ?)""",
            (f"test_{session_suffix}.session", (datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
        )
        userbot_id = cursor.lastrowid
        
        now = datetime.now(timezone.utc)
        expected_task_ids = []
        
        for i in range(num_tasks):
            # Create chat with unique link
            cursor = await db.execute(
                """INSERT INTO chats (chat_link, status, assigned_userbot_id)
                   VALUES (?, 'pending', ?)""",
                (f"t.me/chat_{session_suffix}_{i}", userbot_id)
            )
            chat_id = cursor.lastrowid
            
            # Create join task with future scheduled time
            scheduled_at = now + timedelta(seconds=300 + i * 60)
            cursor = await db.execute(
                """INSERT INTO join_tasks (userbot_id, chat_id, scheduled_at, status, created_at)
                   VALUES (?, ?, ?, 'pending', CURRENT_TIMESTAMP)""",
                (userbot_id, chat_id, scheduled_at.isoformat())
            )
            expected_task_ids.append(cursor.lastrowid)
        
        await db.commit()
    
    # Create queue and load pending tasks
    queue = JoinQueue()
    loaded_count = await queue.load_pending_tasks()
    
    # Verify at least our tasks were loaded (there may be others from previous test runs)
    assert loaded_count >= num_tasks, f"Expected at least {num_tasks} tasks, got {loaded_count}"
    assert queue.qsize() >= num_tasks, f"Expected at least {num_tasks} tasks in queue, got {queue.qsize()}"
    
    # Verify tasks are in correct order and our tasks are present
    previous_scheduled_at = None
    retrieved_count = 0
    found_task_ids = []
    
    while not queue.is_empty():
        try:
            task = await asyncio.wait_for(queue._queue.get(), timeout=0.1)
            
            # Track tasks we created
            if task.task_id in expected_task_ids:
                found_task_ids.append(task.task_id)
            
            # Verify ordering
            if previous_scheduled_at is not None:
                assert task.scheduled_at >= previous_scheduled_at, \
                    f"Task order violation: {task.scheduled_at} came before {previous_scheduled_at}"
            
            previous_scheduled_at = task.scheduled_at
            retrieved_count += 1
        except asyncio.TimeoutError:
            break
    
    # Verify all our tasks were found
    assert len(found_task_ids) == num_tasks, \
        f"Expected to find {num_tasks} of our tasks, found {len(found_task_ids)}"


# Concrete test cases for easier debugging
@pytest.mark.asyncio
async def test_concrete_immediate_execution(test_db):
    """Concrete test: Immediate task execution.
    
    **Validates: Requirements 3.1**
    """
    queue = JoinQueue()
    now = datetime.now(timezone.utc)
    
    # Add task scheduled in the past
    await queue.add_task(
        task_id=1,
        userbot_id=1,
        chat_id=1,
        scheduled_at=now - timedelta(seconds=10)
    )
    
    # Should return immediately
    start_time = datetime.now(timezone.utc)
    task = await asyncio.wait_for(queue.get_next_task(), timeout=1.0)
    end_time = datetime.now(timezone.utc)
    
    elapsed = (end_time - start_time).total_seconds()
    
    assert task is not None
    assert task.task_id == 1
    assert elapsed < 1.0, f"Task took {elapsed:.2f}s (expected < 1.0s)"


@pytest.mark.asyncio
async def test_concrete_empty_queue(test_db):
    """Concrete test: Empty queue blocks until task arrives.
    
    **Validates: Requirements 3.2**
    """
    queue = JoinQueue()
    
    # Start worker on empty queue
    worker_task = asyncio.create_task(queue.get_next_task())
    
    # Wait to ensure worker is blocked
    await asyncio.sleep(1)
    
    # Verify worker is still waiting
    assert not worker_task.done()
    
    # Add a task
    now = datetime.now(timezone.utc)
    await queue.add_task(
        task_id=1,
        userbot_id=1,
        chat_id=1,
        scheduled_at=now
    )
    
    # Worker should complete
    task = await asyncio.wait_for(worker_task, timeout=2.0)
    
    assert task is not None
    assert task.task_id == 1


@pytest.mark.asyncio
async def test_concrete_queue_ordering(test_db):
    """Concrete test: Tasks are retrieved in scheduled_at order.
    
    **Validates: Requirements 3.4**
    """
    queue = JoinQueue()
    now = datetime.now(timezone.utc)
    
    # Add tasks in reverse order
    await queue.add_task(
        task_id=3,
        userbot_id=1,
        chat_id=3,
        scheduled_at=now - timedelta(seconds=10)
    )
    await queue.add_task(
        task_id=2,
        userbot_id=1,
        chat_id=2,
        scheduled_at=now - timedelta(seconds=20)
    )
    await queue.add_task(
        task_id=1,
        userbot_id=1,
        chat_id=1,
        scheduled_at=now - timedelta(seconds=30)
    )
    
    # Should retrieve in order: task 1, task 2, task 3
    task1 = await asyncio.wait_for(queue.get_next_task(), timeout=1.0)
    task2 = await asyncio.wait_for(queue.get_next_task(), timeout=1.0)
    task3 = await asyncio.wait_for(queue.get_next_task(), timeout=1.0)
    
    assert task1.task_id == 1
    assert task2.task_id == 2
    assert task3.task_id == 3
