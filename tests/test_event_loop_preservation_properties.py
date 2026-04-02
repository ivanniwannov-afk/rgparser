"""Preservation property tests for Event Loop operations.

These tests verify that normal Event Loop operations work correctly on UNFIXED code
and must continue to work after the fix is implemented.

**IMPORTANT**: These tests should PASS on unfixed code to establish baseline behavior.

**Validates: Requirements 3.1, 3.2**
"""

import asyncio
import tempfile
import os
from datetime import datetime, timedelta, timezone
from hypothesis import given, strategies as st, settings, HealthCheck
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.ingestion.join_queue import JoinQueue
from src.ingestion.join_logic import safe_join_chat
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


# Property 1: Normal Task Processing Order Preservation
@pytest.mark.asyncio
@settings(max_examples=30, deadline=5000, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    num_tasks=st.integers(min_value=2, max_value=10),
    past_seconds=st.integers(min_value=1, max_value=60)
)
async def test_property_1_normal_task_processing_order(test_db, num_tasks, past_seconds):
    """Property 1: Normal Task Processing Order Preservation
    
    **Validates: Requirements 3.1**
    
    For all tasks without FloodWait (scheduled_at <= now), the system SHALL
    process tasks in priority order by scheduled_at (earliest first).
    This behavior must be preserved after the fix.
    
    **Expected on UNFIXED code**: PASS (confirms baseline behavior)
    """
    queue = JoinQueue()
    now = datetime.now(timezone.utc)
    
    # Create tasks with different scheduled times (all in the past = no FloodWait)
    scheduled_times = []
    for i in range(num_tasks):
        # Each task scheduled further in the past
        scheduled_at = now - timedelta(seconds=past_seconds + i * 10)
        scheduled_times.append(scheduled_at)
        await queue.add_task(
            task_id=i,
            userbot_id=1,
            chat_id=i,
            scheduled_at=scheduled_at
        )
    
    # Retrieve tasks and verify they come out in sorted order (earliest first)
    retrieved_tasks = []
    previous_scheduled_at = None
    
    for _ in range(num_tasks):
        task = await asyncio.wait_for(queue.get_next_task(), timeout=2.0)
        
        assert task is not None, "Task should not be None"
        
        # Verify ordering: each task should have scheduled_at >= previous
        if previous_scheduled_at is not None:
            assert task.scheduled_at >= previous_scheduled_at, (
                f"Task order violation: {task.scheduled_at} came after {previous_scheduled_at}. "
                f"Tasks should be processed in priority order by scheduled_at."
            )
        
        previous_scheduled_at = task.scheduled_at
        retrieved_tasks.append(task)
    
    assert len(retrieved_tasks) == num_tasks, (
        f"Expected {num_tasks} tasks, got {len(retrieved_tasks)}"
    )


# Property 2: Immediate Task Execution Preservation
@pytest.mark.asyncio
@settings(max_examples=30, deadline=5000, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    num_tasks=st.integers(min_value=1, max_value=10),
    past_seconds=st.integers(min_value=0, max_value=120)
)
async def test_property_2_immediate_task_execution(test_db, num_tasks, past_seconds):
    """Property 2: Immediate Task Execution Preservation
    
    **Validates: Requirements 3.1**
    
    For all tasks where scheduled_at <= now (no FloodWait), the system SHALL
    return the task immediately without waiting. This behavior must be preserved.
    
    **Expected on UNFIXED code**: PASS (confirms baseline behavior)
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
        assert elapsed < 1.0, (
            f"Task {i} took {elapsed:.2f}s (expected < 1.0s). "
            f"Tasks without FloodWait should be returned immediately."
        )


# Property 3: Join Without Antibot Completion Time Preservation
@pytest.mark.asyncio
@settings(max_examples=20, deadline=10000, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    num_joins=st.integers(min_value=1, max_value=5)
)
async def test_property_3_join_without_antibot_minimal_delay(test_db, num_joins):
    """Property 3: Join Without Antibot Completion Time Preservation
    
    **Validates: Requirements 3.2**
    
    For all joins without antibot protection, the system SHALL complete the join
    operation without extra delays (completion time is minimal).
    This behavior must be preserved after the fix.
    
    **Expected on UNFIXED code**: PASS (confirms baseline behavior)
    """
    from src.userbot.userbot_pool_manager import UserbotPoolManager
    
    # Create mock pool manager
    pool_manager = AsyncMock(spec=UserbotPoolManager)
    pool_manager.increment_joins_today = AsyncMock()
    pool_manager.mark_unavailable = AsyncMock()
    pool_manager.redistribute_tasks = AsyncMock()
    
    for i in range(num_joins):
        # Create mock client and chat (NO antibot protection)
        mock_client = AsyncMock()
        mock_chat = MagicMock()
        mock_chat.id = 123456 + i
        mock_chat.title = f"Test Chat {i}"
        
        # Mock join_chat to return chat without antibot
        mock_client.join_chat = AsyncMock(return_value=mock_chat)
        
        # Mock get_chat_history to return NO messages with inline keyboards
        async def mock_get_chat_history(chat_id, limit):
            # Return empty history (no antibot protection)
            return
            yield  # Make it an async generator
        
        mock_client.get_chat_history = mock_get_chat_history
        
        # Create chat in database with unique link using timestamp
        import time
        timestamp_suffix = int(time.time() * 1000000)  # Microsecond timestamp
        chat_link = f"t.me/test_chat_{timestamp_suffix}_{i}"
        
        async with get_connection() as db:
            cursor = await db.execute(
                """INSERT INTO chats (chat_link, status)
                   VALUES (?, 'pending')""",
                (chat_link,)
            )
            chat_db_id = cursor.lastrowid
            await db.commit()
        
        # Measure join completion time
        start_time = datetime.now(timezone.utc)
        
        success, error_message = await safe_join_chat(
            client=mock_client,
            chat_link=chat_link,
            chat_db_id=chat_db_id,
            userbot_id=1,
            pool_manager=pool_manager,
            delivery_bot_token=None,
            operator_chat_id=None
        )
        
        end_time = datetime.now(timezone.utc)
        elapsed = (end_time - start_time).total_seconds()
        
        # Verify join succeeded
        assert success is True, f"Join {i} should succeed without antibot protection"
        assert error_message is None, f"Join {i} should have no error message"
        
        # Verify completion time is minimal (< 5 seconds)
        # Note: We allow up to 5 seconds for database operations and network simulation
        assert elapsed < 5.0, (
            f"Join {i} took {elapsed:.2f}s (expected < 5.0s). "
            f"Joins without antibot protection should complete quickly without extra delays."
        )
        
        # Verify join_chat was called
        mock_client.join_chat.assert_called_once()


# Property 4: Empty Queue Blocking Preservation
@pytest.mark.asyncio
@settings(max_examples=20, deadline=10000, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    delay_before_add=st.integers(min_value=1, max_value=3)
)
async def test_property_4_empty_queue_blocking(test_db, delay_before_add):
    """Property 4: Empty Queue Blocking Preservation
    
    **Validates: Requirements 3.1**
    
    When the queue is empty, get_next_task() SHALL block until a task arrives
    or the stop signal is set. This behavior must be preserved after the fix.
    
    **Expected on UNFIXED code**: PASS (confirms baseline behavior)
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


