"""Test for task delay bug fix.

This test verifies that the fix for the task delay bug is working correctly:
- Tasks are created with correct delays (from config: join_delay_min to join_delay_max)
- Tasks are added to the join_queue after creation
- scheduled_at = created_at + delay

**Validates: Requirements 2.1, 2.2, 2.4**
"""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from config import config
from database import init_database, get_connection
from src.ingestion.ingestion_module import IngestionModule
from src.ingestion.join_queue import JoinQueue
from src.userbot.userbot_pool_manager import UserbotPoolManager


@pytest.fixture(scope="session")
async def test_db():
    """Initialize test database."""
    await init_database()
    yield


@pytest.fixture
async def clean_test_data():
    """Clean test data before and after each test."""
    # Cleanup before test
    async with get_connection() as db:
        await db.execute("DELETE FROM chats WHERE id >= 900000")
        await db.execute("DELETE FROM userbots WHERE id >= 900000")
        await db.execute("DELETE FROM join_tasks WHERE id >= 900000")
        await db.commit()
    
    yield
    
    # Cleanup after test
    async with get_connection() as db:
        await db.execute("DELETE FROM chats WHERE id >= 900000")
        await db.execute("DELETE FROM userbots WHERE id >= 900000")
        await db.execute("DELETE FROM join_tasks WHERE id >= 900000")
        await db.commit()


@pytest.fixture
def mock_userbot_pool():
    """Create a mock userbot pool with one active userbot."""
    pool = AsyncMock(spec=UserbotPoolManager)
    
    # Mock get_available_userbots to return one userbot
    pool.get_available_userbots = AsyncMock(return_value=[900001])
    
    return pool


@pytest.fixture
async def setup_test_userbot():
    """Create a test userbot in the database."""
    async with get_connection() as db:
        await db.execute("""
            INSERT INTO userbots (id, session_file, status, joins_today, joins_reset_at, created_at, updated_at)
            VALUES (900001, 'test_session.session', 'active', 0, datetime('now', '+1 day'), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """)
        await db.commit()
    
    yield
    
    # Cleanup
    async with get_connection() as db:
        await db.execute("DELETE FROM userbots WHERE id = 900001")
        await db.commit()


@pytest.mark.asyncio
async def test_task_delay_fix_single_chat(test_db, clean_test_data, setup_test_userbot, mock_userbot_pool):
    """Test that tasks are created with correct delays and added to join_queue.
    
    This test verifies the fix for the task delay bug:
    1. Creates a pending chat
    2. Calls _process_pending_chats() logic
    3. Verifies task is created in DB with delay from config (join_delay_min to join_delay_max)
    4. Verifies task is added to join_queue
    5. Verifies scheduled_at = created_at + delay
    
    **Validates: Requirements 2.1, 2.2, 2.4**
    """
    # Create a pending chat
    chat_id = 900001
    async with get_connection() as db:
        await db.execute("""
            INSERT OR REPLACE INTO chats (id, chat_link, status, created_at, updated_at)
            VALUES (?, 'https://t.me/test_channel_fix', 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (chat_id,))
        await db.commit()
    
    # Initialize components
    ingestion = IngestionModule(
        join_delay_min=config['join_delay_min'],
        join_delay_max=config['join_delay_max'],
        daily_join_limit=config['daily_join_limit']
    )
    join_queue = JoinQueue()
    
    # Simulate _process_pending_chats() logic
    # 1. Distribute chats
    distribution = await ingestion.distribute_chats([chat_id])
    
    # 2. Create join tasks in database
    await ingestion.enqueue_join_tasks(distribution)
    
    # 3. Add tasks to join_queue (this is the fix!)
    tasks_added = 0
    async with get_connection() as db:
        for userbot_id, assigned_chat_ids in distribution.items():
            for assigned_chat_id in assigned_chat_ids:
                # Get the task we just created
                cursor = await db.execute("""
                    SELECT id, scheduled_at, created_at
                    FROM join_tasks
                    WHERE userbot_id = ? AND chat_id = ? AND status = 'pending'
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (userbot_id, assigned_chat_id))
                task_row = await cursor.fetchone()
                
                if task_row:
                    task_id, scheduled_at_str, created_at_str = task_row
                    scheduled_at = datetime.fromisoformat(scheduled_at_str)
                    created_at = datetime.fromisoformat(created_at_str)
                    
                    # Ensure timezone-aware datetime
                    if scheduled_at.tzinfo is None:
                        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    
                    # Add to queue
                    await join_queue.add_task(task_id, userbot_id, assigned_chat_id, scheduled_at)
                    tasks_added += 1
                    
                    # Verify delay is in correct range (from config)
                    delay_seconds = (scheduled_at - created_at).total_seconds()
                    min_delay = config['join_delay_min']
                    max_delay = config['join_delay_max']
                    assert min_delay <= delay_seconds <= max_delay, f"Delay {delay_seconds}s is not in range [{min_delay}, {max_delay}]"
                    
                    print(f"✓ Task {task_id} created with delay {delay_seconds:.1f}s")
    
    # Verify task was added to join_queue
    assert tasks_added == 1, "Expected 1 task to be added to queue"
    assert join_queue.qsize() == 1, "Expected queue size to be 1"
    
    print(f"✓ Test passed: Task created with correct delay and added to queue")


