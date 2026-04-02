# SQLite Concurrency Bug Counterexamples

This document records the counterexamples found during bug condition exploration testing for SQLite Concurrency issues (Task 3).

## Test Execution Summary

**Date**: 2024
**Status**: 2 FAILED (as expected), 2 PASSED (unexpected)
**Conclusion**: Bugs 1.7 and 1.9 confirmed. Bugs 1.6 and 1.8 may not exist or need different test conditions.

## Bug 1.6: Concurrent Writes Cause "Database is Locked"

**Test Status**: PASSED (unexpected - bug may not exist or test needs adjustment)

**Expected Behavior**: Test should FAIL showing "database is locked" errors on concurrent writes.

**Actual Behavior**: All 3 concurrent writes succeeded without errors.

**Analysis**: 
- SQLite WAL mode (enabled in database.py) provides better concurrency than expected
- The bug may only manifest under higher load or specific timing conditions
- May need to increase concurrency level (e.g., 10+ concurrent writes) to trigger the bug
- Or the bug may have been partially mitigated by WAL mode

**Recommendation**: 
- Test may need adjustment to increase concurrency pressure
- Or bug may not exist in current configuration with WAL mode
- Monitor production for "database is locked" errors

## Bug 1.7: System Restart Causes IntegrityError on Duplicate Insert

**Test Status**: FAILED (as expected - bug confirmed)

**Counterexample Found**:
```
IntegrityError: UNIQUE constraint failed: userbots.session_file
```

**Reproduction Steps**:
1. Create userbot with session_file "test_session.session"
2. Verify userbot inserted successfully
3. Simulate system restart by creating new UserbotPoolManager
4. Call add_userbot() again with same session_file
5. **Result**: IntegrityError raised

**Root Cause Confirmed**: 
The `add_userbot()` method in `userbot_pool_manager.py` uses blind INSERT without checking for existing records:

```python
cursor = await db.execute(
    """INSERT INTO userbots (session_file, status, joins_today, joins_reset_at, created_at, updated_at)
       VALUES (?, ?, 0, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
    (session_file, UserbotStatus.ACTIVE.value, next_reset.isoformat())
)
```

**Fix Required**: Use `INSERT OR REPLACE` or check existence before INSERT.

## Bug 1.8: Concurrent Task Creation Causes Wrong ID Retrieval

**Test Status**: PASSED (unexpected - bug may not exist or test needs adjustment)

**Expected Behavior**: Test should FAIL showing race condition with wrong IDs retrieved.

**Actual Behavior**: Both tasks got unique IDs correctly.

**Analysis**:
- The test simulates the buggy code path (SELECT ORDER BY DESC LIMIT 1)
- However, the race condition may not manifest consistently
- May need more aggressive concurrent task creation to trigger the bug
- Or the timing window for the race condition is very narrow

**Recommendation**:
- Test may need adjustment to increase concurrency or add artificial delays
- Or bug may be rare and only manifest under specific timing conditions
- The fix (using lastrowid) is still recommended as best practice

## Bug 1.9: Captcha Notification Locks Session File

**Test Status**: FAILED (as expected - bug confirmed)

**Counterexample Found**:
```
AssertionError: Captcha notification uses Pyrogram Client, which locks session files.
```

**Reproduction Steps**:
1. Create userbot with session file
2. Call _send_manual_captcha_notification()
3. Monitor which API is used (Pyrogram Client vs HTTP API)
4. **Result**: Pyrogram Client is initialized

**Root Cause Confirmed**:
The `_send_manual_captcha_notification()` function in `join_logic.py` initializes a full Pyrogram client:

```python
from pyrogram import Client as BotClient

async with BotClient("notification_bot", bot_token=bot_token) as bot:
    await bot.send_message(operator_chat_id, message)
```

This causes session file locks because Pyrogram creates session files even for bot tokens.

**Fix Required**: Replace Pyrogram Client with HTTP POST via aiohttp:

```python
import aiohttp

url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
payload = {"chat_id": operator_chat_id, "text": message}

async with aiohttp.ClientSession() as session:
    async with session.post(url, json=payload) as response:
        if response.status != 200:
            logger.error(f"Failed to send notification: {await response.text()}")
```

## Summary

**Confirmed Bugs**:
- ✅ Bug 1.7: Duplicate insert causes IntegrityError (CONFIRMED)
- ✅ Bug 1.9: Captcha notification locks session file (CONFIRMED)

**Uncertain Bugs** (may need test adjustment):
- ⚠️ Bug 1.6: Concurrent writes may not cause locks with WAL mode
- ⚠️ Bug 1.8: Race condition may be rare or need more aggressive testing

**Next Steps**:
1. Implement fixes for confirmed bugs (1.7, 1.9)
2. Re-evaluate tests for bugs 1.6 and 1.8
3. Consider implementing fixes for 1.6 and 1.8 as preventive measures (best practices)
4. Monitor production for actual occurrences of these issues
