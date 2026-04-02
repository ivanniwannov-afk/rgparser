"""Join logic for safely joining Telegram chats with error handling.

This module implements the core logic for joining chats through userbots,
including error handling for FloodWait, bans, and antibot protection.

**Validates: Requirements 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 5.3, 5.4**
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple
from pyrogram import Client
from pyrogram.errors import (
    FloodWait,
    UserDeactivatedBan,
    ChannelPrivate,
    InviteRequestSent,
    UsernameInvalid,
    UsernameNotOccupied,
)
from pyrogram.types import Message
import aiosqlite

import database
from src.userbot.userbot_pool_manager import UserbotPoolManager


logger = logging.getLogger(__name__)


class JoinLogic:
    """Encapsulates join task execution logic.
    
    This class coordinates between the userbot pool and the safe_join_chat
    function to execute join tasks. It manages the retrieval of userbot clients
    and chat information, then delegates to safe_join_chat for the actual
    join operation with comprehensive error handling.
    
    **Validates: Requirements 2.1, 2.2, 2.3**
    """
    
    def __init__(self, pool_manager: UserbotPoolManager):
        """Initialize with userbot pool manager.
        
        Args:
            pool_manager: UserbotPoolManager instance for accessing userbots
        """
        self.pool_manager = pool_manager
    
    async def execute_join(self, userbot_id: int, chat_id: int) -> bool:
        """Execute a join task.
        
        This method retrieves the userbot client and chat information from the
        database, then calls safe_join_chat() to perform the actual join operation
        with comprehensive error handling.
        
        **Validates: Requirements 1.3, 2.3, 2.5, 3.1**
        
        Args:
            userbot_id: Database ID of the userbot to use
            chat_id: Database ID of the chat to join
        
        Returns:
            True if join succeeded, False otherwise
        """
        # 1. Get userbot client from pool manager
        client = await self.pool_manager.get_client(userbot_id)
        if not client:
            logger.error(f"Failed to get client for userbot {userbot_id}")
            
            # Update chat status to error with reset of userbot assignment
            await _update_chat_status(
                chat_id,
                "error",
                error_message="Failed to get userbot client",
                reset_userbot_assignment=True
            )
            
            return False
        
        # 2. Get chat information from database
        async with database.get_connection() as db:
            cursor = await db.execute(
                "SELECT chat_link FROM chats WHERE id = ?",
                (chat_id,)
            )
            row = await cursor.fetchone()
            if not row:
                logger.error(f"Chat {chat_id} not found in database")
                return False
            chat_link = row[0]
        
        # 3. Get configuration for notifications
        from config import config
        delivery_bot_token = config.get('bot_token', '')
        operator_chat_id = config.get('operator_chat_id', 0)
        
        # 4. Call safe_join_chat with all parameters
        success, error_message = await safe_join_chat(
            client=client,
            chat_link=chat_link,
            chat_db_id=chat_id,
            userbot_id=userbot_id,
            pool_manager=self.pool_manager,
            delivery_bot_token=delivery_bot_token if delivery_bot_token else None,
            operator_chat_id=operator_chat_id if operator_chat_id else None
        )
        
        return success


async def safe_join_chat(
    client: Client,
    chat_link: str,
    chat_db_id: int,
    userbot_id: int,
    pool_manager: UserbotPoolManager,
    delivery_bot_token: Optional[str] = None,
    operator_chat_id: Optional[int] = None,
) -> Tuple[bool, Optional[str]]:
    """Safely join a Telegram chat with comprehensive error handling.
    
    This function attempts to join a chat and handles various error conditions:
    - FloodWait: Marks userbot as unavailable and redistributes tasks
    - UserDeactivatedBan: Marks userbot as banned
    - Antibot protection: Attempts to automatically handle inline buttons
    - Approval required: Updates chat status to awaiting_approval
    
    **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 5.3, 5.4**
    
    Args:
        client: Pyrogram client instance for the userbot
        chat_link: Link to the chat (t.me/chatname or @username)
        chat_db_id: Database ID of the chat
        userbot_id: Database ID of the userbot
        pool_manager: UserbotPoolManager instance for managing userbot status
        delivery_bot_token: Optional bot token for sending notifications
        operator_chat_id: Optional operator chat ID for notifications
    
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    try:
        # Normalize chat link
        normalized_link = _normalize_chat_link(chat_link)
        
        # Attempt to join the chat
        logger.info(f"Userbot {userbot_id} attempting to join chat: {normalized_link}")
        chat = await client.join_chat(normalized_link)
        
        # Check for antibot protection
        antibot_handled = await _handle_antibot_protection(
            client, chat, userbot_id, delivery_bot_token, operator_chat_id
        )
        
        if not antibot_handled:
            # Antibot protection detected but couldn't be handled automatically
            await _update_chat_status(
                chat_db_id,
                "manual_required",
                error_message="Antibot protection requires manual handling",
                reset_userbot_assignment=True
            )
            
            # Send notification to operator
            if delivery_bot_token and operator_chat_id:
                await _send_manual_captcha_notification(
                    delivery_bot_token,
                    operator_chat_id,
                    chat_link,
                    userbot_id
                )
            
            logger.warning(
                f"Antibot protection on chat {chat_link} requires manual handling"
            )
            return False, "Antibot protection requires manual handling"
        
        # Successfully joined
        await _update_chat_status(
            chat_db_id,
            "active",
            chat_id_telegram=chat.id,
            chat_title=chat.title,
            joined_at=datetime.now(timezone.utc)
        )
        
        # Increment userbot's daily join counter
        await pool_manager.increment_joins_today(userbot_id)
        
        # Log success
        await _log_activity(
            "JoinLogic",
            "INFO",
            f"Successfully joined chat {chat.title} (ID: {chat.id})",
            {
                "userbot_id": userbot_id,
                "chat_id": chat.id,
                "chat_title": chat.title,
                "chat_link": chat_link
            }
        )
        
        logger.info(
            f"Userbot {userbot_id} successfully joined chat {chat.title} (ID: {chat.id})"
        )
        return True, None
    
    except FloodWait as e:
        # Handle FloodWait by marking userbot as unavailable
        logger.error(
            f"FloodWait error for userbot {userbot_id}: must wait {e.value} seconds"
        )
        
        # Add console warning for operator visibility
        print(f"🚨 FloodWait: userbot {userbot_id} must wait {e.value} seconds ({e.value/60:.1f} minutes)")
        
        await pool_manager.mark_unavailable(
            userbot_id,
            reason="floodwait",
            duration=e.value
        )
        
        # Redistribute tasks from this userbot
        await pool_manager.redistribute_tasks(userbot_id)
        
        # Update chat status to error and reset userbot assignment
        await _update_chat_status(
            chat_db_id,
            "error",
            error_message=f"FloodWait: {e.value}s",
            reset_userbot_assignment=True
        )
        
        # Send Telegram notification to operator
        if delivery_bot_token and operator_chat_id:
            await _send_floodwait_notification(
                delivery_bot_token,
                operator_chat_id,
                userbot_id,
                e.value
            )
        
        return False, f"FloodWait: {e.value}s"
    
    except UserDeactivatedBan:
        # Userbot is banned
        logger.error(f"Userbot {userbot_id} is banned (USER_DEACTIVATED_BAN)")
        
        # Mark userbot as banned in pool manager
        async with database.get_connection() as db:
            await db.execute(
                """UPDATE userbots
                   SET status = 'banned', updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (userbot_id,)
            )
            await db.commit()
        
        # Redistribute tasks
        await pool_manager.redistribute_tasks(userbot_id)
        
        # Update chat status and reset userbot assignment
        await _update_chat_status(
            chat_db_id,
            "error",
            error_message="Userbot is banned",
            reset_userbot_assignment=True
        )
        
        # Log and notify
        await _log_activity(
            "JoinLogic",
            "ERROR",
            f"Userbot {userbot_id} is banned",
            {"userbot_id": userbot_id}
        )
        
        return False, "Userbot is banned"
    
    except InviteRequestSent:
        # Join request sent, awaiting approval
        logger.info(f"Join request sent for chat {chat_link}, awaiting approval")
        
        await _update_chat_status(
            chat_db_id,
            "awaiting_approval",
            error_message="Awaiting administrator approval",
            reset_userbot_assignment=True
        )
        
        await _log_activity(
            "JoinLogic",
            "INFO",
            f"Join request sent for chat {chat_link}",
            {"userbot_id": userbot_id, "chat_link": chat_link}
        )
        
        return False, "Awaiting administrator approval"
    
    except (ChannelPrivate, UsernameInvalid, UsernameNotOccupied) as e:
        # Chat is private, invalid, or doesn't exist
        error_msg = f"Chat error: {type(e).__name__}"
        logger.error(f"Error joining chat {chat_link}: {error_msg}")
        
        await _update_chat_status(
            chat_db_id,
            "error",
            error_message=error_msg,
            reset_userbot_assignment=True
        )
        
        await _log_activity(
            "JoinLogic",
            "ERROR",
            f"Failed to join chat {chat_link}: {error_msg}",
            {"userbot_id": userbot_id, "chat_link": chat_link, "error": error_msg}
        )
        
        return False, error_msg
    
    except Exception as e:
        # Unexpected error
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"Unexpected error joining chat {chat_link}: {e}", exc_info=True)
        
        await _update_chat_status(
            chat_db_id,
            "error",
            error_message=error_msg,
            reset_userbot_assignment=True
        )
        
        await _log_activity(
            "JoinLogic",
            "ERROR",
            f"Unexpected error joining chat {chat_link}: {str(e)}",
            {"userbot_id": userbot_id, "chat_link": chat_link, "error": str(e)}
        )
        
        return False, error_msg


def _normalize_chat_link(chat_link: str) -> str:
    """Normalize a chat link to a format accepted by Pyrogram.
    
    Args:
        chat_link: Raw chat link (t.me/chatname, https://t.me/chatname, or @username)
    
    Returns:
        Normalized chat link
    """
    # If it's an invite link (contains /+ or /joinchat/), return as-is
    if "/+" in chat_link or "/joinchat/" in chat_link:
        return chat_link
    
    # Remove https:// or http://
    link = chat_link.replace("https://", "").replace("http://", "")
    
    # Remove t.me/ prefix if present
    if link.startswith("t.me/"):
        link = link[5:]
    
    # Add @ prefix if not present
    if not link.startswith("@"):
        link = f"@{link}"
    
    return link


async def _handle_antibot_protection(
    client: Client,
    chat,
    userbot_id: int,
    delivery_bot_token: Optional[str],
    operator_chat_id: Optional[int],
) -> bool:
    """Handle antibot protection by detecting and clicking inline buttons.
    
    **Validates: Requirements 5.1, 5.2, 5.3, 5.4**
    
    Args:
        client: Pyrogram client instance
        chat: Chat object that was just joined
        userbot_id: Database ID of the userbot
        delivery_bot_token: Optional bot token for notifications
        operator_chat_id: Optional operator chat ID for notifications
    
    Returns:
        True if no antibot protection or successfully handled,
        False if antibot protection requires manual handling
    """
    try:
        # Wait a moment for welcome messages to arrive
        await asyncio.sleep(2)
        
        # Get recent messages in the chat
        messages = []
        async for message in client.get_chat_history(chat.id, limit=5):
            messages.append(message)
        
        # Look for messages with inline keyboards (antibot buttons)
        for message in messages:
            if message.reply_markup and hasattr(message.reply_markup, 'inline_keyboard'):
                # Found a message with inline keyboard
                logger.info(
                    f"Detected antibot protection in chat {chat.title} (ID: {chat.id})"
                )
                
                await _log_activity(
                    "JoinLogic",
                    "INFO",
                    f"Antibot protection detected in chat {chat.title}",
                    {
                        "userbot_id": userbot_id,
                        "chat_id": chat.id,
                        "chat_title": chat.title
                    }
                )
                
                # Try to click the first button
                try:
                    keyboard = message.reply_markup.inline_keyboard
                    if keyboard and len(keyboard) > 0 and len(keyboard[0]) > 0:
                        button = keyboard[0][0]
                        
                        # Click the button
                        await client.request_callback_answer(
                            chat.id,
                            message.id,
                            callback_data=button.callback_data
                        )
                        
                        logger.info(
                            f"Clicked antibot button in chat {chat.title}"
                        )
                        
                        await _log_activity(
                            "JoinLogic",
                            "INFO",
                            f"Successfully clicked antibot button in chat {chat.title}",
                            {
                                "userbot_id": userbot_id,
                                "chat_id": chat.id,
                                "chat_title": chat.title
                            }
                        )
                        
                        # Wait 2 seconds to confirm successful handling (sufficient for button click verification)
                        await asyncio.sleep(2)
                        
                        return True
                    else:
                        # No buttons found, requires manual handling
                        logger.warning(
                            f"Antibot protection in chat {chat.title} has no clickable buttons"
                        )
                        return False
                
                except Exception as e:
                    # Failed to click button
                    logger.error(
                        f"Failed to click antibot button in chat {chat.title}: {e}"
                    )
                    
                    await _log_activity(
                        "JoinLogic",
                        "WARNING",
                        f"Failed to handle antibot protection in chat {chat.title}: {str(e)}",
                        {
                            "userbot_id": userbot_id,
                            "chat_id": chat.id,
                            "chat_title": chat.title,
                            "error": str(e)
                        }
                    )
                    
                    return False
        
        # No antibot protection detected
        return True
    
    except Exception as e:
        logger.error(f"Error checking for antibot protection: {e}", exc_info=True)
        # Assume no antibot protection if we can't check
        return True


async def _send_manual_captcha_notification(
    bot_token: str,
    operator_chat_id: int,
    chat_link: str,
    userbot_id: int,
) -> None:
    """Send notification to operator about manual captcha requirement.
    
    Uses HTTP API instead of Pyrogram Client to avoid session file locks.
    
    **Validates: Requirement 5.4, 2.9**
    
    Args:
        bot_token: Telegram bot token
        operator_chat_id: Operator's chat ID
        chat_link: Link to the chat requiring manual handling
        userbot_id: Database ID of the userbot
    """
    try:
        import aiohttp
        
        # Get userbot session file name
        async with database.get_connection() as db:
            cursor = await db.execute(
                "SELECT session_file FROM userbots WHERE id = ?",
                (userbot_id,)
            )
            row = await cursor.fetchone()
            session_file = row[0] if row else f"userbot-{userbot_id}"
        
        # Create message with exact format specified
        message = (
            f"⚠️ Требуется ручная капча! Чат: {chat_link}\n"
            f"Юзербот: {session_file}"
        )
        
        # Send notification via HTTP API (avoids session file locks)
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": operator_chat_id,
            "text": message
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Failed to send captcha notification: {error_text}")
                else:
                    logger.info(f"Sent manual captcha notification for chat {chat_link}")
    
    except Exception as e:
        logger.error(f"Failed to send manual captcha notification: {e}", exc_info=True)


async def _send_floodwait_notification(
    bot_token: str,
    operator_chat_id: int,
    userbot_id: int,
    wait_seconds: int
) -> None:
    """Send notification to operator about FloodWait error.
    
    Uses HTTP API instead of Pyrogram Client to avoid session file locks.
    
    **Validates: Requirement 2.12**
    
    Args:
        bot_token: Telegram bot token
        operator_chat_id: Operator's chat ID
        userbot_id: Database ID of the userbot
        wait_seconds: Number of seconds to wait
    """
    try:
        import aiohttp
        
        # Get userbot session file name
        async with database.get_connection() as db:
            cursor = await db.execute(
                "SELECT session_file FROM userbots WHERE id = ?",
                (userbot_id,)
            )
            row = await cursor.fetchone()
            session_file = row[0] if row else f"userbot-{userbot_id}"
        
        # Create message
        message = (
            f"⚠️ FloodWait: {session_file}\n"
            f"Ожидание: {wait_seconds} секунд ({wait_seconds/60:.1f} минут)"
        )
        
        # Send notification via HTTP API (avoids session file locks)
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": operator_chat_id,
            "text": message
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Failed to send FloodWait notification: {error_text}")
                else:
                    logger.info(f"Sent FloodWait notification for userbot {userbot_id}")
    
    except Exception as e:
        logger.error(f"Failed to send FloodWait notification: {e}", exc_info=True)


async def _update_chat_status(
    chat_db_id: int,
    status: str,
    error_message: Optional[str] = None,
    chat_id_telegram: Optional[int] = None,
    chat_title: Optional[str] = None,
    joined_at: Optional[datetime] = None,
    reset_userbot_assignment: bool = False,
) -> None:
    """Update chat status in the database.
    
    **Validates: Requirements 4.2, 4.3, 2.4**
    
    Args:
        chat_db_id: Database ID of the chat
        status: New status (pending, active, error, awaiting_approval, manual_required)
        error_message: Optional error message
        chat_id_telegram: Optional Telegram chat ID
        chat_title: Optional chat title
        joined_at: Optional join timestamp
        reset_userbot_assignment: If True, reset assigned_userbot_id to NULL
    """
    async with database.get_connection() as db:
        # Build update query dynamically
        updates = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
        params = [status]
        
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)
        
        if chat_id_telegram is not None:
            updates.append("chat_id = ?")
            params.append(chat_id_telegram)
        
        if chat_title is not None:
            updates.append("chat_title = ?")
            params.append(chat_title)
        
        if joined_at is not None:
            updates.append("joined_at = ?")
            params.append(joined_at.isoformat())
        
        if reset_userbot_assignment:
            updates.append("assigned_userbot_id = NULL")
        
        params.append(chat_db_id)
        
        query = f"UPDATE chats SET {', '.join(updates)} WHERE id = ?"
        
        await db.execute(query, params)
        await db.commit()


async def _log_activity(
    component: str,
    level: str,
    message: str,
    metadata: Optional[dict] = None,
) -> None:
    """Log activity to the database.
    
    Args:
        component: Component name
        level: Log level (INFO, WARNING, ERROR)
        message: Log message
        metadata: Optional metadata dict
    """
    import json
    
    async with database.get_connection() as db:
        await db.execute(
            """INSERT INTO activity_logs (component, level, message, metadata, created_at)
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (component, level, message, json.dumps(metadata) if metadata else None)
        )
        await db.commit()
