"""Test that activity logs are properly written to the database.

This test verifies:
1. The activity_logs table schema is correct
2. Logs are actually written to the database
3. All fields (component, level, message, metadata, created_at) are properly stored
4. End-to-end logging functionality works
"""

import pytest
import aiosqlite
import json
from datetime import datetime
from pathlib import Path

from database import DATABASE_FILE


@pytest.mark.asyncio
async def test_activity_logs_table_schema():
    """Test that activity_logs table has the correct schema in the main database."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        # Get table info
        cursor = await db.execute("PRAGMA table_info(activity_logs)")
        columns = await cursor.fetchall()
        
        # Convert to dict for easier checking
        column_dict = {col[1]: col[2] for col in columns}  # name: type
        
        # Verify all required columns exist
        assert "id" in column_dict
        assert "component" in column_dict
        assert "level" in column_dict
        assert "message" in column_dict
        assert "metadata" in column_dict
        assert "created_at" in column_dict
        
        # Verify types
        assert column_dict["id"] == "INTEGER"
        assert column_dict["component"] == "TEXT"
        assert column_dict["level"] == "TEXT"
        assert column_dict["message"] == "TEXT"
        assert column_dict["metadata"] == "JSON"
        assert column_dict["created_at"] == "TIMESTAMP"


@pytest.mark.asyncio
async def test_activity_logs_index_exists():
    """Test that the activity_logs index exists."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_logs_component_created'"
        )
        result = await cursor.fetchone()
        
        assert result is not None, "Index idx_logs_component_created should exist"



