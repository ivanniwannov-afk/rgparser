"""Security restrictions for userbots."""

import logging
from typing import Any, Callable
from functools import wraps


logger = logging.getLogger(__name__)


class ReadOnlyViolationError(Exception):
    """Raised when attempting to perform write operation with userbot."""
    pass


def read_only_guard(func: Callable) -> Callable:
    """
    Decorator to block write operations on userbots.
    
    Logs warning and raises ReadOnlyViolationError if write operation attempted.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Check if this is a write operation
        func_name = func.__name__
        write_operations = [
            'send_message', 'send_photo', 'send_video', 'send_document',
            'edit_message', 'delete_message', 'forward_message',
            'send_reaction', 'set_chat_title', 'set_chat_photo',
            'pin_message', 'unpin_message', 'ban_chat_member',
            'unban_chat_member', 'restrict_chat_member', 'promote_chat_member'
        ]
        
        if func_name in write_operations:
            logger.warning(
                f"Blocked write operation attempt: {func_name}",
                extra={"operation": func_name, "args": args, "kwargs": kwargs}
            )
            raise ReadOnlyViolationError(
                f"Userbots are read-only. Operation '{func_name}' is not allowed."
            )
        
        return await func(*args, **kwargs)
    
    return wrapper


class ReadOnlyUserbot:
    """Wrapper for Pyrogram client to enforce read-only mode."""
    
    def __init__(self, client):
        """
        Initialize read-only userbot wrapper.
        
        Args:
            client: Pyrogram Client instance
        """
        self._client = client
    
    def __getattr__(self, name: str) -> Any:
        """Intercept attribute access to apply read-only guard."""
        attr = getattr(self._client, name)
        
        # If it's a callable method, wrap it with read-only guard
        if callable(attr):
            return read_only_guard(attr)
        
        return attr
    
    async def join_chat(self, chat_id: str):
        """Allow join_chat as it's a necessary operation."""
        return await self._client.join_chat(chat_id)
    
    async def get_chat(self, chat_id: int):
        """Allow get_chat as it's a read operation."""
        return await self._client.get_chat(chat_id)
    
    async def get_me(self):
        """Allow get_me as it's a read operation."""
        return await self._client.get_me()
