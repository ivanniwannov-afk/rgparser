#!/usr/bin/env python3
"""
Comprehensive verification script for overdue tasks bugfix.

This script verifies:
1. Overdue tasks are loaded and executed after system restart
2. Logs are recorded correctly in activity_logs
3. Future tasks continue to work properly (preservation check)
4. Multiple overdue tasks are processed in correct order
"""

import asyncio
import sys
from datetime import datetime, timezone, timedelta
from database import init_database, get_connection
from src.ingestion.join_queue import JoinQueue
from src.logging.activity_logger import ActivityLogger


async def cleanup_test_data():
    """Clean up test data."""
    async with get_connection() as db:
        await db.execute("DELETE FROM join_tasks WHERE id >= 900000")
        await db.execute("DELETE FROM chats WHERE id >= 900000")
        await db.execute("DELETE FROM userbots WHERE id >= 900000")
        await db.execute("DELETE FROM activity_logs WHERE component LIKE 'VerifyOverdue%'")
        await db.commit()


async def verify_overdue_tasks_execution():
    """Verify that overdue tasks are executed after restart."""
    print("\n=== Test 1: Overdue Tasks Execution ===")
    
    # Create test data
    async with get_connection() as db:
        await db.execute("""
            INSERT INTO userbots (id, session_file, status, joins_today, joins_reset_at, created_at, updated_at)
            VALUES (900001, 'verify_overdue.session', 'active', 0, datetime('now', '+1 day'), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """)
        
        await db.execute("""
            INSERT INTO chats (id, chat_link, status, created_at, updated_at)
            VALUES (900001, 'https://t.me/verify_overdue', 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """)
        
        # Create an overdue task (scheduled 10 minutes ago)
        now = datetime.now(timezone.utc)
        scheduled_at = now - timedelta(minutes=10)
        
        await db.execute("""
            INSERT INTO join_tasks (id, userbot_id, chat_id, status, scheduled_at, created_at)
            VALUES (900001, 900001, 900001, 'pending', ?, ?)
        """, (scheduled_at.isoformat(), (now - timedelta(hours=2)).isoformat()))
        
        await db.commit()
    
    # Simulate system restart - create new queue and load tasks
    queue = JoinQueue()
    loaded_count = await queue.load_pending_tasks()
    
    print(f"✓ Loaded {loaded_count} pending tasks")
    
    # Verify our task was loaded
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT status, scheduled_at FROM join_tasks WHERE id = 900001"
        )
        row = await cursor.fetchone()
        
        if row is None:
            print("✗ FAILED: Task 900001 not found in database")
            return False
        
        if row[0] != 'pending':
            print(f"✗ FAILED: Task status is '{row[0]}', expected 'pending'")
            return False
    
    print("✓ Overdue task is in database with status 'pending'")
    
    # Try to get the task from queue
    task = None
    for _ in range(20):
        try:
            t = await asyncio.wait_for(queue.get_next_task(), timeout=2.0)
            if t and t.task_id == 900001:
                task = t
                break
        except asyncio.TimeoutError:
            break
    
    if task is None:
        print("✗ FAILED: Overdue task was not returned by get_next_task()")
        return False
    
    print(f"✓ Overdue task {task.task_id} returned immediately by get_next_task()")
    
    # Mark task as completed
    await queue.mark_task_completed(task.task_id)
    
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT status FROM join_tasks WHERE id = 900001"
        )
        row = await cursor.fetchone()
        
        if row[0] != 'completed':
            print(f"✗ FAILED: Task status is '{row[0]}', expected 'completed'")
            return False
    
    print("✓ Task marked as completed successfully")
    print("✓ Test 1 PASSED: Overdue tasks are executed after restart\n")
    return True


async def verify_logging():
    """Verify that logs are recorded correctly."""
    print("=== Test 2: Logging Verification ===")
    
    # Write test logs
    await ActivityLogger.log(
        component="VerifyOverdueFix",
        level="INFO",
        message="Test log for overdue fix verification"
    )
    
    await ActivityLogger.log(
        component="VerifyOverdueFix",
        level="WARNING",
        message="Test warning log",
        metadata={"test_id": 900001, "test_type": "overdue_fix"}
    )
    
    # Verify logs were written
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM activity_logs WHERE component = 'VerifyOverdueFix'"
        )
        row = await cursor.fetchone()
        
        if row[0] < 2:
            print(f"✗ FAILED: Expected at least 2 log entries, found {row[0]}")
            return False
    
    print(f"✓ Found {row[0]} log entries in activity_logs")
    
    # Verify metadata
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT metadata FROM activity_logs WHERE component = 'VerifyOverdueFix' AND level = 'WARNING'"
        )
        row = await cursor.fetchone()
        
        if row is None:
            print("✗ FAILED: Warning log not found")
            return False
        
        import json
        metadata = json.loads(row[0])
        if metadata.get("test_id") != 900001:
            print(f"✗ FAILED: Metadata test_id is {metadata.get('test_id')}, expected 900001")
            return False
    
    print("✓ Log metadata stored correctly")
    print("✓ Test 2 PASSED: Logging works correctly\n")
    return True


