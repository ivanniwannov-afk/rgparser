"""Remove banned userbots from database."""

import sqlite3

def remove_banned():
    conn = sqlite3.connect('telegram_leads.db')
    cursor = conn.cursor()
    
    # Get banned userbots
    cursor.execute("SELECT id, session_file FROM userbots WHERE status = 'banned'")
    banned = cursor.fetchall()
    
    if not banned:
        print("No banned userbots found")
        conn.close()
        return
    
    print(f"Found {len(banned)} banned userbot(s):")
    for userbot_id, session_file in banned:
        print(f"  - ID {userbot_id}: {session_file}")
    
    # Delete banned userbots
    cursor.execute("DELETE FROM userbots WHERE status = 'banned'")
    deleted = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    print(f"\nDeleted {deleted} banned userbot(s)")

if __name__ == "__main__":
    remove_banned()
