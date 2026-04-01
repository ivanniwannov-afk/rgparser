"""Userbot Pool Manager for managing multiple Telegram userbots.

**Validates: Requirements 12.1, 12.2, 12.3, 12.4, 13.1, 13.2, 16.1, 16.2, 16.3, 16.4**
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional
import aiosqlite
from pathlib import Path

import database


class UserbotStatus(Enum):
    """Userbot status states."""
    ACTIVE = "active"
    UNAVAILABLE = "unavailable"
    BANNED = "banned"
    INACTIVE = "inactive"


@dataclass
class Userbot:
    """Represents a userbot in the pool."""
    id: int
    session_file: str
    status: UserbotStatus
    unavailable_until: Optional[datetime]
    joins_today: int
    joins_reset_at: datetime


class RateLimiter:
    """Token bucket rate limiter for Telegram API requests.
    
    Implements 20 requests/second limit per userbot.
    **Validates: Requirements 16.2**
    """
    
    def __init__(self, rate: int = 20, per_seconds: float = 1.0):
        """Initialize rate limiter.
        
        Args:
            rate: Maximum number of requests allowed
            per_seconds: Time window in seconds
        """
        self.rate = rate
        self.per_seconds = per_seconds
        self.tokens = float(rate)
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()
        self.min_interval = per_seconds / rate  # Minimum time between requests
    
    async def acquire(self) -> None:
        """Acquire a token, waiting if necessary."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            
            # Refill tokens based on elapsed time
            self.tokens = min(
                self.rate,
                self.tokens + elapsed * (self.rate / self.per_seconds)
            )
            self.last_update = now
            
            # If we don't have enough tokens, wait
            if self.tokens < 1.0:
                wait_time = (1.0 - self.tokens) * (self.per_seconds / self.rate)
                await asyncio.sleep(wait_time)
                
                # Update after waiting
                now = time.monotonic()
                elapsed = now - self.last_update
                self.tokens = min(
                    self.rate,
                    self.tokens + elapsed * (self.rate / self.per_seconds)
                )
                self.last_update = now
            
            # Consume a token
            self.tokens -= 1.0


