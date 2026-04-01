"""Message parser for real-time Telegram message monitoring."""

import asyncio
import hashlib
import re
from datetime import datetime, timedelta
from typing import Optional
import emoji
import aiosqlite
from pyrogram import Client, filters
from pyrogram.types import Message as PyrogramMessage

from database import DATABASE_FILE


class Message:
    """Parsed message data."""
    
    def __init__(
        self,
        text: str,
        sender_id: int,
        sender_username: Optional[str],
        chat_id: int,
        chat_title: str,
        timestamp: datetime
    ):
        self.text = text
        self.sender_id = sender_id
        self.sender_username = sender_username
        self.chat_id = chat_id
        self.chat_title = chat_title
        self.timestamp = timestamp


def normalize_text(text: str) -> str:
    """
    Normalize text for deduplication hashing.
    Removes URLs, emojis, special characters, and whitespace.
    """
    # Remove URLs
    text = re.sub(r'http[s]?://\S+', '', text)
    text = re.sub(r'www\.\S+', '', text)
    
    # Remove emojis
    text = emoji.replace_emoji(text, '')
    
    # Remove special characters and whitespace
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', '', text)
    
    return text.lower()



class MessageParser:
    """Parser for monitoring Telegram messages in real-time."""
    
    def __init__(self, trigger_words: list[str], on_message_callback):
        """
        Initialize message parser.
        
        Args:
            trigger_words: List of trigger words for filtering
            on_message_callback: Async callback function(message: Message) -> None
        """
        self.trigger_words = [word.lower() for word in trigger_words]
        self.on_message_callback = on_message_callback
        self._subscribed_chats: set[int] = set()
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def subscribe_to_chat(self, chat_id: int) -> None:
        """Subscribe to messages from a chat."""
        self._subscribed_chats.add(chat_id)
    
    async def unsubscribe_from_chat(self, chat_id: int) -> None:
        """Unsubscribe from messages from a chat."""
        self._subscribed_chats.discard(chat_id)
    
    def is_subscribed(self, chat_id: int) -> bool:
        """Check if subscribed to a chat."""
        return chat_id in self._subscribed_chats

    
    async def handle_new_message(self, message: PyrogramMessage) -> None:
        """
        Handle incoming Telegram message.
        
        Args:
            message: Pyrogram message object
        """
        # Extract message data
        if not message.text:
            return
        
        # Check if from subscribed chat
        if message.chat.id not in self._subscribed_chats:
            return
        
        # Check trigger words
        if not self.check_trigger_words(message.text):
            return
        
        # Check for duplicates
        if await self.deduplicate(message.text):
            return  # Duplicate found, skip
        
        # Parse message
        parsed_message = Message(
            text=message.text,
            sender_id=message.from_user.id if message.from_user else 0,
            sender_username=message.from_user.username if message.from_user else None,
            chat_id=message.chat.id,
            chat_title=message.chat.title or "Unknown",
            timestamp=message.date or datetime.now()
        )
        
        # Pass to callback
        await self.on_message_callback(parsed_message)

    
    def check_trigger_words(self, text: str) -> bool:
        """
        Check if message contains any trigger words (case-insensitive).
        
        Args:
            text: Message text
            
        Returns:
            True if contains trigger word, False otherwise
        """
        text_lower = text.lower()
        return any(trigger in text_lower for trigger in self.trigger_words)
    
    async def deduplicate(self, text: str) -> bool:
        """
        Check if message is a duplicate within 24 hours.
        
        Args:
            text: Message text
            
        Returns:
            True if duplicate, False if unique
        """
        # Normalize and hash
        normalized = normalize_text(text)
        msg_hash = hashlib.sha256(normalized.encode()).hexdigest()
        
        # Check in database
        async with aiosqlite.connect(DATABASE_FILE) as db:
            cursor = await db.execute(
                "SELECT created_at FROM message_hashes WHERE hash = ?",
                (msg_hash,)
            )
            row = await cursor.fetchone()
            
            if row:
                # Check if within 24 hours
                created_at = datetime.fromisoformat(row[0])
                if datetime.now() - created_at < timedelta(hours=24):
                    return True  # Duplicate
            
            # Save hash
            await db.execute(
                "INSERT OR REPLACE INTO message_hashes (hash, created_at) VALUES (?, ?)",
                (msg_hash, datetime.now().isoformat())
            )
            await db.commit()
        
        return False  # Unique

    
    async def start_cleanup_task(self) -> None:
        """Start background task to clean up old hashes."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_old_hashes())
    
    async def stop_cleanup_task(self) -> None:
        """Stop background cleanup task."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
    
    async def _cleanup_old_hashes(self) -> None:
        """Background task to clean up hashes older than 24 hours."""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour
                
                cutoff_time = datetime.now() - timedelta(hours=24)
                async with aiosqlite.connect(DATABASE_FILE) as db:
                    await db.execute(
                        "DELETE FROM message_hashes WHERE created_at < ?",
                        (cutoff_time.isoformat(),)
                    )
                    await db.commit()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in hash cleanup: {e}")
