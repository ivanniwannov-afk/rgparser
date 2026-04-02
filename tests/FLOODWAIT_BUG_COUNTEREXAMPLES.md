# FloodWait Event Loop Blocking Bug - Counterexamples

## Bug Confirmation

The bug condition exploration tests have been executed on the UNFIXED code and have **FAILED as expected**, confirming that the bug exists.

## Counterexamples Found

### Counterexample 1: Concrete Case
**Test**: `test_bug_condition_concrete_case`

**Setup**:
- Task 1: scheduled 60 seconds in the future
- Task 2: scheduled 1 second in the future (added while worker is waiting for Task 1)

**Expected Behavior**:
- Worker should wake up when Task 2 is added
- Worker should process Task 2 first (within ~3 seconds total: 2s wait + 1s delay)

**Actual Behavior**:
- Worker remained blocked for 5+ seconds
- Worker did NOT wake up to process Task 2
- Test timed out after 5 seconds

**Conclusion**: Event loop is blocked by `asyncio.wait_for()` and cannot respond to new task events.

---

### Counterexample 2: Property-Based Test
**Test**: `test_property_1_bug_condition_event_loop_blocking`

**Falsifying Example**:
```python
long_delay_seconds=60
short_delay_seconds=1
```

**Setup**:
- Task 1: scheduled 60 seconds in the future
- Task 2: scheduled 1 second in the future (added while worker is waiting for Task 1)

**Expected Behavior**:
- Worker wakes up immediately when new task arrives
- Worker re-evaluates queue and processes task with earliest scheduled_at first

**Actual Behavior**:
- Worker blocked for 5+ seconds waiting for long delay task
- Worker did NOT wake up to process new short delay task
- Event loop remained blocked

**Conclusion**: The bug is confirmed - new tasks with earlier scheduled times are NOT processed until the current delay expires.

---

## Root Cause Analysis

Based on the counterexamples, the root cause is confirmed:

1. **Blocking Wait Implementation**: The `get_next_task()` method uses `asyncio.wait_for(self._stop_event.wait(), timeout=delay)` which blocks the event loop for the entire delay duration.

2. **No New Task Notification**: When `add_task()` is called, there is no mechanism to notify the worker that a new task has arrived. The worker only wakes up when the current delay expires or the stop event is set.

3. **Single Wait Condition**: The worker waits for only one condition (delay timeout or stop event), not considering that new tasks might arrive with earlier scheduled times.

## Impact

This bug has critical impact on the system:

- **FloodWait Scenario**: When a userbot receives FloodWait(24000) - 400 minutes, ALL new tasks are blocked for 400 minutes, even if they have 1-minute delays
- **Priority Inversion**: Tasks with earlier scheduled times cannot be processed if a task with a later scheduled time is currently waiting
- **System Unresponsiveness**: The entire join queue becomes unresponsive to new tasks during long delays

## Next Steps

1. ✅ Bug condition exploration test written and run on unfixed code
2. ✅ Test FAILED as expected, confirming bug exists
3. ✅ Counterexamples documented
4. ⏭️ Next: Write preservation property tests (Task 2)
5. ⏭️ Next: Implement event-driven queue fix (Task 3)
