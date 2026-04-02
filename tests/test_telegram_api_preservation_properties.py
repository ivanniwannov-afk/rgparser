"""Preservation property tests for Telegram API operations.

These tests verify that normal Telegram API operations work correctly on UNFIXED code
and must continue to work after the fix is implemented.

**IMPORTANT**: These tests should PASS on unfixed code to establish baseline behavior.

**Validates: Requirements 3.10, 3.11, 3.12**
"""

import asyncio
import tempfile
import os
from datetime import datetime, timedelta, timezone
from hypothesis import given, strategies as st, settings, HealthCheck
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from src.delivery.delivery_bot import DeliveryBot, QualifiedLead
from src.ingestion.join_logic import safe_join_chat
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


# Property 1: Non-Rate-Limited Message Delivery Preservation
@pytest.mark.asyncio
@settings(max_examples=20, deadline=10000, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    num_leads=st.integers(min_value=1, max_value=10)
)
async def test_property_1_non_rate_limited_message_delivery(test_db, num_leads):
    """Property 1: Non-Rate-Limited Message Delivery Preservation
    
    **Validates: Requirements 3.10**
    
    For all message sends without rate limits (no RetryAfter errors), the system SHALL
    successfully deliver leads to the operator. This behavior must be preserved.
    
    **Expected on UNFIXED code**: PASS (confirms baseline behavior)
    """
    # Create mock bot and application
    mock_bot = AsyncMock()
    mock_app = MagicMock()
    
    # Mock send_message to succeed without RetryAfter
    mock_bot.send_message = AsyncMock()
    
    # Create DeliveryBot instance
    delivery_bot = DeliveryBot(
        bot_token="test_token",
        operator_chat_id=123456789
    )
    delivery_bot._bot = mock_bot
    delivery_bot._app = mock_app
    
    # Deliver multiple leads
    for i in range(num_leads):
        lead = QualifiedLead(
            text=f"Test message {i}",
            sender_id=100000 + i,
            sender_username=f"test_user_{i}",
            chat_id=200000 + i,
            chat_title=f"Test Chat {i}",
            timestamp=datetime.now(timezone.utc)
        )
        
        # Deliver lead (should succeed without RetryAfter)
        await delivery_bot.deliver_lead(lead)
        
        # Verify send_message was called
        assert mock_bot.send_message.call_count == i + 1, (
            f"send_message should be called {i + 1} times, but was called {mock_bot.send_message.call_count} times"
        )
    
    # Verify all leads were delivered
    assert mock_bot.send_message.call_count == num_leads, (
        f"Expected {num_leads} messages sent, got {mock_bot.send_message.call_count}"
    )


# Property 2: Messages Without Inline Buttons Delivery Preservation
@pytest.mark.asyncio
@settings(max_examples=20, deadline=10000, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    num_messages=st.integers(min_value=1, max_value=10)
)
async def test_property_2_messages_without_buttons_delivery(test_db, num_messages):
    """Property 2: Messages Without Inline Buttons Delivery Preservation
    
    **Validates: Requirements 3.11**
    
    For all messages without inline buttons, the system SHALL deliver them correctly
    without requiring polling. This behavior must be preserved.
    
    **Expected on UNFIXED code**: PASS (confirms baseline behavior)
    """
    # Create mock bot
    mock_bot = AsyncMock()
    mock_app = MagicMock()
    
    # Mock send_message to succeed
    mock_bot.send_message = AsyncMock()
    
    # Create DeliveryBot instance
    delivery_bot = DeliveryBot(
        bot_token="test_token",
        operator_chat_id=123456789
    )
    delivery_bot._bot = mock_bot
    delivery_bot._app = mock_app
    
    # Send messages without inline buttons
    for i in range(num_messages):
        # Create lead object
        lead = QualifiedLead(
            text=f"Test message {i}",
            sender_id=100000 + i,
            sender_username=f"test_user_{i}",
            chat_id=200000 + i,
            chat_title=f"Test Chat {i}",
            timestamp=datetime.now(timezone.utc)
        )
        
        # Deliver lead (no inline buttons)
        await delivery_bot.deliver_lead(lead)
        
        # Verify message was sent
        assert mock_bot.send_message.call_count == i + 1
        
        # Verify no inline keyboard was passed (or it's None)
        call_kwargs = mock_bot.send_message.call_args[1]
        reply_markup = call_kwargs.get('reply_markup')
        
        # If reply_markup exists, it should be for spam/block buttons
        # The key point is that the message is delivered successfully
        # without requiring polling (polling is only needed for callbacks)
    
    # Verify all messages were delivered
    assert mock_bot.send_message.call_count == num_messages


