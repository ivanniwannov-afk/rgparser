"""Join Queue for managing chat join tasks with prioritized scheduling.

This module implements an asynchronous priority queue for managing join tasks
with randomized delays to simulate human behavior.
"""

import asyncio
import heapq
from datetime import datetime, timezone, timedelta
from typing import Optional
from dataclasses import dataclass, field
import aiosqlite

from database import get_connection


@dataclass(order=True)
class JoinTask:
    """Represents a join task with priority based on scheduled time."""
    
    scheduled_at: datetime = field(compare=True)
    task_id: int = field(compare=False)
    userbot_id: int = field(compare=False)
    chat_id: int = field(compare=False)
    
    def __post_init__(self):
        """Ensure scheduled_at is timezone-aware."""
        if self.scheduled_at.tzinfo is None:
            # Assume UTC if no timezone
            self.scheduled_at = self.scheduled_at.replace(tzinfo=timezone.utc)


class JoinQueue:
    """Asynchronous priority queue for managing join tasks.
    
    This queue manages join tasks with scheduled execution times, ensuring
    tasks are processed in the correct order based on their scheduled_at timestamp.
    
    Validates: Requirements 3.1, 3.2, 3.3, 18.2, 18.3
    """
    
    def __init__(self):
        """Initialize the join queue."""
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._processing = False
        self._stop_event = asyncio.Event()
    
    async def add_task(self, task_id: int, userbot_id: int, chat_id: int, scheduled_at: datetime) -> None:
        """Add a join task to the queue.
        
        Args:
            task_id: Database ID of the join task
            userbot_id: ID of the userbot assigned to this task
            chat_id: ID of the chat to join
            scheduled_at: When the task should be executed
        
        Validates: Requirements 3.2
        """
        task = JoinTask(
            scheduled_at=scheduled_at,
            task_id=task_id,
            userbot_id=userbot_id,
            chat_id=chat_id
        )
        await self._queue.put(task)
    
    async def cleanup_old_tasks(self) -> int:
        """Mark old pending tasks as failed to prevent accumulation.
        
        Tasks that are older than 24 hours and still pending are marked as failed
        since they were likely created before a system restart and never added
        to the execution queue.
        
        NOTE: The 24-hour window avoids conflicts with load_pending_tasks(), which
        loads ALL pending tasks (including overdue ones) on system startup. A shorter
        window (e.g., 1 hour) would incorrectly mark recently loaded tasks as failed
        if they were created more than 1 hour ago but are only slightly overdue.
        This method handles truly old tasks (created > 24 hours ago) separately from
        load_pending_tasks() to prevent accumulation of genuinely abandoned tasks.
        
        Returns:
            Number of tasks marked as failed
        
        Validates: Requirements 2.1
        """
        # Calculate the cutoff time (24 hours ago)
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
        cutoff_str = cutoff_time.isoformat()
        
        async with get_connection() as db:
            cursor = await db.execute(
                """UPDATE join_tasks
                   SET status = 'failed', completed_at = CURRENT_TIMESTAMP
                   WHERE status = 'pending' AND created_at < ?""",
                (cutoff_str,)
            )
            await db.commit()
            return cursor.rowcount
    
    async def load_pending_tasks(self) -> int:
        """Load all pending join tasks from the database into the queue.
        
        This method is called on system startup to restore the queue state
        from persisted data. Loads ALL pending tasks regardless of creation time
        to ensure overdue tasks are executed after system restart.
        
        Returns:
            Number of tasks loaded
        
        Validates: Requirements 18.2, 18.3, 2.1
        """
        loaded_count = 0
        
        async with get_connection() as db:
            cursor = await db.execute(
                """SELECT id, userbot_id, chat_id, scheduled_at
                   FROM join_tasks
                   WHERE status = 'pending'
                   ORDER BY scheduled_at ASC"""
            )
            rows = await cursor.fetchall()
            
            for task_id, userbot_id, chat_id, scheduled_at_str in rows:
                # Parse the scheduled time
                scheduled_at = datetime.fromisoformat(scheduled_at_str)
                
                # Add to queue
                await self.add_task(task_id, userbot_id, chat_id, scheduled_at)
                loaded_count += 1
        
        return loaded_count
    
    async def get_next_task(self) -> Optional[JoinTask]:
        """Get the next task that is ready to be executed.
        
        This method blocks until a task is ready (its scheduled_at time has passed)
        or until the stop event is set.
        
        Returns:
            The next task to execute, or None if stopped
        
        Validates: Requirements 3.4
        """
        while not self._stop_event.is_set():
            try:
                # Try to get a task with a short timeout
                task = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                
                # Check if it's time to execute this task
                now = datetime.now(timezone.utc)
                
                if task.scheduled_at <= now:
                    # Task is ready to execute (including overdue tasks)
                    delay_seconds = (now - task.scheduled_at).total_seconds()
                    if delay_seconds > 0:
                        print(f"⚠ Task {task.task_id} is overdue by {delay_seconds:.0f} seconds, executing immediately")
                    return task
                else:
                    # Task is not ready yet, wait until it is
                    delay = (task.scheduled_at - now).total_seconds()
                    print(f"Task {task.task_id} scheduled in {delay:.0f} seconds")
                    
                    # Put the task back in the queue
                    await self._queue.put(task)
                    
                    # Wait until the task is ready or stop event is set
                    try:
                        await asyncio.wait_for(
                            self._stop_event.wait(),
                            timeout=delay
                        )
                        # Stop event was set
                        return None
                    except asyncio.TimeoutError:
                        # Delay elapsed, continue to get the task again
                        continue
            
            except asyncio.TimeoutError:
                # No task available, continue waiting
                continue
        
        return None
    
    async def mark_task_processing(self, task_id: int) -> None:
        """Mark a task as processing in the database.
        
        Args:
            task_id: Database ID of the task
        """
        async with get_connection() as db:
            await db.execute(
                """UPDATE join_tasks
                   SET status = 'processing'
                   WHERE id = ?""",
                (task_id,)
            )
            await db.commit()
    
    async def mark_task_completed(self, task_id: int) -> None:
        """Mark a task as completed in the database.
        
        Args:
            task_id: Database ID of the task
        """
        async with get_connection() as db:
            await db.execute(
                """UPDATE join_tasks
                   SET status = 'completed', completed_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (task_id,)
            )
            await db.commit()
    
    async def mark_task_failed(self, task_id: int) -> None:
        """Mark a task as failed in the database.
        
        Args:
            task_id: Database ID of the task
        """
        async with get_connection() as db:
            await db.execute(
                """UPDATE join_tasks
                   SET status = 'failed', completed_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (task_id,)
            )
            await db.commit()
    
    def stop(self) -> None:
        """Signal the queue to stop processing tasks."""
        self._stop_event.set()
    
    def is_empty(self) -> bool:
        """Check if the queue is empty.
        
        Returns:
            True if the queue has no tasks, False otherwise
        """
        return self._queue.empty()
    
    def qsize(self) -> int:
        """Get the approximate size of the queue.
        
        Returns:
            Number of tasks in the queue
        """
        return self._queue.qsize()
