"""Ingestion Module for Telegram Lead Monitoring System.

Handles chat list acceptance, validation, and distribution among userbots.
"""

import re
import random
from datetime import datetime, timedelta, timezone
from typing import Optional
import aiosqlite

from database import get_connection


class ValidationResult:
    """Result of chat list validation."""
    
    def __init__(self):
        self.valid_chats: list[str] = []
        self.invalid_chats: list[tuple[str, str]] = []  # (link, error_message)
    
    @property
    def is_valid(self) -> bool:
        """Check if all chats are valid."""
        return len(self.invalid_chats) == 0
    
    @property
    def has_valid_chats(self) -> bool:
        """Check if there are any valid chats."""
        return len(self.valid_chats) > 0


class IngestionModule:
    """Module for ingesting chat lists and distributing them among userbots."""
    
    # Regex pattern for valid Telegram chat links
    CHAT_LINK_PATTERN = re.compile(r'^(https?://)?(t\.me/|@)[\w\d_]+$', re.IGNORECASE)
    
    def __init__(self, join_delay_min: int = 300, join_delay_max: int = 1800, daily_join_limit: int = 10):
        """Initialize the ingestion module.
        
        Args:
            join_delay_min: Minimum delay between joins in seconds (default: 300)
            join_delay_max: Maximum delay between joins in seconds (default: 1800)
            daily_join_limit: Maximum joins per userbot per day (default: 10)
        """
        self.join_delay_min = join_delay_min
        self.join_delay_max = join_delay_max
        self.daily_join_limit = daily_join_limit
    
    async def accept_chat_list(self, chat_links: list[str]) -> ValidationResult:
        """Accept and validate a list of chat links, saving valid ones to database.
        
        Args:
            chat_links: List of Telegram chat links to validate and save
        
        Returns:
            ValidationResult containing valid and invalid chats
        
        Validates: Requirements 1.1, 1.2, 1.3, 1.4
        """
        result = ValidationResult()
        
        for link in chat_links:
            # Validate format
            if not self.validate_chat_link(link):
                result.invalid_chats.append((link, "Invalid chat link format"))
                continue
            
            # Check for duplicates in database
            async with get_connection() as db:
                cursor = await db.execute(
                    "SELECT id FROM chats WHERE chat_link = ?",
                    (link,)
                )
                existing = await cursor.fetchone()
                
                if existing:
                    result.invalid_chats.append((link, "Chat already exists in database"))
                    continue
            
            result.valid_chats.append(link)
        
        # Save valid chats to database with status "pending"
        if result.has_valid_chats:
            async with get_connection() as db:
                for link in result.valid_chats:
                    await db.execute(
                        """INSERT INTO chats (chat_link, status, created_at, updated_at)
                           VALUES (?, 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
                        (link,)
                    )
                await db.commit()
        
        return result
    
    def validate_chat_link(self, link: str) -> bool:
        """Validate a single chat link format.
        
        Args:
            link: Chat link to validate
        
        Returns:
            True if link is valid, False otherwise
        
        Validates: Requirements 1.2
        """
        if not link or not isinstance(link, str):
            return False
        
        return bool(self.CHAT_LINK_PATTERN.match(link.strip()))
    
    async def distribute_chats(self, chat_ids: list[int]) -> dict[int, list[int]]:
        """Distribute chats among available userbots using round-robin with load balancing.
        
        Args:
            chat_ids: List of chat IDs to distribute
        
        Returns:
            Dictionary mapping userbot_id to list of assigned chat_ids
        
        Validates: Requirements 2.1, 2.2, 2.3, 2.4
        """
        if not chat_ids:
            return {}
        
        # Get available userbots (active, not at daily limit, not unavailable)
        async with get_connection() as db:
            cursor = await db.execute(
                """SELECT id, joins_today, joins_reset_at
                   FROM userbots
                   WHERE status = 'active'
                   AND (unavailable_until IS NULL OR unavailable_until < CURRENT_TIMESTAMP)
                   ORDER BY joins_today ASC, id ASC"""
            )
            userbots = await cursor.fetchall()
        
        if not userbots:
            raise ValueError("No available userbots for distribution")
        
        # Filter userbots that haven't reached daily limit
        now = datetime.now(timezone.utc)
        available_userbots = []
        
        for userbot_id, joins_today, joins_reset_at in userbots:
            reset_time = datetime.fromisoformat(joins_reset_at)
            
            # Reset counter if reset time has passed
            if now >= reset_time:
                joins_today = 0
            
            # Only include if under daily limit
            if joins_today < self.daily_join_limit:
                available_userbots.append((userbot_id, joins_today))
        
        if not available_userbots:
            raise ValueError("All userbots have reached daily join limit")
        
        # Distribute chats using round-robin with load balancing
        distribution: dict[int, list[int]] = {userbot_id: [] for userbot_id, _ in available_userbots}
        
        # Sort by current load (joins_today) to balance
        available_userbots.sort(key=lambda x: x[1])
        
        # Round-robin distribution
        userbot_index = 0
        for chat_id in chat_ids:
            userbot_id = available_userbots[userbot_index][0]
            distribution[userbot_id].append(chat_id)
            
            # Update load counter for balancing
            current_load = available_userbots[userbot_index][1]
            available_userbots[userbot_index] = (userbot_id, current_load + 1)
            
            # Check if this userbot reached the limit
            if available_userbots[userbot_index][1] >= self.daily_join_limit:
                # Remove from available list
                available_userbots.pop(userbot_index)
                if not available_userbots:
                    # No more userbots available
                    break
                # Adjust index if needed
                if userbot_index >= len(available_userbots):
                    userbot_index = 0
            else:
                # Move to next userbot
                userbot_index = (userbot_index + 1) % len(available_userbots)
                # Re-sort to maintain load balance
                available_userbots.sort(key=lambda x: x[1])
                # Find current userbot in sorted list
                userbot_index = 0
        
        # Update database with assignments
        async with get_connection() as db:
            for userbot_id, assigned_chat_ids in distribution.items():
                if assigned_chat_ids:
                    for chat_id in assigned_chat_ids:
                        await db.execute(
                            """UPDATE chats
                               SET assigned_userbot_id = ?, updated_at = CURRENT_TIMESTAMP
                               WHERE id = ?""",
                            (userbot_id, chat_id)
                        )
            await db.commit()
        
        # Remove empty assignments
        return {k: v for k, v in distribution.items() if v}
    
    async def enqueue_join_tasks(self, distribution: dict[int, list[int]]) -> None:
        """Create join tasks with randomized delays for distributed chats.
        
        Args:
            distribution: Dictionary mapping userbot_id to list of chat_ids
        
        Validates: Requirements 3.1, 3.2
        """
        # DEBUG LOGGING
        print(f"[DEBUG] enqueue_join_tasks called")
        print(f"[DEBUG] self.join_delay_min = {self.join_delay_min}")
        print(f"[DEBUG] self.join_delay_max = {self.join_delay_max}")
        
        async with get_connection() as db:
            now = datetime.now(timezone.utc)
            print(f"[DEBUG] Current time: {now.isoformat()}")
            
            for userbot_id, chat_ids in distribution.items():
                for chat_id in chat_ids:
                    # Each task gets independent random delay from now
                    delay_seconds = random.randint(self.join_delay_min, self.join_delay_max)
                    scheduled_time = now + timedelta(seconds=delay_seconds)
                    
                    print(f"[DEBUG] Task for chat {chat_id}:")
                    print(f"[DEBUG]   delay_seconds = {delay_seconds}")
                    print(f"[DEBUG]   scheduled_time = {scheduled_time.isoformat()}")
                    
                    # Create join task
                    await db.execute(
                        """INSERT INTO join_tasks (userbot_id, chat_id, scheduled_at, status, created_at)
                           VALUES (?, ?, ?, 'pending', CURRENT_TIMESTAMP)""",
                        (userbot_id, chat_id, scheduled_time.isoformat())
                    )
            
            await db.commit()
            print(f"[DEBUG] Tasks committed to database")