class UserbotPoolManager:
    """Manages a pool of Telegram userbots.
    
    **Validates: Requirements 12.1, 12.2, 12.3, 12.4, 13.1, 13.2, 16.1, 16.3, 16.4**
    """
    
    def __init__(self, health_check_interval: int = 300):
        """Initialize the userbot pool manager.
        
        Args:
            health_check_interval: Interval in seconds between health checks
        """
        self._userbots: dict[int, Userbot] = {}
        self._rate_limiters: dict[int, RateLimiter] = {}
        self._health_check_interval = health_check_interval
        self._health_check_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
    
    async def add_userbot(self, session_file: str) -> int:
        """Add a new userbot to the pool.
        
        **Validates: Requirements 12.1, 12.3**
        
        Args:
            session_file: Path to the Telegram session file
            
        Returns:
            The ID of the newly added userbot
            
        Raises:
            ValueError: If session file doesn't exist or is invalid
        """
        # Validate session file exists
        if not Path(session_file).exists():
            raise ValueError(f"Session file not found: {session_file}")
        
        # Add to database
        async with database.get_connection() as db:
            cursor = await db.execute(
                """INSERT INTO userbots (session_file, status, joins_today, joins_reset_at, created_at, updated_at)
                   VALUES (?, ?, 0, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
                (
                    session_file,
                    UserbotStatus.ACTIVE.value,
                    (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
                )
            )
            userbot_id = cursor.lastrowid
            await db.commit()
        
        # Create userbot object
        userbot = Userbot(
            id=userbot_id,
            session_file=session_file,
            status=UserbotStatus.ACTIVE,
            unavailable_until=None,
            joins_today=0,
            joins_reset_at=datetime.now(timezone.utc) + timedelta(days=1)
        )
        
        # Add to pool
        self._userbots[userbot_id] = userbot
        self._rate_limiters[userbot_id] = RateLimiter(rate=20, per_seconds=1.0)
        
        return userbot_id
    
    async def remove_userbot(self, userbot_id: int) -> None:
        """Remove a userbot from the pool.
        
        **Validates: Requirements 12.2, 12.4**
        
        Args:
            userbot_id: ID of the userbot to remove
        """
        if userbot_id in self._userbots:
            # Update status to inactive in database
            async with database.get_connection() as db:
                await db.execute(
                    """UPDATE userbots SET status = ?, updated_at = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    (UserbotStatus.INACTIVE.value, userbot_id)
                )
                await db.commit()
            
            # Remove from pool
            del self._userbots[userbot_id]
            if userbot_id in self._rate_limiters:
                del self._rate_limiters[userbot_id]
    
    async def get_available_userbots(self) -> list[Userbot]:
        """Get list of available userbots.
        
        **Validates: Requirements 12.1, 12.2**
        
        Returns:
            List of userbots with status ACTIVE and not at daily limit
        """
        now = datetime.now(timezone.utc)
        available = []
        
        for userbot in self._userbots.values():
            # Check if unavailable period has expired and reactivate if needed
            if userbot.status == UserbotStatus.UNAVAILABLE:
                if userbot.unavailable_until and userbot.unavailable_until <= now:
                    await self._reactivate_userbot(userbot.id)
                    userbot.status = UserbotStatus.ACTIVE
                    userbot.unavailable_until = None
                else:
                    # Still unavailable
                    continue
            
            # Check if userbot is active
            if userbot.status != UserbotStatus.ACTIVE:
                continue
            
            # Check daily join limit
            if userbot.joins_reset_at <= now:
                # Reset daily counter
                await self._reset_daily_joins(userbot.id)
                userbot.joins_today = 0
                userbot.joins_reset_at = now + timedelta(days=1)
            
            # Check if under daily limit (10 joins/day)
            if userbot.joins_today < 10:
                available.append(userbot)
        
        return available
    
    async def mark_unavailable(
        self,
        userbot_id: int,
        reason: str,
        duration: int
    ) -> None:
        """Mark a userbot as unavailable for a specified duration.
        
        **Validates: Requirements 16.1, 16.4**
        
        Args:
            userbot_id: ID of the userbot
            reason: Reason for unavailability (e.g., "floodwait")
            duration: Duration in seconds
        """
        if userbot_id not in self._userbots:
            return
        
        userbot = self._userbots[userbot_id]
        unavailable_until = datetime.now(timezone.utc) + timedelta(seconds=duration)
        
        userbot.status = UserbotStatus.UNAVAILABLE
        userbot.unavailable_until = unavailable_until
        
        # Update database
        async with database.get_connection() as db:
            await db.execute(
                """UPDATE userbots 
                   SET status = ?, unavailable_until = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (UserbotStatus.UNAVAILABLE.value, unavailable_until.isoformat(), userbot_id)
            )
            await db.commit()
        
        # Log the event
        await self._log_activity(
            "UserbotPoolManager",
            "WARNING",
            f"Userbot {userbot_id} marked unavailable: {reason} for {duration}s",
            {"userbot_id": userbot_id, "reason": reason, "duration": duration}
        )
    
    async def health_check_loop(self) -> None:
        """Periodically check health of all userbots.
        
        **Validates: Requirements 13.1, 13.2**
        
        Runs every health_check_interval seconds.
        """
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(self._health_check_interval)
                
                for userbot_id, userbot in list(self._userbots.items()):
                    # Skip if already unavailable or inactive
                    if userbot.status in (UserbotStatus.UNAVAILABLE, UserbotStatus.INACTIVE):
                        continue
                    
                    # Perform health check
                    is_healthy = await self._check_userbot_health(userbot_id)
                    
                    if not is_healthy:
                        # Mark as unavailable
                        userbot.status = UserbotStatus.UNAVAILABLE
                        
                        # Update database
                        async with database.get_connection() as db:
                            await db.execute(
                                """UPDATE userbots 
                                   SET status = ?, updated_at = CURRENT_TIMESTAMP
                                   WHERE id = ?""",
                                (UserbotStatus.UNAVAILABLE.value, userbot_id)
                            )
                            await db.commit()
                        
                        # Log and notify
                        await self._log_activity(
                            "UserbotPoolManager",
                            "WARNING",
                            f"Userbot {userbot_id} failed health check",
                            {"userbot_id": userbot_id}
                        )
                        
                        # Send admin notification
                        await self._notify_admin(
                            f"⚠️ Userbot {userbot_id} ({userbot.session_file}) failed health check and marked unavailable"
                        )
            
            except Exception as e:
                await self._log_activity(
                    "UserbotPoolManager",
                    "ERROR",
                    f"Error in health check loop: {e}",
                    {"error": str(e)}
                )
    
    async def start_health_check(self) -> None:
        """Start the health check background task."""
        if self._health_check_task is None or self._health_check_task.done():
            self._stop_event.clear()
            self._health_check_task = asyncio.create_task(self.health_check_loop())
    
    async def stop_health_check(self) -> None:
        """Stop the health check background task."""
        self._stop_event.set()
        if self._health_check_task and not self._health_check_task.done():
            await self._health_check_task
    
    async def acquire_rate_limit(self, userbot_id: int) -> None:
        """Acquire rate limit token for a userbot.
        
        **Validates: Requirements 16.2**
        
        Args:
            userbot_id: ID of the userbot
        """
        if userbot_id in self._rate_limiters:
            await self._rate_limiters[userbot_id].acquire()
    
    async def redistribute_tasks(self, userbot_id: int) -> None:
        """Redistribute pending tasks from an unavailable userbot.
        
        **Validates: Requirements 16.3**
        
        Args:
            userbot_id: ID of the unavailable userbot
        """
        # Get available userbots
        available = await self.get_available_userbots()
        
        if not available:
            await self._log_activity(
                "UserbotPoolManager",
                "WARNING",
                f"No available userbots to redistribute tasks from userbot {userbot_id}",
                {"userbot_id": userbot_id}
            )
            return
        
        # Get pending tasks for this userbot
        async with database.get_connection() as db:
            cursor = await db.execute(
                """SELECT id, chat_id FROM join_tasks 
                   WHERE userbot_id = ? AND status = 'pending'""",
                (userbot_id,)
            )
            pending_tasks = await cursor.fetchall()
        
        if not pending_tasks:
            return
        
        # Redistribute tasks round-robin
        async with database.get_connection() as db:
            for i, (task_id, chat_id) in enumerate(pending_tasks):
                new_userbot = available[i % len(available)]
                
                # Update task assignment
                await db.execute(
                    """UPDATE join_tasks SET userbot_id = ? WHERE id = ?""",
                    (new_userbot.id, task_id)
                )
                
                # Update chat assignment
                await db.execute(
                    """UPDATE chats SET assigned_userbot_id = ? WHERE id = ?""",
                    (new_userbot.id, chat_id)
                )
            
            await db.commit()
        
        await self._log_activity(
            "UserbotPoolManager",
            "INFO",
            f"Redistributed {len(pending_tasks)} tasks from userbot {userbot_id}",
            {"userbot_id": userbot_id, "task_count": len(pending_tasks)}
        )
    
    async def increment_joins_today(self, userbot_id: int) -> None:
        """Increment the daily join counter for a userbot.
        
        Args:
            userbot_id: ID of the userbot
        """
        if userbot_id in self._userbots:
            userbot = self._userbots[userbot_id]
            userbot.joins_today += 1
            
            # Update database
            async with database.get_connection() as db:
                await db.execute(
                    """UPDATE userbots SET joins_today = ?, updated_at = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    (userbot.joins_today, userbot_id)
                )
                await db.commit()
    
    async def _check_userbot_health(self, userbot_id: int) -> bool:
        """Check if a userbot is healthy.
        
        This is a placeholder that always returns True for now.
        In a real implementation, this would attempt to connect to Telegram
        and verify the session is valid.
        
        Args:
            userbot_id: ID of the userbot to check
            
        Returns:
            True if healthy, False otherwise
        """
        # Placeholder: In real implementation, would check Telegram connection
        # For now, assume all userbots are healthy
        return True
    
    async def _reactivate_userbot(self, userbot_id: int) -> None:
        """Reactivate a userbot after unavailable period expires.
        
        **Validates: Requirements 16.4**
        
        Args:
            userbot_id: ID of the userbot
        """
        async with database.get_connection() as db:
            await db.execute(
                """UPDATE userbots 
                   SET status = ?, unavailable_until = NULL, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (UserbotStatus.ACTIVE.value, userbot_id)
            )
            await db.commit()
        
        await self._log_activity(
            "UserbotPoolManager",
            "INFO",
            f"Userbot {userbot_id} reactivated after unavailable period",
            {"userbot_id": userbot_id}
        )
    
    async def _reset_daily_joins(self, userbot_id: int) -> None:
        """Reset the daily join counter for a userbot.
        
        Args:
            userbot_id: ID of the userbot
        """
        next_reset = datetime.now(timezone.utc) + timedelta(days=1)
        
        async with database.get_connection() as db:
            await db.execute(
                """UPDATE userbots 
                   SET joins_today = 0, joins_reset_at = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (next_reset.isoformat(), userbot_id)
            )
            await db.commit()
    
    async def _log_activity(
        self,
        component: str,
        level: str,
        message: str,
        metadata: Optional[dict] = None
    ) -> None:
        """Log activity to database.
        
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
    
    async def _notify_admin(self, message: str) -> None:
        """Send notification to administrator.
        
        This is a placeholder. In real implementation, would send via Telegram bot.
        
        Args:
            message: Notification message
        """
        # Placeholder: In real implementation, would send via Telegram bot
        await self._log_activity(
            "UserbotPoolManager",
            "INFO",
            f"Admin notification: {message}",
            {"notification": message}
        )
