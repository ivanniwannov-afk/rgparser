"""Clear pending join tasks and reset pending chats."""

import sqlite3

def clear_pending():
    conn = sqlite3.connect('telegram_leads.db')
    cursor = conn.cursor()
    
    # Delete all pending join tasks
    cursor.execute("DELETE FROM join_tasks WHERE status = 'pending'")
    deleted_tasks = cursor.rowcount
    
    # Reset pending chats to unassigned
    cursor.execute("""
        UPDATE chats 
        SET assigned_userbot_id = NULL, 
            updated_at = CURRENT_TIMESTAMP
        WHERE status = 'pending'
    """)
    reset_chats = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    print("=" * 50)
    print("CLEARED PENDING TASKS")
    print("=" * 50)
    print(f"Deleted {deleted_tasks} pending join tasks")
    print(f"Reset {reset_chats} pending chats")
    print()
    print("Now the system will recreate tasks with new delays")
    print("=" * 50)

if __name__ == "__main__":
    clear_pending()
