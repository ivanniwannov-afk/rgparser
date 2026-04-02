# Counterexamples: Telegram API Limits Bugs

This document records the counterexamples found during bug condition exploration testing for Telegram API Limits issues in the production-critical-fixes spec.

## Test Execution Summary

**Date**: 2026-04-02
**Spec**: production-critical-fixes
**Category**: Telegram API Limits (Bugs 1.10, 1.11, 1.12)
**Status**: All 3 tests FAILED as expected on unfixed code ✅

## Counterexample 1: RetryAfter Error Loses Lead (Bug 1.10)

**Test**: `test_retry_after_loses_lead`
**Bug Condition**: delivery_bot sends message and receives `telegram.error.RetryAfter(30)`, lead is lost in generic except block

**Expected Behavior**: Lead should be delivered after waiting 30 seconds (2 send attempts)

**Actual Behavior on UNFIXED Code**:
- Exception raised: `telegram.error.RetryAfter: Flood control exceeded. Retry in 30 seconds`
- Call count: 1 (expected 2 for retry logic)
- Lead was lost - no retry attempted

**Root Cause Confirmed**: 
The `deliver_lead()` method in `src/delivery/delivery_bot.py` does NOT catch `RetryAfter` exceptions specifically. The error propagates up and the lead is lost. There is no retry logic implemented.

**Code Location**: `src/delivery/delivery_bot.py`, line 115 (`await self._bot.send_message(...)`)

**Counterexample Details**:
```python
# When RetryAfter(30 seconds) is raised:
# - First send_message call raises RetryAfter
# - No retry logic catches it
# - Exception propagates to caller
# - Lead is lost
# - Call count: 1 (should be 2 with retry)
```

## Counterexample 2: Inline Buttons Without Polling (Bug 1.11)

**Test**: `test_inline_buttons_without_polling`
**Bug Condition**: delivery_bot sends messages with inline buttons, but doesn't start polling to listen for callbacks

**Expected Behavior**: Polling should be started to receive button click callbacks

**Actual Behavior on UNFIXED Code**:
- `polling_started` flag: False
- The `start()` method initializes the application but never calls `start_polling()` or `run_polling()`
- Inline buttons are sent but callbacks are never received

**Root Cause Confirmed**:
The `start()` method in `src/delivery/delivery_bot.py` initializes the Bot and Application, registers callback handlers, but NEVER starts the polling mechanism. Without polling, the bot cannot receive updates (including callback button presses).

**Code Location**: `src/delivery/delivery_bot.py`, `start()` method (lines 49-73)

**Counterexample Details**:
```python
# Current start() method:
# 1. Creates Bot instance
# 2. Creates Application
# 3. Registers CallbackQueryHandler
# 4. Calls app.initialize()
# 5. Calls app.start()
# 6. MISSING: app.updater.start_polling() or app.run_polling()
#
# Result: Handlers are registered but never invoked
# Inline buttons sent to operator do nothing when clicked
```

## Counterexample 3: FloodWait Logged Silently (Bug 1.12)

**Test**: `test_floodwait_silent_logging`
**Bug Condition**: Userbot receives FloodWait(3600 seconds), error is logged to database but operator is not notified

**Expected Behavior**: 
1. Console warning should be printed
2. Telegram notification should be sent to operator

**Actual Behavior on UNFIXED Code**:
- Console output: Contains "🚨 FloodWait: userbot 1 must wait 3600 seconds (60.0 minutes)" ✅
- Telegram notification sent: False ❌
- Only database logging occurs (activity_logs table)

**Root Cause Confirmed**:
The FloodWait exception handler in `safe_join_chat()` (`src/ingestion/join_logic.py`, line 202) DOES print a console warning (this was already implemented), but it does NOT send a Telegram notification to the operator. The operator has no way to be alerted about FloodWait issues except by checking the console or database logs.

**Code Location**: `src/ingestion/join_logic.py`, FloodWait handler (lines 199-220)

**Counterexample Details**:
```python
# Current FloodWait handler:
# 1. Logs error message ✅
# 2. Prints console warning ✅
# 3. Marks userbot unavailable ✅
# 4. Redistributes tasks ✅
# 5. Updates chat status ✅
# 6. MISSING: Send Telegram notification to operator ❌
#
# Result: Operator not alerted in real-time about rate limiting
# Must manually check console or database to discover FloodWait
```

## Summary

All three bug conditions were successfully reproduced:

1. **RetryAfter (1.10)**: Lead lost when rate limit hit - no retry logic
2. **Inline Buttons (1.11)**: Buttons don't work - polling never started
3. **FloodWait Notification (1.12)**: Console warning works, but Telegram notification missing

These counterexamples confirm the root causes identified in the design document and provide concrete evidence that the bugs exist in the unfixed code.

## Next Steps

1. Implement fixes as specified in Phase 3 of tasks.md
2. Re-run these same tests after fixes to verify they pass
3. Run preservation tests to ensure no regressions
