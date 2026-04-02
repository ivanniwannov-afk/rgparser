"""Example demonstrating the JoinQueue usage with IngestionModule.

This example shows how to:
1. Accept a list of chat links
2. Distribute them among userbots
3. Create join tasks with randomized delays
4. Load pending tasks on startup
5. Process tasks from the queue
"""

import asyncio
from datetime import datetime, timezone
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.ingestion.ingestion_module import IngestionModule
from src.ingestion.join_queue import JoinQueue
from database import init_database, get_connection


async def setup_test_userbot():
    """Create a test userbot in the database."""
    async with get_connection() as db:
        cursor = await db.execute(
            """INSERT INTO userbots (session_file, status, joins_today, joins_reset_at)
               VALUES (?, 'active', 0, ?)""",
            ("test_session.session", datetime.now(timezone.utc).isoformat())
        )
        userbot_id = cursor.lastrowid
        await db.commit()
        return userbot_id


async def main():
    """Main example function."""
    print("=== Join Queue Example ===\n")
    
    # Initialize database
    print("1. Initializing database...")
    await init_database()
    
    # Create a test userbot
    print("2. Creating test userbot...")
    userbot_id = await setup_test_userbot()
    print(f"   Created userbot with ID: {userbot_id}")
    
    # Create ingestion module
    print("\n3. Creating ingestion module...")
    ingestion = IngestionModule(
        join_delay_min=5,   # 5 seconds for demo
        join_delay_max=15,  # 15 seconds for demo
        daily_join_limit=10
    )
    
    # Accept chat list
    print("\n4. Accepting chat list...")
    chat_links = [
        "t.me/testchat1",
        "t.me/testchat2",
        "t.me/testchat3",
        "@testchat4",
        "https://t.me/testchat5"
    ]
    result = await ingestion.accept_chat_list(chat_links)
    print(f"   Valid chats: {len(result.valid_chats)}")
    print(f"   Invalid chats: {len(result.invalid_chats)}")
    
    # Get chat IDs
    async with get_connection() as db:
        cursor = await db.execute("SELECT id FROM chats WHERE status = 'pending'")
        chat_ids = [row[0] for row in await cursor.fetchall()]
    
    # Distribute chats
    print("\n5. Distributing chats among userbots...")
    distribution = await ingestion.distribute_chats(chat_ids)
    print(f"   Distribution: {distribution}")
    
    # Create join tasks
    print("\n6. Creating join tasks with randomized delays...")
    await ingestion.enqueue_join_tasks(distribution)
    
    # Show created tasks
    async with get_connection() as db:
        cursor = await db.execute(
            """SELECT id, userbot_id, chat_id, scheduled_at, status
               FROM join_tasks
               ORDER BY scheduled_at ASC"""
        )
        tasks = await cursor.fetchall()
        print(f"   Created {len(tasks)} tasks:")
        for task_id, ub_id, ch_id, scheduled_at, status in tasks:
            scheduled_time = datetime.fromisoformat(scheduled_at)
            delay = (scheduled_time - datetime.now(timezone.utc)).total_seconds()
            print(f"   - Task {task_id}: Chat {ch_id}, scheduled in {delay:.1f}s, status={status}")
    
    # Create join queue and load pending tasks
    print("\n7. Creating join queue and loading pending tasks...")
    queue = JoinQueue()
    loaded_count = await queue.load_pending_tasks()
    print(f"   Loaded {loaded_count} pending tasks")
    print(f"   Queue size: {queue.qsize()}")
    
    # Process first few tasks (demo only)
    print("\n8. Processing tasks from queue (demo - first 3 tasks)...")
    processed = 0
    max_to_process = 3
    
    while processed < max_to_process and not queue.is_empty():
        print(f"\n   Waiting for next task...")
        task = await queue.get_next_task()
        
        if task is None:
            print("   Queue stopped or empty")
            break
        
        execution_time = datetime.now(timezone.utc)
        delay_from_scheduled = (execution_time - task.scheduled_at).total_seconds()
        
        print(f"   ✓ Got task {task.task_id}:")
        print(f"     - Userbot: {task.userbot_id}")
        print(f"     - Chat: {task.chat_id}")
        print(f"     - Scheduled: {task.scheduled_at}")
        print(f"     - Executed: {execution_time}")
        print(f"     - Delay from scheduled: {delay_from_scheduled:.2f}s")
        
        # Mark as processing
        await queue.mark_task_processing(task.task_id)
        print(f"     - Status updated to: processing")
        
        # Simulate join operation
        await asyncio.sleep(0.5)
        
        # Mark as completed
        await queue.mark_task_completed(task.task_id)
        print(f"     - Status updated to: completed")
        
        processed += 1
    
    print(f"\n9. Processed {processed} tasks")
    print(f"   Remaining in queue: {queue.qsize()}")
    
    # Show final state
    async with get_connection() as db:
        cursor = await db.execute(
            """SELECT status, COUNT(*) FROM join_tasks GROUP BY status"""
        )
        status_counts = await cursor.fetchall()
        print("\n10. Final task status:")
        for status, count in status_counts:
            print(f"    - {status}: {count}")
    
    print("\n=== Example Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
