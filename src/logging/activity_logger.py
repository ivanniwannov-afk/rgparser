"""Activity logging for system events."""

import json
from datetime import datetime
from typing import Any, Optional
import aiosqlite

from database import DATABASE_FILE


class ActivityLogger:
    """Logger for system activity events."""
    
    @staticmethod
    async def log(
        component: str,
        level: str,
        message: str,
        metadata: Optional[dict[str, Any]] = None
    ) -> None:
        """
        Log an activity event.
        
        Args:
            component: Component name (e.g., "IngestionModule", "LLMVerifier")
            level: Log level ("INFO", "WARNING", "ERROR")
            message: Log message
            metadata: Optional metadata dictionary
        """
        try:
            if level not in ["INFO", "WARNING", "ERROR"]:
                raise ValueError(f"Invalid log level: {level}")
            
            metadata_json = json.dumps(metadata) if metadata else None
            
            async with aiosqlite.connect(DATABASE_FILE) as db:
                await db.execute(
                    """INSERT INTO activity_logs (component, level, message, metadata, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (component, level, message, metadata_json, datetime.now().isoformat())
                )
                await db.commit()
        except Exception as e:
            # Fail gracefully - print to console as fallback
            print(f"[ActivityLogger ERROR] Failed to log: {component} - {level} - {message}")
            print(f"[ActivityLogger ERROR] Exception: {type(e).__name__}: {e}")
    
    @staticmethod
    async def log_join_attempt(
        userbot_id: int,
        chat_link: str,
        success: bool,
        error_message: Optional[str] = None
    ) -> None:
        """Log a join attempt."""
        await ActivityLogger.log(
            component="IngestionModule",
            level="INFO" if success else "ERROR",
            message=f"Join attempt: {chat_link}",
            metadata={
                "userbot_id": userbot_id,
                "chat_link": chat_link,
                "success": success,
                "error_message": error_message
            }
        )
    
    @staticmethod
    async def log_llm_request(
        message_text: str,
        response: bool,
        duration_ms: float
    ) -> None:
        """Log an LLM API request."""
        await ActivityLogger.log(
            component="LLMVerifier",
            level="INFO",
            message=f"LLM verification: {'qualified' if response else 'not qualified'}",
            metadata={
                "message_preview": message_text[:100],
                "qualified": response,
                "duration_ms": duration_ms
            }
        )

    
    @staticmethod
    async def log_lead_delivery(
        sender_id: int,
        chat_title: str,
        message_preview: str
    ) -> None:
        """Log a lead delivery."""
        await ActivityLogger.log(
            component="DeliveryBot",
            level="INFO",
            message=f"Lead delivered from {chat_title}",
            metadata={
                "sender_id": sender_id,
                "chat_title": chat_title,
                "message_preview": message_preview[:100]
            }
        )
    
    @staticmethod
    async def log_error(
        component: str,
        error_message: str,
        exception: Optional[Exception] = None
    ) -> None:
        """Log an error."""
        metadata = {"error_message": error_message}
        if exception:
            metadata["exception_type"] = type(exception).__name__
            metadata["exception_str"] = str(exception)
        
        await ActivityLogger.log(
            component=component,
            level="ERROR",
            message=error_message,
            metadata=metadata
        )
