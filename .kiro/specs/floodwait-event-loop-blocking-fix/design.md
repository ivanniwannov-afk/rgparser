# FloodWait Event Loop Blocking Fix Design

## Overview

This bugfix addresses a critical architectural flaw in the join queue system where FloodWait errors with long delays (e.g., 400 minutes) block the entire event loop, preventing new tasks with shorter timers from being processed. The fix implements an event-driven queue mechanism using `asyncio.wait()` instead of blocking `asyncio.wait_for()`, allowing the worker to wake up when new tasks arrive and re-evaluate priorities. Additionally, FloodWait error logging is enhanced with bright console output for better visibility.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug - when a FloodWait error with a long delay blocks the event loop, preventing new tasks from being processed
- **Property (P)**: The desired behavior - the queue worker should wake up when new tasks arrive and re-evaluate priorities, even while waiting for a delayed task
- **Preservation**: Existing task execution behavior (immediate execution of ready tasks, database status updates, queue ordering) that must remain unchanged
- **FloodWait**: Telegram API rate limit error that requires waiting a specified number of seconds before retrying
- **Event Loop Blocking**: When `asyncio.wait_for()` with a long timeout prevents the event loop from processing other events
- **`get_next_task()`**: The method in `src/ingestion/join_queue.py` that retrieves the next task to execute, currently blocking on long delays
- **`_new_task_event`**: New asyncio.Event that will signal when tasks are added to the queue
- **Priority Queue**: The `asyncio.PriorityQueue` that orders tasks by `scheduled_at` timestamp

## Bug Details

### Bug Condition

The bug manifests when a userbot receives a FloodWait error with a long delay (e.g., 400 minutes). The `get_next_task()` method uses `asyncio.wait_for(self._stop_event.wait(), timeout=delay)` which blocks the entire event loop for the duration of the delay. During this blocking period, new tasks added to the database with shorter delays cannot be processed because the worker is sleeping and cannot respond to new task events.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type (task: JoinTask, new_tasks_in_db: List[JoinTask])
  OUTPUT: boolean
  
  RETURN task.scheduled_at > datetime.now(timezone.utc) + timedelta(minutes=10)
         AND len(new_tasks_in_db) > 0
         AND min(new_task.scheduled_at for new_task in new_tasks_in_db) < task.scheduled_at
         AND worker_is_blocked_waiting_for_task(task)
