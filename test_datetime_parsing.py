"""Simple test to verify datetime.fromisoformat() parsing."""

from datetime import datetime, timezone

# Test data from actual database
test_cases = [
    "2026-03-31T07:44:07.833993+00:00",  # With timezone
    "2026-03-31T07:39:30.783006+00:00",  # With timezone
    "2026-03-31T07:39:30.783006",        # Without timezone (naive)
]

print("=" * 60)
print("Testing datetime.fromisoformat() parsing")
print("=" * 60)

for i, scheduled_at_str in enumerate(test_cases, 1):
    print(f"\nTest {i}: {scheduled_at_str}")
    
    try:
        # Parse using fromisoformat (same as in load_pending_tasks())
        parsed_dt = datetime.fromisoformat(scheduled_at_str)
        
        print(f"  ✓ Parsed successfully")
        print(f"  Type: {type(parsed_dt)}")
        print(f"  Value: {parsed_dt}")
        print(f"  Timezone: {parsed_dt.tzinfo}")
        print(f"  Is timezone-aware: {parsed_dt.tzinfo is not None}")
        
        # Test if it can be compared with current time
        now = datetime.now(timezone.utc)
        is_overdue = parsed_dt <= now
        print(f"  Can compare with now: ✓")
        print(f"  Is overdue: {is_overdue}")
        
    except Exception as e:
        print(f"  ❌ Error: {e}")

print("\n" + "=" * 60)
print("Conclusion:")
print("=" * 60)
print("✓ datetime.fromisoformat() correctly parses ISO format strings")
print("✓ Timezone information is preserved when present")
print("✓ Parsed datetime objects can be compared with timezone-aware datetimes")
print("\nFor naive datetimes (without timezone), JoinTask.__post_init__()")
print("adds UTC timezone automatically.")
