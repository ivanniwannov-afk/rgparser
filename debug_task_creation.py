"""Debug script to check task creation with current config."""

import asyncio
import aiosqlite
from datetime import datetime, timezone
from config import config

async def debug_task_creation():
    """Debug task creation process."""
    print("=" * 60)
    print("TASK CREATION DEBUG")
    print("=" * 60)
    print()
    
    # Check config values
    print("CONFIG VALUES:")
    print(f"  join_delay_min: {config['join_delay_min']} seconds")
    print(f"  join_delay_max: {config['join_delay_max']} seconds")
    print()
    
    # Check existing tasks
    async with aiosqlite.connect("telegram_leads.db") as db:
        cursor = await db.execute("""
            SELECT id, userbot_id, chat_id, scheduled_at, status, created_at
            FROM join_tasks
            ORDER BY created_at DESC
            LIMIT 10
        """)
        tasks = await cursor.fetchall()
        
        if tasks:
            print("LAST 10 TASKS IN DATABASE:")
            print()
            now = datetime.now(timezone.utc)
            
            for task_id, userbot_id, chat_id, scheduled_at, status, created_at in tasks:
                try:
                    scheduled_time = datetime.fromisoformat(scheduled_at)
                    created_time = datetime.fromisoformat(created_at)
                    
                    # Make both timezone-aware if needed
                    if scheduled_time.tzinfo is None:
                        scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)
                    if created_time.tzinfo is None:
                        created_time = created_time.replace(tzinfo=timezone.utc)
                    
                    delay_seconds = (scheduled_time - created_time).total_seconds()
                    delay_minutes = delay_seconds / 60
                    
                    print(f"Task #{task_id}:")
                    print(f"  Userbot: {userbot_id}, Chat: {chat_id}")
                    print(f"  Status: {status}")
                    print(f"  Created: {created_at}")
                    print(f"  Scheduled: {scheduled_at}")
                    print(f"  Delay: {delay_seconds:.0f} seconds ({delay_minutes:.1f} minutes)")
                    print()
                except Exception as e:
                    print(f"Task #{task_id}: Error parsing dates - {e}")
                    print()
        else:
            print("NO TASKS IN DATABASE")
            print()
    
    # Test IngestionModule directly
    print("=" * 60)
    print("TESTING INGESTION MODULE DIRECTLY")
    print("=" * 60)
    print()
    
    from src.ingestion.ingestion_module import IngestionModule
    
    ingestion = IngestionModule(
        join_delay_min=config['join_delay_min'],
        join_delay_max=config['join_delay_max'],
        daily_join_limit=config['daily_join_limit']
    )
    
    print(f"IngestionModule initialized with:")
    print(f"  join_delay_min: {ingestion.join_delay_min}")
    print(f"  join_delay_max: {ingestion.join_delay_max}")
    print(f"  daily_join_limit: {ingestion.daily_join_limit}")
    print()

if __name__ == "__main__":
    asyncio.run(debug_task_creation())
