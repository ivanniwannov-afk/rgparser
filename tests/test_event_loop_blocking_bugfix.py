"""Bug Condition Exploration Tests for Event Loop Blocking

**CRITICAL**: These tests MUST FAIL on unfixed code - failure confirms the bugs exist.
**DO NOT attempt to fix the tests or the code when they fail.**
**NOTE**: These tests encode the expected behavior - they will validate the fix when they pass after implementation.
**GOAL**: Surface counterexamples that demonstrate Event Loop blocking bugs exist.

**Validates: Requirements 1.1, 1.2, 2.1, 2.2**
"""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

from src.ingestion.join_queue import JoinQueue
from src.ingestion.join_logic import _handle_antibot_protection


class TestEventLoopBlocking:
    """Test suite for Event Loop blocking bugs.
    
    These tests demonstrate that:
    1. FloodWait blocks the worker thread for the entire duration
    2. Antibot sleep blocks the thread for 60 seconds instead of 2-3 seconds
    """
    
    @pytest.mark.asyncio
    async def test_floodwait_blocks_worker_thread(self):
        """Test 1.1: FloodWait blocks worker thread
        
        **Bug Condition**: Worker gets task with FloodWait 24000s (400 minutes),
        blocks for entire duration instead of processing other ready tasks.
        
        **Expected Behavior**: Worker processes 5-second task immediately.
        
        **On UNFIXED code**: EXPECT FAILURE - worker blocked for 400 minutes.
        
        **Validates: Requirements 1.1, 2.1**
        """
        # Create join queue
        queue = JoinQueue()
        
        # Create a task with a long FloodWait delay (24000 seconds = 400 minutes)
        now = datetime.now(timezone.utc)
        long_delay_time = now + timedelta(seconds=24000)
        
        # Add the long-delay task
        await queue.add_task(
            task_id=1,
            userbot_id=1,
            chat_id=1,
            scheduled_at=long_delay_time
        )
        
        # Start a coroutine to get the next task (this will wait for the long delay)
        get_task_future = asyncio.create_task(queue.get_next_task())
        
        # Wait a moment to ensure the worker is waiting
        await asyncio.sleep(0.5)
        
        # Now add a task with a 5-second delay
        short_delay_time = now + timedelta(seconds=5)
        await queue.add_task(
            task_id=2,
            userbot_id=2,
            chat_id=2,
            scheduled_at=short_delay_time
        )
        
        # Wait for the short delay to pass
        await asyncio.sleep(6)
        
        # Check if the worker has processed the short-delay task
        # Expected behavior: Worker should wake up and process task 2 immediately
        # Bug behavior: Worker is still blocked waiting for task 1's 24000-second delay
        
        # Try to get the task with a timeout
        try:
            task = await asyncio.wait_for(get_task_future, timeout=1.0)
            
            # Expected: We should get task 2 (the short-delay task)
            # Bug: We would still be waiting for task 1
            assert task is not None, "Worker should have returned a task"
            assert task.task_id == 2, (
                f"Expected worker to process short-delay task (ID 2), "
                f"but got task ID {task.task_id}. "
                f"This indicates the worker is blocked by the long FloodWait."
            )
            
        except asyncio.TimeoutError:
            pytest.fail(
                "Worker is blocked and did not process the short-delay task. "
                "This confirms the FloodWait blocking bug: the worker is stuck "
                "waiting for the 24000-second delay instead of waking up to "
                "process the 5-second task."
            )
        finally:
            # Cleanup: stop the queue
            queue.stop()
            try:
                await asyncio.wait_for(get_task_future, timeout=0.1)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
    
    @pytest.mark.asyncio
    async def test_antibot_sleep_blocks_thread_for_60_seconds(self):
        """Test 1.2: Antibot sleep blocks thread for 60 seconds
        
        **Bug Condition**: Userbot passes antibot protection, system executes
        asyncio.sleep(60), freezing the execution thread for 60 seconds.
        
        **Expected Behavior**: Sleep duration is 2-3 seconds.
        
        **On UNFIXED code**: EXPECT FAILURE - sleep is 60 seconds.
        
        **Validates: Requirements 1.2, 2.2**
        """
        # Create mock client and chat
        mock_client = AsyncMock()
        mock_chat = MagicMock()
        mock_chat.id = 123456
        mock_chat.title = "Test Chat"
        
        # Create a mock message with inline keyboard (antibot protection)
        mock_message = MagicMock()
        mock_message.id = 1
        mock_message.reply_markup = MagicMock()
        mock_message.reply_markup.inline_keyboard = [
            [MagicMock(callback_data=b"antibot_button")]
        ]
        
        # Mock get_chat_history to return the antibot message
        async def mock_get_chat_history(chat_id, limit):
            yield mock_message
        
        mock_client.get_chat_history = mock_get_chat_history
        mock_client.request_callback_answer = AsyncMock()
        
        # Measure the actual sleep duration
        start_time = asyncio.get_event_loop().time()
        
        result = await _handle_antibot_protection(
            client=mock_client,
            chat=mock_chat,
            userbot_id=1,
            delivery_bot_token=None,
            operator_chat_id=None
        )
        
        end_time = asyncio.get_event_loop().time()
        actual_duration = end_time - start_time
        
        # Expected behavior: Sleep duration should be 2-3 seconds
        # Bug behavior: Sleep duration is 60 seconds
        assert actual_duration < 5, (
            f"Antibot sleep duration is {actual_duration:.1f} seconds, "
            f"which is much longer than the expected 2-3 seconds. "
            f"This confirms the antibot sleep blocking bug: the system is "
            f"sleeping for 60 seconds instead of 2-3 seconds."
        )
        
        # Verify the button was clicked
        mock_client.request_callback_answer.assert_called_once()
        
        # Verify the function returned True (antibot handled)
        assert result is True, "Antibot protection should be handled successfully"
