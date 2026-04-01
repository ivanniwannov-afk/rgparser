"""Nuclear clean - delete ALL tasks and reset ALL chats."""

import sqlite3

def nuclear_clean():
    conn = sqlite3.connect('telegram_leads.db')
    cursor = conn.cursor()
    
    print("=" * 60)
    print("NUCLEAR CLEAN - DELETING ALL TASKS")
    print("=" * 60)
    print()
    
    # Delete ALL join tasks (not just pending)
    cursor.execute("DELETE FROM join_tasks")
    deleted_tasks = cursor.rowcount
    print(f"✓ Deleted {deleted_tasks} join tasks (ALL statuses)")
    
    # Reset ALL chats to unassigned pending
    cursor.execute("""
        UPDATE chats 
        SET assigned_userbot_id = NULL,
            status = 'pending',
            joined_at = NULL,
            error_message = NULL,
            updated_at = CURRENT_TIMESTAMP
    """)
    reset_chats = cursor.rowcount
    print(f"✓ Reset {reset_chats} chats to pending")
    
    # Reset userbot join counters
    cursor.execute("""
        UPDATE userbots
        SET joins_today = 0,
            updated_at = CURRENT_TIMESTAMP
    """)
    reset_userbots = cursor.rowcount
    print(f"✓ Reset {reset_userbots} userbot counters")
    
    conn.commit()
    conn.close()
    
    print()
    print("=" * 60)
    print("DATABASE COMPLETELY CLEANED")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Restart the system (stop.bat + run.bat)")
    print("2. Add a test channel through dashboard")
    print("3. Check delays with check_status.bat")
    print("=" * 60)

if __name__ == "__main__":
    nuclear_clean()
    input("\nPress Enter to exit...")