# Property 5: Stop Signal Preservation
@pytest.mark.asyncio
@settings(max_examples=20, deadline=5000, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    delay_before_stop=st.integers(min_value=1, max_value=3)
)
async def test_property_5_stop_signal(test_db, delay_before_stop):
    """Property 5: Stop Signal Preservation
    
    **Validates: Requirements 3.1**
    
    When the stop signal is set, get_next_task() SHALL return None.
    This behavior must be preserved after the fix.
    
    **Expected on UNFIXED code**: PASS (confirms baseline behavior)
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


# Concrete test cases for easier debugging
@pytest.mark.asyncio
async def test_concrete_normal_task_processing_order(test_db):
    """Concrete test: Normal tasks process in scheduled_at order.
    
    **Validates: Requirements 3.1**
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


@pytest.mark.asyncio
async def test_concrete_immediate_execution(test_db):
    """Concrete test: Tasks without FloodWait execute immediately.
    
    **Validates: Requirements 3.1**
    """
    queue = JoinQueue()
    now = datetime.now(timezone.utc)
    
    # Add task scheduled in the past (no FloodWait)
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
async def test_concrete_join_without_antibot(test_db):
    """Concrete test: Join without antibot completes quickly.
    
    **Validates: Requirements 3.2**
    """
    from src.userbot.userbot_pool_manager import UserbotPoolManager
    
    # Create mock pool manager
    pool_manager = AsyncMock(spec=UserbotPoolManager)
    pool_manager.increment_joins_today = AsyncMock()
    
    # Create mock client and chat (NO antibot protection)
    mock_client = AsyncMock()
    mock_chat = MagicMock()
    mock_chat.id = 123456
    mock_chat.title = "Test Chat"
    
    # Mock join_chat to return chat without antibot
    mock_client.join_chat = AsyncMock(return_value=mock_chat)
    
    # Mock get_chat_history to return NO messages with inline keyboards
    async def mock_get_chat_history(chat_id, limit):
        # Return empty history (no antibot protection)
        return
        yield  # Make it an async generator
    
    mock_client.get_chat_history = mock_get_chat_history
    
    # Create chat in database
    async with get_connection() as db:
        cursor = await db.execute(
            """INSERT INTO chats (chat_link, status)
               VALUES (?, 'pending')""",
            ("t.me/test_chat",)
        )
        chat_db_id = cursor.lastrowid
        await db.commit()
    
    # Measure join completion time
    start_time = datetime.now(timezone.utc)
    
    success, error_message = await safe_join_chat(
        client=mock_client,
        chat_link="t.me/test_chat",
        chat_db_id=chat_db_id,
        userbot_id=1,
        pool_manager=pool_manager,
        delivery_bot_token=None,
        operator_chat_id=None
    )
    
    end_time = datetime.now(timezone.utc)
    elapsed = (end_time - start_time).total_seconds()
    
    # Verify join succeeded
    assert success is True
    assert error_message is None
    
    # Verify completion time is minimal (< 5 seconds)
    assert elapsed < 5.0, f"Join took {elapsed:.2f}s (expected < 5.0s)"
    
    # Verify join_chat was called
    mock_client.join_chat.assert_called_once()
