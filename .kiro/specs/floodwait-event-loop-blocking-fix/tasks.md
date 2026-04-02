# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Event Loop Blocking on FloodWait
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Scope the property to concrete failing case: task with 60-second delay blocks new task with 1-second delay
  - Test that when a task with long delay (60 seconds) is waiting, new tasks with short delays (1 second) are blocked until the long delay expires
  - The test assertions should match the Expected Behavior Properties from design: worker wakes on new task event and processes earliest task first
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists)
  - Document counterexamples found: new tasks with earlier scheduled_at are not processed until current delay expires
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.4, 2.1, 2.2, 2.4_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Non-Blocking Scenarios Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Observe behavior on UNFIXED code for non-buggy inputs:
    - Tasks with scheduled_at <= now are returned immediately
    - Empty queue blocks until task arrives or stop signal
    - Database status updates work correctly (processing, completed, failed)
    - Queue ordering by scheduled_at is maintained (earliest first)
  - Write property-based tests capturing observed behavior patterns from Preservation Requirements
  - Property-based testing generates many test cases for stronger guarantees
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3. Implement event-driven queue fix

  - [x] 3.1 Add _new_task_event to JoinQueue
    - Add `self._new_task_event = asyncio.Event()` in `__init__()` method
    - This event will signal when new tasks are added to the queue
    - _Bug_Condition: isBugCondition(input) where task.scheduled_at > now + 10 minutes AND new tasks with earlier scheduled_at exist AND worker is blocked_
    - _Expected_Behavior: Worker wakes on new task event and processes task with earliest scheduled_at_
    - _Preservation: Immediate task execution, empty queue waiting, status updates, queue ordering must remain unchanged_
    - _Requirements: 2.1, 2.2, 2.4_

  - [x] 3.2 Signal event in add_task()
    - After `await self._queue.put(task)`, add: `self._new_task_event.set()`
    - This notifies the worker that a new task has arrived
    - _Requirements: 2.2_

  - [x] 3.3 Replace blocking wait with asyncio.wait()
    - Rewrite the waiting logic in `get_next_task()` to use `asyncio.wait()` with multiple conditions
    - Create tasks for: delay timer (`asyncio.sleep(delay)`), stop event (`self._stop_event.wait()`), new task event (`self._new_task_event.wait()`)
    - Use `asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)`
    - When new task event fires, clear it with `self._new_task_event.clear()` and re-evaluate the queue
    - Cancel pending tasks after one completes
    - _Requirements: 2.1, 2.2, 2.4_

  - [x] 3.4 Enhance FloodWait logging in safe_join_chat()
    - In `src/ingestion/join_logic.py`, modify the FloodWait exception handler
    - Change `logger.warning()` to `logger.error()`
    - Add bright console output: `print(f"🚨 FloodWait: userbot {userbot_id} must wait {e.value} seconds ({e.value/60:.1f} minutes)")`
    - _Requirements: 1.3, 2.3_

  - [x] 3.5 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Event-Driven Queue Wakes on New Tasks
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - Verify that new tasks with earlier scheduled_at wake the worker immediately
    - Verify that tasks are processed in correct priority order
    - _Requirements: 2.1, 2.2, 2.4_

  - [x] 3.6 Verify preservation tests still pass
    - **Property 2: Preservation** - Non-Blocking Scenarios Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm immediate task execution still works
    - Confirm empty queue waiting still works
    - Confirm database status updates still work
    - Confirm queue ordering still works
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 4. Checkpoint - Ensure all tests pass
  - Run all property-based tests (bug condition + preservation)
  - Verify no regressions in existing functionality
  - Test FloodWait scenario with real delays (if feasible)
  - Ensure all tests pass, ask the user if questions arise