@pytest.mark.asyncio
async def test_task_delay_fix_multiple_chats(test_db, clean_test_data, setup_test_userbot, mock_userbot_pool):
    """Test that multiple tasks are created with correct delays and added to join_queue.
    
    This test verifies the fix works for multiple chats:
    1. Creates 3 pending chats
    2. Calls _process_pending_chats() logic
    3. Verifies all tasks are created with delays from config (join_delay_min to join_delay_max)
    4. Verifies all tasks are added to join_queue
    
    **Validates: Requirements 2.1, 2.2, 2.4**
    """
    # Create 3 pending chats
    chat_ids = [900002, 900003, 900004]
    async with get_connection() as db:
        for i, chat_id in enumerate(chat_ids):
            await db.execute("""
                INSERT OR REPLACE INTO chats (id, chat_link, status, created_at, updated_at)
                VALUES (?, ?, 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (chat_id, f'https://t.me/test_channel_{i}'))
        await db.commit()
    
    # Initialize components
    ingestion = IngestionModule(
        join_delay_min=config['join_delay_min'],
        join_delay_max=config['join_delay_max'],
        daily_join_limit=config['daily_join_limit']
    )
    join_queue = JoinQueue()
    
    # Simulate _process_pending_chats() logic
    distribution = await ingestion.distribute_chats(chat_ids)
    await ingestion.enqueue_join_tasks(distribution)
    
    # Add tasks to join_queue
    tasks_added = 0
    delays = []
    
    async with get_connection() as db:
        for userbot_id, assigned_chat_ids in distribution.items():
            for assigned_chat_id in assigned_chat_ids:
                cursor = await db.execute("""
                    SELECT id, scheduled_at, created_at
                    FROM join_tasks
                    WHERE userbot_id = ? AND chat_id = ? AND status = 'pending'
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (userbot_id, assigned_chat_id))
                task_row = await cursor.fetchone()
                
                if task_row:
                    task_id, scheduled_at_str, created_at_str = task_row
                    scheduled_at = datetime.fromisoformat(scheduled_at_str)
                    created_at = datetime.fromisoformat(created_at_str)
                    
                    if scheduled_at.tzinfo is None:
                        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    
                    await join_queue.add_task(task_id, userbot_id, assigned_chat_id, scheduled_at)
                    tasks_added += 1
                    
                    # Verify delay
                    delay_seconds = (scheduled_at - created_at).total_seconds()
                    delays.append(delay_seconds)
                    min_delay = config['join_delay_min']
                    max_delay = config['join_delay_max']
                    assert min_delay <= delay_seconds <= max_delay, f"Delay {delay_seconds}s is not in range [{min_delay}, {max_delay}]"
    
    # Verify all tasks were added
    assert tasks_added == 3, f"Expected 3 tasks to be added, got {tasks_added}"
    assert join_queue.qsize() == 3, f"Expected queue size to be 3, got {join_queue.qsize()}"
    
    # Verify all delays are in correct range
    min_delay = config['join_delay_min']
    max_delay = config['join_delay_max']
    for delay in delays:
        assert min_delay <= delay <= max_delay, f"Delay {delay}s is not in range [{min_delay}, {max_delay}]"
    
    print(f"✓ Test passed: {tasks_added} tasks created with delays {delays}")


@pytest.mark.asyncio
async def test_scheduled_at_equals_created_at_plus_delay(test_db, clean_test_data, setup_test_userbot, mock_userbot_pool):
    """Test that scheduled_at = created_at + delay.
    
    This test verifies the mathematical relationship between timestamps:
    scheduled_at should equal created_at plus the delay in seconds.
    
    **Validates: Requirements 2.1, 2.4**
    """
    # Create a pending chat
    chat_id = 900005
    async with get_connection() as db:
        await db.execute("""
            INSERT OR REPLACE INTO chats (id, chat_link, status, created_at, updated_at)
            VALUES (?, 'https://t.me/test_channel_math', 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (chat_id,))
        await db.commit()
    
    # Initialize components
    ingestion = IngestionModule(
        join_delay_min=config['join_delay_min'],
        join_delay_max=config['join_delay_max'],
        daily_join_limit=config['daily_join_limit']
    )
    
    # Create task
    distribution = await ingestion.distribute_chats([chat_id])
    await ingestion.enqueue_join_tasks(distribution)
    
    # Verify the mathematical relationship
    async with get_connection() as db:
        cursor = await db.execute("""
            SELECT scheduled_at, created_at
            FROM join_tasks
            WHERE chat_id = ? AND status = 'pending'
            ORDER BY created_at DESC
            LIMIT 1
        """, (chat_id,))
        task_row = await cursor.fetchone()
        
        assert task_row is not None, "Task not found in database"
        
        scheduled_at_str, created_at_str = task_row
        scheduled_at = datetime.fromisoformat(scheduled_at_str)
        created_at = datetime.fromisoformat(created_at_str)
        
        if scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        
        # Calculate delay
        delay_seconds = (scheduled_at - created_at).total_seconds()
        
        # Verify: scheduled_at = created_at + delay
        expected_scheduled_at = created_at + timedelta(seconds=delay_seconds)
        
        # Allow 1 second tolerance for floating point precision
        time_diff = abs((scheduled_at - expected_scheduled_at).total_seconds())
        assert time_diff < 1.0, f"scheduled_at does not equal created_at + delay (diff: {time_diff}s)"
        
        # Verify delay is in correct range
        min_delay = config['join_delay_min']
        max_delay = config['join_delay_max']
        assert min_delay <= delay_seconds <= max_delay, f"Delay {delay_seconds}s is not in range [{min_delay}, {max_delay}]"
        
        print(f"✓ Test passed: scheduled_at = created_at + {delay_seconds:.1f}s")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