@pytest.mark.asyncio
async def test_basic_log_write():
    """Test that a basic log entry can be written to the database."""
    # Write a test log
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute(
            """INSERT INTO activity_logs (component, level, message, metadata, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            ("TestComponentBasic", "INFO", "Test message for schema verification", None, datetime.now().isoformat())
        )
        await db.commit()
        
        # Verify it was written
        cursor = await db.execute(
            "SELECT component, level, message, metadata FROM activity_logs WHERE component = 'TestComponentBasic'"
        )
        row = await cursor.fetchone()
        
        assert row is not None
        assert row[0] == "TestComponentBasic"
        assert row[1] == "INFO"
        assert row[2] == "Test message for schema verification"
        assert row[3] is None
        
        # Clean up
        await db.execute("DELETE FROM activity_logs WHERE component = 'TestComponentBasic'")
        await db.commit()


@pytest.mark.asyncio
async def test_log_with_metadata():
    """Test that logs with metadata are properly stored."""
    metadata = {
        "user_id": 12345,
        "action": "test_action",
        "details": {"key": "value"}
    }
    
    metadata_json = json.dumps(metadata)
    
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute(
            """INSERT INTO activity_logs (component, level, message, metadata, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            ("TestMetadata", "WARNING", "Test with metadata", metadata_json, datetime.now().isoformat())
        )
        await db.commit()
        
        # Verify
        cursor = await db.execute(
            "SELECT component, level, message, metadata FROM activity_logs WHERE component = 'TestMetadata'"
        )
        row = await cursor.fetchone()
        
        assert row[0] == "TestMetadata"
        assert row[1] == "WARNING"
        assert row[2] == "Test with metadata"
        
        # Parse and verify metadata
        stored_metadata = json.loads(row[3])
        assert stored_metadata == metadata
        
        # Clean up
        await db.execute("DELETE FROM activity_logs WHERE component = 'TestMetadata'")
        await db.commit()



@pytest.mark.asyncio
async def test_all_log_levels():
    """Test that all log levels (INFO, WARNING, ERROR) work."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute(
            """INSERT INTO activity_logs (component, level, message, created_at)
               VALUES (?, ?, ?, ?)""",
            ("TestLevels1", "INFO", "Info message", datetime.now().isoformat())
        )
        await db.execute(
            """INSERT INTO activity_logs (component, level, message, created_at)
               VALUES (?, ?, ?, ?)""",
            ("TestLevels2", "WARNING", "Warning message", datetime.now().isoformat())
        )
        await db.execute(
            """INSERT INTO activity_logs (component, level, message, created_at)
               VALUES (?, ?, ?, ?)""",
            ("TestLevels3", "ERROR", "Error message", datetime.now().isoformat())
        )
        await db.commit()
        
        # Verify
        cursor = await db.execute(
            "SELECT level FROM activity_logs WHERE component LIKE 'TestLevels%' ORDER BY component"
        )
        rows = await cursor.fetchall()
        
        assert len(rows) == 3
        assert rows[0][0] == "INFO"
        assert rows[1][0] == "WARNING"
        assert rows[2][0] == "ERROR"
        
        # Clean up
        await db.execute("DELETE FROM activity_logs WHERE component LIKE 'TestLevels%'")
        await db.commit()


@pytest.mark.asyncio
async def test_created_at_timestamp_format():
    """Test that created_at timestamps are properly formatted."""
    before = datetime.now()
    
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute(
            """INSERT INTO activity_logs (component, level, message, created_at)
               VALUES (?, ?, ?, ?)""",
            ("TestTimestamp", "INFO", "Test timestamp", datetime.now().isoformat())
        )
        await db.commit()
        
        cursor = await db.execute(
            "SELECT created_at FROM activity_logs WHERE component = 'TestTimestamp'"
        )
        row = await cursor.fetchone()
        
        # Parse the timestamp
        created_at = datetime.fromisoformat(row[0])
        
        after = datetime.now()
        
        # Verify it's within the expected range
        assert before <= created_at <= after
        
        # Clean up
        await db.execute("DELETE FROM activity_logs WHERE component = 'TestTimestamp'")
        await db.commit()



@pytest.mark.asyncio
async def test_activity_logger_integration():
    """Test that ActivityLogger properly writes to the database."""
    from src.logging.activity_logger import ActivityLogger
    
    # Test basic log
    await ActivityLogger.log(
        component="IntegrationTest",
        level="INFO",
        message="Integration test message"
    )
    
    # Verify it was written
    async with aiosqlite.connect(DATABASE_FILE) as db:
        cursor = await db.execute(
            "SELECT component, level, message FROM activity_logs WHERE component = 'IntegrationTest'"
        )
        row = await cursor.fetchone()
        
        assert row is not None
        assert row[0] == "IntegrationTest"
        assert row[1] == "INFO"
        assert row[2] == "Integration test message"
        
        # Clean up
        await db.execute("DELETE FROM activity_logs WHERE component = 'IntegrationTest'")
        await db.commit()


@pytest.mark.asyncio
async def test_activity_logger_with_metadata():
    """Test that ActivityLogger properly stores metadata."""
    from src.logging.activity_logger import ActivityLogger
    
    metadata = {"test_key": "test_value", "number": 42}
    
    await ActivityLogger.log(
        component="MetadataTest",
        level="WARNING",
        message="Test with metadata",
        metadata=metadata
    )
    
    # Verify
    async with aiosqlite.connect(DATABASE_FILE) as db:
        cursor = await db.execute(
            "SELECT metadata FROM activity_logs WHERE component = 'MetadataTest'"
        )
        row = await cursor.fetchone()
        
        assert row is not None
        stored_metadata = json.loads(row[0])
        assert stored_metadata == metadata
        
        # Clean up
        await db.execute("DELETE FROM activity_logs WHERE component = 'MetadataTest'")
        await db.commit()


@pytest.mark.asyncio
async def test_activity_logger_log_join_attempt():
    """Test log_join_attempt functionality."""
    from src.logging.activity_logger import ActivityLogger
    
    await ActivityLogger.log_join_attempt(
        userbot_id=999,
        chat_link="https://t.me/testchat",
        success=True
    )
    
    # Verify
    async with aiosqlite.connect(DATABASE_FILE) as db:
        cursor = await db.execute(
            """SELECT component, level, message, metadata 
               FROM activity_logs 
               WHERE component = 'IngestionModule' 
               AND message LIKE '%Join attempt%'
               ORDER BY id DESC LIMIT 1"""
        )
        row = await cursor.fetchone()
        
        assert row is not None
        assert row[0] == "IngestionModule"
        assert row[1] == "INFO"
        
        metadata = json.loads(row[3])
        assert metadata["userbot_id"] == 999
        assert metadata["chat_link"] == "https://t.me/testchat"
        assert metadata["success"] is True
        
        # Clean up
        await db.execute(
            "DELETE FROM activity_logs WHERE component = 'IngestionModule' AND message LIKE '%Join attempt%'"
        )
        await db.commit()



@pytest.mark.asyncio
async def test_activity_logger_log_error():
    """Test log_error functionality."""
    from src.logging.activity_logger import ActivityLogger
    
    test_exception = ValueError("Test error")
    
    await ActivityLogger.log_error(
        component="ErrorTest",
        error_message="Something went wrong",
        exception=test_exception
    )
    
    # Verify
    async with aiosqlite.connect(DATABASE_FILE) as db:
        cursor = await db.execute(
            "SELECT component, level, message, metadata FROM activity_logs WHERE component = 'ErrorTest'"
        )
        row = await cursor.fetchone()
        
        assert row is not None
        assert row[0] == "ErrorTest"
        assert row[1] == "ERROR"
        assert row[2] == "Something went wrong"
        
        metadata = json.loads(row[3])
        assert metadata["error_message"] == "Something went wrong"
        assert metadata["exception_type"] == "ValueError"
        assert metadata["exception_str"] == "Test error"
        
        # Clean up
        await db.execute("DELETE FROM activity_logs WHERE component = 'ErrorTest'")
        await db.commit()


@pytest.mark.asyncio
async def test_invalid_log_level_constraint():
    """Test that invalid log levels are rejected by database constraint."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                """INSERT INTO activity_logs (component, level, message, created_at)
                   VALUES (?, ?, ?, ?)""",
                ("TestInvalid", "DEBUG", "Should fail", datetime.now().isoformat())
            )
            await db.commit()
