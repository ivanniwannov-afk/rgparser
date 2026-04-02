"""Clean test data from database."""

import sqlite3
import sys

def clean_database():
    """Remove all test data from database."""
    try:
        conn = sqlite3.connect('telegram_leads.db')
        cursor = conn.cursor()
        
        # Delete all chats
        cursor.execute('DELETE FROM chats')
        deleted_chats = cursor.rowcount
        
        # Delete all userbots (optional - uncomment if needed)
        # cursor.execute('DELETE FROM userbots')
        # deleted_userbots = cursor.rowcount
        
        # Delete all join tasks
        cursor.execute('DELETE FROM join_tasks')
        deleted_tasks = cursor.rowcount
        
        # Delete all activity logs (optional - uncomment if needed)
        # cursor.execute('DELETE FROM activity_logs')
        # deleted_logs = cursor.rowcount
        
        # Delete all spam database entries (optional - uncomment if needed)
        # cursor.execute('DELETE FROM spam_database')
        # deleted_spam = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        print("=" * 50)
        print("DATABASE CLEANED SUCCESSFULLY")
        print("=" * 50)
        print(f"Deleted {deleted_chats} chats")
        print(f"Deleted {deleted_tasks} join tasks")
        # print(f"Deleted {deleted_userbots} userbots")
        # print(f"Deleted {deleted_logs} activity logs")
        # print(f"Deleted {deleted_spam} spam entries")
        print("=" * 50)
        
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    clean_database()
