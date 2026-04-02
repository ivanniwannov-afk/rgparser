"""Bug condition exploration test for FloodWait Event Loop Blocking.

This test demonstrates the bug where long FloodWait delays block the event loop,
preventing new tasks with shorter delays from being processed.

**CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists.
**DO NOT attempt to fix the test or the code when it fails.**

**Validates: Requirements 1.1, 1.2, 1.4, 2.1, 2.2, 2.4**
"""

import asyncio
import tempfile
import os
from datetime import datetime, timedelta, timezone
from hypothesis import given, strategies as st, settings, HealthCheck
import pytest

from src.ingestion.join_queue import JoinQueue
from database import init_database


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
    import asyncio
    asyncio.run(init_database())
    
    yield test_db_file.name
    
    # Cleanup
    database.DATABASE_FILE = original_db
    try:
        os.unlink(test_db_file.name)
    except:
        pass


@pytest.mark.asyncio
@settings(max_examples=10, deadline=70000, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    long_delay_seconds=st.integers(min_value=60, max_value=60),
    short_delay_seconds=st.integers(min_value=1, max_value=1)
)
async def test_property_1_bug_condition_event_loop_blocking(test_db, long_delay_seconds, short_delay_seconds):
    """Property 1: Bug Condition - Event Loop Blocking on FloodWait
    
    **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists.
    
    **Validates: Requirements 1.1, 1.2, 1.4, 2.1, 2.2, 2.4**
    
    For any state where the worker is waiting for a delayed task and a new task
    with an earlier scheduled_at is added to the queue, the worker SHALL wake up
    immediately, re-evaluate the queue, and process the task with the earliest
    scheduled_at.
    
    This test encodes the EXPECTED BEHAVIOR. On unfixed code, it will FAIL because:
    - The worker blocks on the long delay and cannot wake up for new tasks
    - New tasks with shorter delays are not processed until the long delay expires
    
    On fixed code, this test will PASS because:
    - The worker wakes up when new tasks arrive
    - Tasks are processed in priority order (earliest scheduled_at first)
    """
    queue = JoinQueue()
    now = datetime.now(timezone.utc)
    
    # Add a task with a long delay (simulating FloodWait)
    long_task_scheduled_at = now + timedelta(seconds=long_delay_seconds)
    await queue.add_task(
        task_id=1,
        userbot_id=1,
        chat_id=1,
        scheduled_at=long_task_scheduled_at
    )
    
    print(f"Added long delay task: {long_delay_seconds} seconds")
    
    # Start worker in background
    worker_task = asyncio.create_task(queue.get_next_task())
    
    # Wait a bit to ensure worker is blocked waiting
    await asyncio.sleep(2)
    
    # Add a new task with a short delay while worker is waiting
    short_task_scheduled_at = now + timedelta(seconds=short_delay_seconds)
    await queue.add_task(
        task_id=2,
        userbot_id=1,
        chat_id=2,
        scheduled_at=short_task_scheduled_at
    )
    
    print(f"Added short delay task: {short_delay_seconds} seconds (while worker is waiting)")
    
    # EXPECTED BEHAVIOR: Worker should wake up and process the short delay task first
    # On unfixed code: Worker remains blocked, this will timeout
    # On fixed code: Worker wakes up immediately and returns the short delay task
    
    try:
        # Wait for worker to return a task
        # Give it 5 seconds to wake up and process the short delay task
        # (short_delay_seconds is 1, so 5 seconds is more than enough)
        result_task = await asyncio.wait_for(worker_task, timeout=5.0)
        
        # Verify the worker returned the short delay task (task_id=2)
        assert result_task is not None, "Worker returned None instead of a task"
        assert result_task.task_id == 2, \
            f"Worker returned task {result_task.task_id} instead of task 2 (short delay task)"
        
        # Verify the task was processed quickly (within 5 seconds)
        execution_time = datetime.now(timezone.utc)
        elapsed = (execution_time - now).total_seconds()
        
        # On fixed code: elapsed should be ~3 seconds (2 second wait + 1 second delay)
        # On unfixed code: this assertion won't be reached because timeout will occur
        assert elapsed < 10, \
            f"Task took {elapsed:.1f} seconds to process (expected < 10 seconds)"
        
        print(f"✓ Worker woke up and processed short delay task in {elapsed:.1f} seconds")
        
    except asyncio.TimeoutError:
        # This is the EXPECTED FAILURE on unfixed code
        # The worker is blocked waiting for the long delay and cannot wake up
        worker_task.cancel()
        
        # Try to get the worker task result to see what it was doing
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
        
        # This assertion will FAIL on unfixed code, proving the bug exists
        pytest.fail(
            f"BUG CONFIRMED: Worker blocked for 5+ seconds waiting for long delay task "
            f"({long_delay_seconds}s) and did not wake up to process new short delay task "
            f"({short_delay_seconds}s). This proves the event loop is blocked."
        )


@pytest.mark.asyncio
async def test_bug_condition_concrete_case(test_db):
    """Concrete test case demonstrating the bug condition.
    
    This is a simplified version without property-based testing for easier debugging.
    
    **CRITICAL**: This test MUST FAIL on unfixed code.
    
    **Validates: Requirements 1.1, 1.2, 1.4, 2.1, 2.2, 2.4**
    """
    queue = JoinQueue()
    now = datetime.now(timezone.utc)
    
    # Add a task with 60-second delay
    long_task_scheduled_at = now + timedelta(seconds=60)
    await queue.add_task(
        task_id=1,
        userbot_id=1,
        chat_id=1,
        scheduled_at=long_task_scheduled_at
    )
    
    print("Added task 1 with 60-second delay")
    
    # Start worker
    worker_task = asyncio.create_task(queue.get_next_task())
    
    # Wait to ensure worker is blocked
    await asyncio.sleep(2)
    
    # Add a task with 1-second delay
    short_task_scheduled_at = now + timedelta(seconds=1)
    await queue.add_task(
        task_id=2,
        userbot_id=1,
        chat_id=2,
        scheduled_at=short_task_scheduled_at
    )
    
    print("Added task 2 with 1-second delay (should be processed first)")
    
    # EXPECTED: Worker wakes up and returns task 2 within 5 seconds
    try:
        result_task = await asyncio.wait_for(worker_task, timeout=5.0)
        
        assert result_task is not None
        assert result_task.task_id == 2, \
            f"Expected task 2 (short delay), got task {result_task.task_id}"
        
        print("✓ Worker correctly processed short delay task first")
        
    except asyncio.TimeoutError:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
        
        pytest.fail(
            "BUG CONFIRMED: Worker did not wake up to process new short delay task. "
            "Event loop is blocked by long delay."
        )