END FUNCTION
```

### Examples

- **Example 1**: Userbot receives FloodWait(24000) - must wait 400 minutes. Task is scheduled for 400 minutes in the future. Worker calls `asyncio.wait_for(timeout=24000)` and blocks. New task arrives with 5-minute delay, but worker cannot process it until 400 minutes elapse.

- **Example 2**: Task scheduled for 2 hours in the future. Worker blocks for 2 hours. Multiple new tasks arrive with 1-minute delays during the 2-hour wait. None of these tasks are processed until the 2-hour timer expires.

- **Example 3**: FloodWait(300) - 5 minutes. Worker blocks for 5 minutes. New task arrives with 30-second delay. The 30-second task waits 5 minutes before execution instead of 30 seconds.

- **Edge Case**: Queue has one task scheduled 1 hour in the future. Worker blocks for 1 hour. System receives 100 new tasks with immediate execution times. All 100 tasks wait 1 hour before processing begins.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Tasks ready for execution (scheduled_at <= now) must continue to be returned immediately
- Empty queue behavior must continue to block until a task arrives or stop signal is received
- Database status updates (processing, completed, failed) must continue to work correctly
- Queue ordering by scheduled_at must remain unchanged (earliest first)
- `load_pending_tasks()` must continue to restore all pending tasks on system startup

**Scope:**
All inputs that do NOT involve waiting for a future task while new tasks with earlier scheduled times arrive should be completely unaffected by this fix. This includes:
- Immediate task execution (scheduled_at <= now)
- Empty queue waiting
- Task status transitions
- Queue initialization and loading
- Stop signal handling

## Hypothesized Root Cause

Based on the bug description and code analysis, the root causes are:

1. **Blocking Wait Implementation**: The `get_next_task()` method uses `asyncio.wait_for(self._stop_event.wait(), timeout=delay)` which blocks the event loop for the entire delay duration. This prevents the worker from responding to new task events.

2. **No New Task Notification**: When `add_task()` is called, there is no mechanism to notify the worker that a new task has arrived. The worker only wakes up when the current delay expires or the stop event is set.

3. **Single Wait Condition**: The worker waits for only one condition (delay timeout or stop event), not considering that new tasks might arrive with earlier scheduled times.

4. **Insufficient FloodWait Logging**: FloodWait errors use `logger.warning()` which may not be visible in console output, making it difficult to diagnose when the queue is blocked by long delays.

## Correctness Properties

Property 1: Bug Condition - Event-Driven Queue Wakes on New Tasks

_For any_ state where the worker is waiting for a delayed task and a new task with an earlier scheduled_at is added to the queue, the worker SHALL wake up immediately, re-evaluate the queue, and process the task with the earliest scheduled_at.

**Validates: Requirements 2.1, 2.2, 2.4**

Property 2: Preservation - Immediate Task Execution

_For any_ task where scheduled_at <= now, the fixed `get_next_task()` SHALL return the task immediately without waiting, preserving the existing behavior of immediate execution for ready tasks.

**Validates: Requirements 3.1, 3.3, 3.4**

Property 3: Preservation - Database Status Updates

_For any_ task status transition (pending -> processing -> completed/failed), the fixed code SHALL update the database exactly as the original code does, preserving all status tracking functionality.

**Validates: Requirements 3.3**

Property 4: Preservation - Queue Ordering

_For any_ set of tasks in the queue, the fixed code SHALL retrieve them in order of scheduled_at (earliest first), preserving the priority queue ordering behavior.

**Validates: Requirements 3.1, 3.4**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `src/ingestion/join_queue.py`

**Class**: `JoinQueue`

**Specific Changes**:

1. **Add Event for New Tasks**: Add `_new_task_event` as an instance variable in `__init__()` to signal when new tasks arrive
   - Initialize: `self._new_task_event = asyncio.Event()`

2. **Signal Event in add_task()**: Modify `add_task()` to set the event after adding a task to the queue
   - After `await self._queue.put(task)`, add: `self._new_task_event.set()`

3. **Replace Blocking Wait with asyncio.wait()**: Rewrite the waiting logic in `get_next_task()` to use `asyncio.wait()` with multiple conditions
   - Create tasks for: delay timer, stop event, new task event
   - Use `asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)`
   - When new task event fires, clear it and re-evaluate the queue
   - Cancel pending tasks after one completes

4. **Improve FloodWait Logging**: Modify `safe_join_chat()` in `src/ingestion/join_logic.py` to use `logger.error()` with bright formatting
   - Change from `logger.warning()` to `logger.error()`
   - Add console output with emoji: `print(f"🚨 FloodWait: userbot {userbot_id} must wait {e.value} seconds ({e.value/60:.1f} minutes)")`

5. **Clear Event After Processing**: Ensure `_new_task_event.clear()` is called after waking up to prevent spurious wake-ups

**File**: `src/ingestion/join_logic.py`

**Function**: `safe_join_chat()`

**Specific Changes**:

1. **Enhanced FloodWait Logging**: In the FloodWait exception handler, add bright console output
   - Add: `print(f"🚨 FloodWait: userbot {userbot_id} must wait {e.value} seconds ({e.value/60:.1f} minutes)")`
   - Change `logger.warning()` to `logger.error()`

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code by simulating FloodWait scenarios and verifying that new tasks are blocked, then verify the fix works correctly by ensuring new tasks wake the worker and are processed in priority order.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm that long delays block new task processing.

**Test Plan**: Write tests that add a task with a long delay (e.g., 60 seconds), then add new tasks with short delays (e.g., 1 second) while the worker is waiting. Run these tests on the UNFIXED code to observe that new tasks are not processed until the long delay expires.

**Test Cases**:
1. **Long Delay Blocks Short Tasks**: Add task with 60-second delay, then add task with 1-second delay. Verify that 1-second task waits 60 seconds (will fail on unfixed code)
2. **Multiple New Tasks Blocked**: Add task with 120-second delay, then add 5 tasks with 5-second delays. Verify all 5 tasks wait 120 seconds (will fail on unfixed code)
3. **FloodWait Scenario**: Simulate FloodWait by adding task with 300-second delay, then add immediate tasks. Verify immediate tasks wait 300 seconds (will fail on unfixed code)
4. **Priority Inversion**: Add task scheduled 1 hour in future, then add task scheduled now. Verify current task waits 1 hour (will fail on unfixed code)

**Expected Counterexamples**:
- New tasks with earlier scheduled_at are not processed until the current delay expires
- Worker does not wake up when new tasks are added
- Event loop remains blocked despite new tasks being available

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := get_next_task_fixed(input)
  ASSERT worker_wakes_on_new_task(result)
  ASSERT task_with_earliest_scheduled_at_is_returned(result)
END FOR
```

**Test Cases**:
1. **Event-Driven Wake-Up**: Add task with 60-second delay, start worker, add task with 1-second delay, verify worker wakes within 2 seconds and processes 1-second task first
2. **Priority Re-Evaluation**: Add task scheduled 1 hour in future, add task scheduled now, verify current task is processed immediately
3. **Multiple New Tasks**: Add task with 120-second delay, add 5 tasks with varying delays (5, 10, 15, 20, 25 seconds), verify all tasks are processed in correct order without waiting 120 seconds
4. **FloodWait Recovery**: Simulate FloodWait with 300-second delay, add immediate tasks, verify immediate tasks are processed without waiting 300 seconds

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT get_next_task_original(input) = get_next_task_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for immediate task execution, empty queue waiting, and status updates, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Immediate Task Execution Preservation**: Observe that tasks with scheduled_at <= now are returned immediately on unfixed code, then write test to verify this continues after fix
2. **Empty Queue Preservation**: Observe that empty queue blocks until task arrives on unfixed code, then write test to verify this continues after fix
3. **Status Update Preservation**: Observe that mark_task_processing/completed/failed update database correctly on unfixed code, then write test to verify this continues after fix
4. **Queue Ordering Preservation**: Observe that tasks are retrieved in scheduled_at order on unfixed code, then write test to verify this continues after fix

### Unit Tests

- Test `_new_task_event` is set when `add_task()` is called
- Test `_new_task_event` is cleared after worker wakes up
- Test `asyncio.wait()` returns when new task event fires
- Test worker cancels pending wait tasks after wake-up
- Test FloodWait logging includes bright console output
- Test edge case: new task event fires but no new tasks in queue

### Property-Based Tests

- Generate random task schedules and verify worker always processes earliest task first
- Generate random sequences of task additions and verify worker wakes up correctly
- Generate random FloodWait delays and verify new tasks are not blocked
- Test that all non-blocking scenarios continue to work across many random inputs

### Integration Tests

- Test full workflow: FloodWait occurs, new tasks arrive, worker processes new tasks first
- Test multiple FloodWait scenarios with overlapping delays
- Test system restart with pending FloodWait tasks
- Test stop signal works correctly during delayed task waiting
