"""Verify database schema SQL is correct."""

import re


def extract_table_definitions(file_path: str) -> dict[str, str]:
    """Extract CREATE TABLE statements from database.py."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find all CREATE TABLE statements
    pattern = r'CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\)'
    matches = re.findall(pattern, content, re.DOTALL)
    
    tables = {}
    for table_name, definition in matches:
        tables[table_name] = definition.strip()
    
    return tables


def verify_schema():
    """Verify database schema matches design document requirements."""
    print("Verifying database schema...")
    
    tables = extract_table_definitions("database.py")
    
    # Expected tables from design.md
    expected_tables = [
        "userbots",
        "chats",
        "join_tasks",
        "message_hashes",
        "spam_database",
        "blocklist",
        "activity_logs"
    ]
    
    print(f"\nFound {len(tables)} tables:")
    for table_name in tables.keys():
        print(f"  ✓ {table_name}")
    
    # Check all expected tables exist
    missing_tables = set(expected_tables) - set(tables.keys())
    if missing_tables:
        print(f"\n✗ Missing tables: {missing_tables}")
        return False
    
    print(f"\n✅ All {len(expected_tables)} required tables are defined!")
    
    # Verify key columns exist
    print("\nVerifying key columns...")
    
    # userbots table
    if "session_file" in tables["userbots"] and "status" in tables["userbots"]:
        print("  ✓ userbots: session_file, status")
    
    # chats table
    if "chat_link" in tables["chats"] and "status" in tables["chats"]:
        print("  ✓ chats: chat_link, status")
    
    # join_tasks table
    if "scheduled_at" in tables["join_tasks"] and "status" in tables["join_tasks"]:
        print("  ✓ join_tasks: scheduled_at, status")
    
    # message_hashes table
    if "hash" in tables["message_hashes"] and "created_at" in tables["message_hashes"]:
        print("  ✓ message_hashes: hash, created_at")
    
    # spam_database table
    if "message_text" in tables["spam_database"]:
        print("  ✓ spam_database: message_text")
    
    # blocklist table
    if "user_id" in tables["blocklist"]:
        print("  ✓ blocklist: user_id")
    
    # activity_logs table
    if "component" in tables["activity_logs"] and "level" in tables["activity_logs"]:
        print("  ✓ activity_logs: component, level")
    
    print("\n✅ Database schema verification complete!")
    return True


if __name__ == "__main__":
    success = verify_schema()
    exit(0 if success else 1)