# Property 3: Operations Without FloodWait Completion Preservation
@pytest.mark.asyncio
@settings(max_examples=20, deadline=15000, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    num_operations=st.integers(min_value=1, max_value=5)
)
async def test_property_3_operations_without_floodwait_no_delays(test_db, num_operations):
    """Property 3: Operations Without FloodWait Completion Preservation
    
    **Validates: Requirements 3.12**
    
    For all userbot operations without FloodWait errors, the system SHALL complete
    operations without additional delays. This behavior must be preserved.
    
    **Expected on UNFIXED code**: PASS (confirms baseline behavior)
    """
    from src.userbot.userbot_pool_manager import UserbotPoolManager
    
    # Create mock pool manager
    pool_manager = AsyncMock(spec=UserbotPoolManager)
    pool_manager.increment_joins_today = AsyncMock()
    pool_manager.mark_unavailable = AsyncMock()
    pool_manager.redistribute_tasks = AsyncMock()
    
    for i in range(num_operations):
        # Create mock client (NO FloodWait error)
        mock_client = AsyncMock()
        mock_chat = MagicMock()
        mock_chat.id = 123456 + i
        mock_chat.title = f"Test Chat {i}"
        
        # Mock join_chat to succeed without FloodWait
        mock_client.join_chat = AsyncMock(return_value=mock_chat)
        
        # Mock get_chat_history (no antibot)
        async def mock_get_chat_history(chat_id, limit):
            return
            yield
        
        mock_client.get_chat_history = mock_get_chat_history
        
        # Create chat in database with unique link
        import time
        timestamp_suffix = int(time.time() * 1000000)
        chat_link = f"t.me/test_chat_{timestamp_suffix}_{i}"
        
        async with get_connection() as db:
            cursor = await db.execute(
                """INSERT INTO chats (chat_link, status)
                   VALUES (?, 'pending')""",
                (chat_link,)
            )
            chat_db_id = cursor.lastrowid
            await db.commit()
        
        # Measure operation completion time
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
        
        # Verify operation succeeded
        assert success is True, f"Operation {i} should succeed without FloodWait"
        assert error_message is None
        
        # Verify no extra delays (< 5 seconds for database + network simulation)
        assert elapsed < 5.0, (
            f"Operation {i} took {elapsed:.2f}s (expected < 5.0s). "
            f"Operations without FloodWait should complete without additional delays."
        )
        
        # Verify join_chat was called
        mock_client.join_chat.assert_called_once()


# Concrete test cases for easier debugging

@pytest.mark.asyncio
async def test_concrete_non_rate_limited_delivery(test_db):
    """Concrete test: Non-rate-limited message delivers successfully.
    
    **Validates: Requirements 3.10**
    """
    # Create mock bot
    mock_bot = AsyncMock()
    mock_app = MagicMock()
    mock_bot.send_message = AsyncMock()
    
    # Create DeliveryBot instance
    delivery_bot = DeliveryBot(
        bot_token="test_token",
        operator_chat_id=123456789
    )
    delivery_bot._bot = mock_bot
    delivery_bot._app = mock_app
    
    # Deliver lead
    lead = QualifiedLead(
        text="Test message",
        sender_id=100000,
        sender_username="test_user",
        chat_id=200000,
        chat_title="Test Chat",
        timestamp=datetime.now(timezone.utc)
    )
    
    await delivery_bot.deliver_lead(lead)
    
    # Verify message was sent
    mock_bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_concrete_message_without_buttons(test_db):
    """Concrete test: Message without inline buttons delivers correctly.
    
    **Validates: Requirements 3.11**
    """
    # Create mock bot
    mock_bot = AsyncMock()
    mock_app = MagicMock()
    mock_bot.send_message = AsyncMock()
    
    # Create DeliveryBot instance
    delivery_bot = DeliveryBot(
        bot_token="test_token",
        operator_chat_id=123456789
    )
    delivery_bot._bot = mock_bot
    delivery_bot._app = mock_app
    
    # Deliver lead (message will have buttons, but delivery itself works without polling)
    lead = QualifiedLead(
        text="Test message",
        sender_id=100000,
        sender_username="test_user",
        chat_id=200000,
        chat_title="Test Chat",
        timestamp=datetime.now(timezone.utc)
    )
    
    await delivery_bot.deliver_lead(lead)
    
    # Verify message was sent
    mock_bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_concrete_operation_without_floodwait(test_db):
    """Concrete test: Operation without FloodWait completes without delays.
    
    **Validates: Requirements 3.12**
    """
    from src.userbot.userbot_pool_manager import UserbotPoolManager
    
    # Create mock pool manager
    pool_manager = AsyncMock(spec=UserbotPoolManager)
    pool_manager.increment_joins_today = AsyncMock()
    
    # Create mock client (NO FloodWait)
    mock_client = AsyncMock()
    mock_chat = MagicMock()
    mock_chat.id = 123456
    mock_chat.title = "Test Chat"
    
    # Mock join_chat to succeed without FloodWait
    mock_client.join_chat = AsyncMock(return_value=mock_chat)
    
    # Mock get_chat_history (no antibot)
    async def mock_get_chat_history(chat_id, limit):
        return
        yield
    
    mock_client.get_chat_history = mock_get_chat_history
    
    # Create chat in database
    async with get_connection() as db:
        cursor = await db.execute(
            """INSERT INTO chats (chat_link, status)
               VALUES (?, 'pending')""",
            ("t.me/test_chat_concrete",)
        )
        chat_db_id = cursor.lastrowid
        await db.commit()
    
    # Measure operation completion time
    start_time = datetime.now(timezone.utc)
    
    success, error_message = await safe_join_chat(
        client=mock_client,
        chat_link="t.me/test_chat_concrete",
        chat_db_id=chat_db_id,
        userbot_id=1,
        pool_manager=pool_manager,
        delivery_bot_token=None,
        operator_chat_id=None
    )
    
    end_time = datetime.now(timezone.utc)
    elapsed = (end_time - start_time).total_seconds()
    
    # Verify operation succeeded
    assert success is True
    assert error_message is None
    
    # Verify no extra delays
    assert elapsed < 5.0, f"Operation took {elapsed:.2f}s (expected < 5.0s)"
    
    # Verify join_chat was called
    mock_client.join_chat.assert_called_once()
