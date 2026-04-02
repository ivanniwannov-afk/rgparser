"""Tests for ActivityLogger error handling."""

import pytest
import asyncio
from unittest.mock import patch, AsyncMock
from src.logging.activity_logger import ActivityLogger


@pytest.mark.asyncio
async def test_log_handles_database_error(capsys):
    """Test that log() handles database errors gracefully."""
    # Mock aiosqlite.connect to raise an exception
    with patch('src.logging.activity_logger.aiosqlite.connect', side_effect=Exception("Database connection failed")):
        # This should not raise an exception
        await ActivityLogger.log(
            component="TestComponent",
            level="INFO",
            message="Test message"
        )
    
    # Check that error was printed to console
    captured = capsys.readouterr()
    assert "[ActivityLogger ERROR] Failed to log: TestComponent - INFO - Test message" in captured.out
    assert "Exception: Exception: Database connection failed" in captured.out


@pytest.mark.asyncio
async def test_log_join_attempt_handles_error(capsys):
    """Test that log_join_attempt() handles errors gracefully."""
    with patch('src.logging.activity_logger.aiosqlite.connect', side_effect=Exception("Database error")):
        # This should not raise an exception
        await ActivityLogger.log_join_attempt(
            userbot_id=1,
            chat_link="https://t.me/testchat",
            success=True
        )
    
    # Check that error was printed to console (from base log() method)
    captured = capsys.readouterr()
    assert "[ActivityLogger ERROR] Failed to log: IngestionModule - INFO - Join attempt: https://t.me/testchat" in captured.out
    assert "Exception: Exception: Database error" in captured.out


@pytest.mark.asyncio
async def test_log_llm_request_handles_error(capsys):
    """Test that log_llm_request() handles errors gracefully."""
    with patch('src.logging.activity_logger.aiosqlite.connect', side_effect=Exception("Database error")):
        # This should not raise an exception
        await ActivityLogger.log_llm_request(
            message_text="Test message",
            response=True,
            duration_ms=100.5
        )
    
    # Check that error was printed to console (from base log() method)
    captured = capsys.readouterr()
    assert "[ActivityLogger ERROR] Failed to log: LLMVerifier - INFO - LLM verification: qualified" in captured.out
    assert "Exception: Exception: Database error" in captured.out


@pytest.mark.asyncio
async def test_log_lead_delivery_handles_error(capsys):
    """Test that log_lead_delivery() handles errors gracefully."""
    with patch('src.logging.activity_logger.aiosqlite.connect', side_effect=Exception("Database error")):
        # This should not raise an exception
        await ActivityLogger.log_lead_delivery(
            sender_id=123,
            chat_title="Test Chat",
            message_preview="Test message preview"
        )
    
    # Check that error was printed to console (from base log() method)
    captured = capsys.readouterr()
    assert "[ActivityLogger ERROR] Failed to log: DeliveryBot - INFO - Lead delivered from Test Chat" in captured.out
    assert "Exception: Exception: Database error" in captured.out


@pytest.mark.asyncio
async def test_log_error_handles_error(capsys):
    """Test that log_error() handles errors gracefully."""
    with patch('src.logging.activity_logger.aiosqlite.connect', side_effect=Exception("Database error")):
        # This should not raise an exception
        await ActivityLogger.log_error(
            component="TestComponent",
            error_message="Test error message",
            exception=ValueError("Test exception")
        )
    
    # Check that error was printed to console (from base log() method)
    captured = capsys.readouterr()
    assert "[ActivityLogger ERROR] Failed to log: TestComponent - ERROR - Test error message" in captured.out
    assert "Exception: Exception: Database error" in captured.out


@pytest.mark.asyncio
async def test_log_handles_json_serialization_error(capsys):
    """Test that log() handles JSON serialization errors gracefully."""
    # Create metadata that cannot be serialized to JSON
    class UnserializableObject:
        pass
    
    with patch('src.logging.activity_logger.json.dumps', side_effect=TypeError("Object not serializable")):
        # This should not raise an exception
        await ActivityLogger.log(
            component="TestComponent",
            level="INFO",
            message="Test message",
            metadata={"obj": UnserializableObject()}
        )
    
    # Check that error was printed to console
    captured = capsys.readouterr()
    assert "[ActivityLogger ERROR] Failed to log: TestComponent - INFO - Test message" in captured.out
    assert "TypeError" in captured.out