async def verify_future_tasks():
    """Verify that future tasks still work properly (preservation check)."""
    print("=== Test 3: Future Tasks Preservation ===")
    
    # Create test data
    async with get_connection() as db:
        await db.execute("""
            INSERT OR REPLACE INTO userbots (id, session_file, status, joins_today, joins_reset_at, created_at, updated_at)
            VALUES (900002, 'verify_future.session', 'active', 0, datetime('now', '+1 day'), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """)
        
        await db.execute("""
            INSERT OR REPLACE INTO chats (id, chat_link, status, created_at, updated_at)
            VALUES (900002, 'https://t.me/verify_future', 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """)
        
        # Create a future task (scheduled 3 seconds from now)
        now = datetime.now(timezone.utc)
        scheduled_at = now + timedelta(seconds=3)
        
        await db.execute("""
            INSERT INTO join_tasks (id, userbot_id, chat_id, status, scheduled_at, created_at)
            VALUES (900002, 900002, 900002, 'pending', ?, ?)
        """, (scheduled_at.isoformat(), now.isoformat()))
        
        await db.commit()
    
    # Create queue and add task
    queue = JoinQueue()
    await queue.add_task(900002, 900002, 900002, scheduled_at)
    
    print("✓ Future task added to queue")
    
    # Try to get task immediately (should wait)
    start_time = datetime.now(timezone.utc)
    
    try:
        task = await asyncio.wait_for(queue.get_next_task(), timeout=5.0)
        end_time = datetime.now(timezone.utc)
        
        if task is None:
            print("✗ FAILED: Task not returned")
            return False
        
        if task.task_id != 900002:
            print(f"✗ FAILED: Wrong task returned: {task.task_id}")
            return False
        
        wait_time = (end_time - start_time).total_seconds()
        
        # Should have waited at least 2 seconds (allowing some margin)
        if wait_time < 2.0:
            print(f"✗ FAILED: Task returned too early (waited {wait_time:.2f}s, expected ~3s)")
            return False
        
        print(f"✓ Future task returned after {wait_time:.2f}s (expected ~3s)")
        print("✓ Test 3 PASSED: Future tasks work correctly\n")
        return True
        
    except asyncio.TimeoutError:
        print("✗ FAILED: Timeout waiting for future task")
        return False


async def verify_multiple_overdue_tasks():
    """Verify that multiple overdue tasks are processed in correct order."""
    print("=== Test 4: Multiple Overdue Tasks Order ===")
    
    # Create test data
    async with get_connection() as db:
        await db.execute("""
            INSERT OR REPLACE INTO userbots (id, session_file, status, joins_today, joins_reset_at, created_at, updated_at)
            VALUES (900003, 'verify_multi.session', 'active', 0, datetime('now', '+1 day'), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """)
        
        await db.execute("""
            INSERT OR REPLACE INTO chats (id, chat_link, status, created_at, updated_at)
            VALUES (900003, 'https://t.me/verify_multi', 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """)
        
        # Create 3 overdue tasks with different scheduled times
        now = datetime.now(timezone.utc)
        tasks_data = [
            (900010, now - timedelta(minutes=15)),  # Earliest
            (900011, now - timedelta(minutes=10)),  # Middle
            (900012, now - timedelta(minutes=5)),   # Latest
        ]
        
        for task_id, scheduled_at in tasks_data:
            await db.execute("""
                INSERT INTO join_tasks (id, userbot_id, chat_id, status, scheduled_at, created_at)
                VALUES (?, 900003, 900003, 'pending', ?, ?)
            """, (task_id, scheduled_at.isoformat(), (now - timedelta(hours=2)).isoformat()))
        
        await db.commit()
    
    # Load tasks
    queue = JoinQueue()
    await queue.load_pending_tasks()
    
    print("✓ Loaded pending tasks")
    
    # Get tasks and verify order
    returned_task_ids = []
    expected_tasks = {900010, 900011, 900012}
    
    for _ in range(30):
        try:
            task = await asyncio.wait_for(queue.get_next_task(), timeout=2.0)
            if task and task.task_id in expected_tasks:
                returned_task_ids.append(task.task_id)
                if len(returned_task_ids) == 3:
                    break
        except asyncio.TimeoutError:
            break
    
    if len(returned_task_ids) != 3:
        print(f"✗ FAILED: Expected 3 tasks, got {len(returned_task_ids)}: {returned_task_ids}")
        return False
    
    expected_order = [900010, 900011, 900012]
    if returned_task_ids != expected_order:
        print(f"✗ FAILED: Wrong order. Expected {expected_order}, got {returned_task_ids}")
        return False
    
    print(f"✓ Tasks returned in correct order: {returned_task_ids}")
    print("✓ Test 4 PASSED: Multiple overdue tasks processed correctly\n")
    return True


async def main():
    """Run all verification tests."""
    print("=" * 60)
    print("OVERDUE TASKS BUGFIX - COMPREHENSIVE VERIFICATION")
    print("=" * 60)
    
    # Initialize database
    await init_database()
    
    # Clean up before tests
    await cleanup_test_data()
    
    results = []
    
    try:
        # Run all tests
        results.append(("Overdue Tasks Execution", await verify_overdue_tasks_execution()))
        results.append(("Logging", await verify_logging()))
        results.append(("Future Tasks Preservation", await verify_future_tasks()))
        results.append(("Multiple Overdue Tasks", await verify_multiple_overdue_tasks()))
        
    finally:
        # Clean up after tests
        await cleanup_test_data()
    
    # Print summary
    print("=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    
    all_passed = True
    for test_name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{test_name}: {status}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("\n✓ ALL TESTS PASSED - Bugfix verified successfully!")
        return 0
    else:
        print("\n✗ SOME TESTS FAILED - Please review the output above")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
