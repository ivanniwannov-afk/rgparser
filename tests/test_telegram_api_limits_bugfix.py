"""Bug Condition Exploration Tests for Telegram API Limits

**CRITICAL**: These tests MUST FAIL on unfixed code - failure confirms the bugs exist.
**DO NOT attempt to fix the tests or the code when they fail.**
**NOTE**: These tests encode the expected behavior - they will validate the fix when they pass after implementation.
**GOAL**: Surface counterexamples that demonstrate Telegram API Limits bugs exist.

**Validates: Requirements 1.10, 1.11, 1.12, 2.10, 2.11, 2.12**
"""

import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, call
from io import StringIO
import sys

from src.delivery.delivery_bot import DeliveryBot, QualifiedLead
from src.ingestion.join_logic import safe_join_chat


class TestTelegramAPILimits:
    """Test suite for Telegram API Limits bugs.
    
    These tests demonstrate that:
    1. RetryAfter errors cause leads to be lost
    2. Inline buttons don't work because polling is not started
    3. FloodWait errors are logged silently without operator notification
    """
    
    @pytest.mark.asyncio
    async def test_retry_after_loses_lead(self):
        """Test 1.10: RetryAfter error loses lead
        
        **Bug Condition**: delivery_bot sends message and receives telegram.error.RetryAfter,
        lead is lost in generic except block because this error is not handled.
        
        **Expected Behavior**: Lead delivered after waiting 30 seconds.
        
        **On UNFIXED code**: EXPECT FAILURE - lead lost, no retry.
        
        **Validates: Requirements 1.10, 2.10**
        """
        from telegram.error import RetryAfter
        from datetime import timedelta
        
        # Create delivery bot
        bot = DeliveryBot(bot_token="test_token", operator_chat_id=123456)
        
        # Create a qualified lead
        lead = QualifiedLead(
            text="Test lead message",
            sender_id=789,
            sender_username="testuser",
            chat_id=456,
            chat_title="Test Chat",
            timestamp=datetime.now()
        )
        
        # Mock the bot and application
        mock_bot = AsyncMock()
        mock_app = MagicMock()
        bot._bot = mock_bot
        bot._app = mock_app
        
        # Create a RetryAfter exception with timedelta
        retry_after_error = RetryAfter(timedelta(seconds=30))
        
        # Track call count
        call_count = 0
        
        async def mock_send_message(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call raises RetryAfter
                raise retry_after_error
            else:
                # Second call succeeds
                return MagicMock(message_id=1)
        
        mock_bot.send_message = mock_send_message
        
        # Try to deliver the lead
        start_time = asyncio.get_event_loop().time()
        
        try:
            await bot.deliver_lead(lead)
            
            # Expected behavior: Should retry after waiting
            end_time = asyncio.get_event_loop().time()
            elapsed = end_time - start_time
            
            # Verify the message was sent twice (first failed, second succeeded)
            assert call_count == 2, (
                f"Expected 2 send attempts (first fails with RetryAfter, second succeeds), "
                f"but got {call_count} attempts. "
                f"This confirms the RetryAfter bug: the system does not retry after "
                f"receiving RetryAfter error, and the lead is lost."
            )
            
            # Verify we waited approximately 30 seconds
            assert elapsed >= 29, (
                f"Expected to wait ~30 seconds for RetryAfter, but only waited {elapsed:.1f}s. "
                f"The system should wait for retry_after duration before retrying."
            )
            
        except Exception as e:
            # Bug behavior: Exception is raised and lead is lost
            pytest.fail(
                f"Lead delivery failed with exception: {e}. "
                f"This confirms the RetryAfter bug: the system does not handle "
                f"RetryAfter errors, and the lead is lost in the generic except block. "
                f"Call count was {call_count} (expected 2 for retry logic)."
            )
    
    @pytest.mark.asyncio
    async def test_inline_buttons_without_polling(self):
        """Test 1.11: Inline buttons don't work without polling
        
        **Bug Condition**: delivery_bot sends messages with inline buttons,
        but buttons don't work because bot doesn't run start_polling() to listen for callbacks.
        
        **Expected Behavior**: Callback received and processed.
        
        **On UNFIXED code**: EXPECT FAILURE - no polling, callback never received.
        
        **Validates: Requirements 1.11, 2.11**
        """
        # Track if polling was started
        polling_started = False
        
        # Create a mock application that tracks if start_polling is called
        mock_updater = MagicMock()
        
        async def mock_start_polling():
            nonlocal polling_started
            polling_started = True
        
        mock_updater.start_polling = mock_start_polling
        
        mock_app = MagicMock()
        mock_app.updater = mock_updater
        mock_app.initialize = AsyncMock()
        mock_app.start = AsyncMock()
        mock_app.add_handler = MagicMock()
        
        # Mock Bot
        mock_bot = AsyncMock()
        
        # Mock the telegram.ext module to return our mock app
        with patch('telegram.ext.Application') as mock_application_class:
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.build.return_value = mock_app
            mock_application_class.builder.return_value = mock_builder
            
            # Mock Bot class
            with patch('telegram.Bot', return_value=mock_bot):
                # Create delivery bot and call start()
                bot = DeliveryBot(bot_token="test_token", operator_chat_id=123456)
                await bot.start()
        
        # Give asyncio.create_task a moment to execute
        await asyncio.sleep(0.1)
        
        # Expected behavior: After start(), polling should be active
        # Bug behavior: Polling is never started
        
        assert polling_started, (
            "Polling was not started. "
            "This confirms the inline buttons bug: the bot does not start polling "
            "to listen for callback button presses. When inline buttons are sent, "
            "clicking them will have no effect because the bot is not listening for callbacks. "
            "The start() method initializes the application but never calls start_polling() "
            "or run_polling() to begin listening for updates."
        )
    
    @pytest.mark.asyncio
    async def test_floodwait_silent_logging(self):
        """Test 1.12: FloodWait logged silently without operator notification
        
        **Bug Condition**: Userbot receives FloodWait from Telegram,
        error is logged to database but system doesn't notify operator via console or Telegram.
        
        **Expected Behavior**: Console warning printed AND Telegram notification sent.
        
        **On UNFIXED code**: EXPECT FAILURE - only database log, no console/Telegram.
        
        **Validates: Requirements 1.12, 2.12**
        """
        # Create mock client and pool manager
        mock_client = AsyncMock()
        mock_pool_manager = AsyncMock()
        mock_pool_manager.mark_unavailable = AsyncMock()
        mock_pool_manager.redistribute_tasks = AsyncMock()
        
        # Mock FloodWait error
        from pyrogram.errors import FloodWait
        floodwait_error = FloodWait(value=3600)  # 1 hour FloodWait
        
        # Mock join_chat to raise FloodWait
        mock_client.join_chat = AsyncMock(side_effect=floodwait_error)
        
        # Capture console output
        captured_output = StringIO()
        original_stdout = sys.stdout
        
        # Mock aiohttp for Telegram notification
        notification_sent = False
        notification_message = None
        
        class MockResponse:
            def __init__(self):
                self.status = 200
            
            async def text(self):
                return "OK"
            
            async def __aenter__(self):
                return self
            
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        class MockSession:
            def post(self, url, json=None, **kwargs):
                nonlocal notification_sent, notification_message
                if "sendMessage" in url:
                    notification_sent = True
                    notification_message = json.get("text", "") if json else ""
                return MockResponse()
            
            async def __aenter__(self):
                return self
            
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        try:
            # Redirect stdout to capture print statements
            sys.stdout = captured_output
            
            with patch('aiohttp.ClientSession', return_value=MockSession()):
                # Call safe_join_chat
                success, error_msg = await safe_join_chat(
                    client=mock_client,
                    chat_link="@testchat",
                    chat_db_id=1,
                    userbot_id=1,
                    pool_manager=mock_pool_manager,
                    delivery_bot_token="test_bot_token",
                    operator_chat_id=123456
                )
            
            # Get captured output
            console_output = captured_output.getvalue()
            
        finally:
            # Restore stdout
            sys.stdout = original_stdout
        
        # Expected behavior: Console warning should be printed
        console_warning_present = "FloodWait" in console_output and "3600" in console_output
        
        assert console_warning_present, (
            f"Console warning not found in output. "
            f"Captured output: '{console_output}'. "
            f"This confirms the FloodWait notification bug: the system does not "
            f"print an explicit warning to the console when FloodWait occurs. "
            f"Operators cannot see FloodWait errors in real-time."
        )
        
        # Expected behavior: Telegram notification should be sent
        assert notification_sent, (
            "Telegram notification was not sent. "
            "This confirms the FloodWait notification bug: the system does not "
            "send a Telegram notification to the operator when FloodWait occurs. "
            "Operators are not alerted about rate limiting issues."
        )
        
        # Verify notification content
        if notification_sent:
            assert "FloodWait" in notification_message, (
                f"Notification message does not contain 'FloodWait'. "
                f"Message: '{notification_message}'"
            )
            assert "3600" in notification_message or "60" in notification_message, (
                f"Notification message does not contain wait time. "
                f"Message: '{notification_message}'"
            )
        
        # Verify the function returned False (join failed)
        assert success is False, "Join should fail when FloodWait occurs"
        assert "FloodWait" in error_msg, f"Error message should mention FloodWait, got: {error_msg}"
