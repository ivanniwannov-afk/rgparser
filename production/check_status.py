"""Check system status and pending tasks."""

import sqlite3
import sys
from datetime import datetime, timezone

def check_status():
    """Check system status."""
    try:
        conn = sqlite3.connect('telegram_leads.db')
        cursor = conn.cursor()
        
        print("=" * 60)
        print("SYSTEM STATUS CHECK")
        print("=" * 60)
        print()
        
        # Check userbots
        print("USERBOTS:")
        cursor.execute("""
            SELECT status, COUNT(*) 
            FROM userbots 
            GROUP BY status
        """)
        userbots = cursor.fetchall()
        
        if userbots:
            for status, count in userbots:
                print(f"  {status}: {count}")
        else:
            print("  NO USERBOTS FOUND!")
        
        print()
        
        # Check chats
        print("CHATS:")
        cursor.execute("""
            SELECT status, COUNT(*) 
            FROM chats 
            GROUP BY status
        """)
        chats = cursor.fetchall()
        
        if chats:
            for status, count in chats:
                print(f"  {status}: {count}")
        else:
            print("  NO CHATS FOUND")
        
        print()
        
        # Check pending chats details
        print("PENDING CHATS DETAILS:")
        cursor.execute("""
            SELECT id, chat_link, assigned_userbot_id, created_at
            FROM chats
            WHERE status = 'pending'
            ORDER BY created_at DESC
            LIMIT 10
        """)
        pending = cursor.fetchall()
        
        if pending:
            for chat_id, link, userbot_id, created in pending:
                print(f"  ID {chat_id}: {link}")
                print(f"    Assigned userbot: {userbot_id if userbot_id else 'NOT ASSIGNED'}")
                print(f"    Created: {created}")
                print()
        else:
            print("  NO PENDING CHATS")
        
        print()
        
        # Check join tasks
        print("JOIN TASKS:")
        cursor.execute("""
            SELECT status, COUNT(*) 
            FROM join_tasks 
            GROUP BY status
        """)
        tasks = cursor.fetchall()
        
        if tasks:
            for status, count in tasks:
                print(f"  {status}: {count}")
        else:
            print("  NO JOIN TASKS FOUND!")
        
        print()
        
        # Check scheduled tasks with creation time
        print("SCHEDULED JOIN TASKS:")
        cursor.execute("""
            SELECT id, userbot_id, chat_id, scheduled_at, status, created_at
            FROM join_tasks
            WHERE status = 'pending'
            ORDER BY scheduled_at ASC
            LIMIT 10
        """)
        scheduled = cursor.fetchall()
        
        if scheduled:
            # Use timezone-aware datetime for all operations
            now = datetime.now(timezone.utc)
            for task_id, userbot_id, chat_id, scheduled_at, status, created_at in scheduled:
                try:
                    # Parse scheduled time (ensure timezone-aware)
                    if '+' in scheduled_at or 'Z' in scheduled_at:
                        scheduled_time = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                    else:
                        # If no timezone info, assume UTC
                        scheduled_time = datetime.fromisoformat(scheduled_at).replace(tzinfo=timezone.utc)
                    
                    # Parse created time (ensure timezone-aware)
                    if created_at:
                        if '+' in created_at or 'Z' in created_at:
                            created_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        else:
                            # If no timezone info, assume UTC
                            created_time = datetime.fromisoformat(created_at).replace(tzinfo=timezone.utc)
                        
                        # Calculate initial delay (scheduled - created)
                        delay_seconds = (scheduled_time - created_time).total_seconds()
                    else:
                        delay_seconds = None
                    
                    # Calculate remaining time until execution
                    remaining_seconds = (scheduled_time - now).total_seconds()
                    
                    print(f"  Task {task_id}: Chat {chat_id}, Userbot {userbot_id}")
                    
                    # Show initial delay at creation
                    if delay_seconds is not None:
                        print(f"    Задержка при создании: {int(delay_seconds)} сек ({delay_seconds/60:.1f} мин)")
                    
                    # Show remaining time or overdue status
                    if remaining_seconds > 0:
                        print(f"    Выполнится через: {remaining_seconds/60:.1f} мин")
                    else:
                        print(f"    ПРОСРОЧЕНО на {abs(remaining_seconds)/60:.1f} мин")
                    
                    print(f"    Created: {created_at}")
                    print(f"    Scheduled: {scheduled_at}")
                    print()
                except Exception as e:
                    print(f"  Task {task_id}: Chat {chat_id}, Userbot {userbot_id}")
                    print(f"    Scheduled: {scheduled_at}")
                    print(f"    Error: {e}")
                    print()
        else:
            print("  NO SCHEDULED TASKS")
        
        print()
        
        # Check recent activity logs
        print("RECENT ACTIVITY (last 10):")
        cursor.execute("""
            SELECT created_at, level, component, message
            FROM activity_logs
            ORDER BY created_at DESC
            LIMIT 10
        """)
        logs = cursor.fetchall()
        
        if logs:
            for created, level, component, message in logs:
                print(f"  [{created}] {level} // {component}: {message[:80]}")
        else:
            print("  NO ACTIVITY LOGS")
        
        print()
        print("=" * 60)
        
        conn.close()
        
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    check_status()
