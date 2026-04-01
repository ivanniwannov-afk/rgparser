# Implementation Plan

- [ ] 1. Write bug condition exploration tests
  - **Property 1: Bug Condition** - Critical System Failures
  - **CRITICAL**: These tests MUST FAIL on unfixed code - failure confirms the bugs exist
  - **DO NOT attempt to fix the tests or the code when they fail**
  - **NOTE**: These tests encode the expected behavior - they will validate the fixes when they pass after implementation
  - **GOAL**: Surface counterexamples that demonstrate the three bugs exist
  - Test 1.1: Attempt to import JoinLogic from join_logic module (will fail with ImportError on unfixed code)
  - Test 1.2: Create a task 65 minutes ago, call load_pending_tasks(), then call cleanup_old_tasks(), verify task is marked as failed (demonstrates cleanup conflict on unfixed code)
  - Test 1.3: Create a pending chat, create a pending task for it, call _process_pending_chats(), verify duplicate task is created (demonstrates duplication on unfixed code)
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests FAIL (this is correct - it proves the bugs exist)
  - Document counterexamples found to understand root causes
  - Mark task complete when tests are written, run, and failures are documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8_

- [ ] 2. Write preservation property tests (BEFORE implementing fixes)
  - **Property 2: Preservation** - Existing Functionality Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Observe behavior on UNFIXED code for non-buggy operations
  - Test 2.1: Verify safe_join_chat() error handling (FloodWait, UserDeactivatedBan, InviteRequestSent, etc.) works correctly
  - Test 2.2: Verify queue operations (add_task, get_next_task, mark_task_processing, mark_task_completed, mark_task_failed) work correctly
  - Test 2.3: Verify task execution respects scheduled_at timestamps and priority order
  - Test 2.4: Verify cleanup_old_tasks() marks genuinely old tasks (created > 24 hours ago) as failed
  - Test 2.5: Verify _process_pending_chats() creates tasks for chats without existing pending tasks
  - Test 2.6: Verify enqueue_join_tasks() applies randomized delays correctly
  - Write property-based tests capturing observed behavior patterns from Preservation Requirements
  - Property-based testing generates many test cases for stronger guarantees
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

- [ ] 3. Fix 1: Create JoinLogic class with execute_join() method

  - [x] 3.1 Implement JoinLogic class in src/ingestion/join_logic.py
    - Create class with constructor accepting UserbotPoolManager parameter
    - Store pool_manager as instance variable
    - Add docstring explaining the class encapsulates join task execution logic
    - _Bug_Condition: isBugCondition1 where "from src.ingestion.join_logic import JoinLogic" IN main.py AND "class JoinLogic" NOT IN src/ingestion/join_logic.py_
    - _Expected_Behavior: Import succeeds, class is instantiable, execute_join method exists and functions correctly_
    - _Preservation: All existing safe_join_chat() error handling and queue operations remain unchanged_
    - _Requirements: 1.1, 1.2, 2.1, 2.2_

  - [x] 3.2 Implement execute_join() method
    - Method signature: async def execute_join(self, userbot_id: int, chat_id: int) -> bool
    - Get userbot client from pool_manager using get_client(userbot_id)
    - Return False if client not found
    - Query database for chat_link using chat_id
    - Return False if chat not found
    - Get configuration for delivery_bot_token and operator_chat_id
    - Call safe_join_chat() with all required parameters (client, chat_link, chat_db_id, userbot_id, pool_manager, delivery_bot_token, operator_chat_id)
    - Return success boolean from safe_join_chat()
    - Add comprehensive docstring with Args and Returns sections
    - _Bug_Condition: isBugCondition1 where execute_join method does not exist_
    - _Expected_Behavior: Method retrieves userbot client and chat info, calls safe_join_chat(), returns boolean_
    - _Preservation: safe_join_chat() continues to handle all error conditions exactly as before_
    - _Requirements: 1.3, 2.3, 3.1_

  - [ ] 3.3 Verify JoinLogic import test now passes
    - **Property 1: Expected Behavior** - JoinLogic Import Success
    - **IMPORTANT**: Re-run the SAME test from task 1 (Test 1.1) - do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied
    - Run import test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms JoinLogic class exists and is importable)
    - _Requirements: 2.1, 2.2, 2.3_

- [ ] 4. Fix 2: Increase cleanup_old_tasks() time window from 1 hour to 24 hours

  - [x] 4.1 Update cleanup_old_tasks() in src/ingestion/join_queue.py
    - Change timedelta(hours=1) to timedelta(hours=24) on line 89
    - Update docstring to reflect 24-hour window
    - Add comment explaining rationale: "The 24-hour window avoids conflicts with load_pending_tasks(), which loads ALL pending tasks (including overdue ones) on system startup"
    - _Bug_Condition: isBugCondition2 where task.status == 'pending' AND (now - task.created_at) > 1_hour AND task IN loaded_by_load_pending_tasks()_
    - _Expected_Behavior: Tasks loaded by load_pending_tasks() are NOT marked as failed if created within last 24 hours_
    - _Preservation: Genuinely abandoned tasks (created > 24 hours ago) are still marked as failed_
    - _Requirements: 1.4, 1.5, 2.4, 2.5, 3.4_

  - [ ] 4.2 Verify cleanup conflict test now passes
    - **Property 1: Expected Behavior** - No Cleanup Conflict
    - **IMPORTANT**: Re-run the SAME test from task 1 (Test 1.2) - do NOT write a new test
    - Run cleanup conflict test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms tasks loaded by load_pending_tasks are NOT marked as failed)
    - _Requirements: 2.4, 2.5_

- [ ] 5. Fix 3: Add duplicate prevention to _process_pending_chats()

  - [x] 5.1 Update _process_pending_chats() query in main.py
    - Modify SQL query to use LEFT JOIN with join_tasks table
    - Change from: SELECT c.id FROM chats c WHERE c.status = 'pending' AND c.assigned_userbot_id IS NULL
    - Change to: SELECT c.id FROM chats c LEFT JOIN join_tasks jt ON c.id = jt.chat_id AND jt.status = 'pending' WHERE c.status = 'pending' AND c.assigned_userbot_id IS NULL AND jt.id IS NULL
    - Add comment explaining: "Exclude chats that already have pending tasks to prevent duplication"
    - _Bug_Condition: isBugCondition3 where chat.status == 'pending' AND EXISTS(pending task for chat) AND _process_pending_chats() attempts to create task_
    - _Expected_Behavior: No duplicate tasks created for chats with existing pending tasks_
    - _Preservation: Tasks are still created for chats without existing pending tasks, distribution and enqueuing continue as before_
    - _Requirements: 1.6, 1.8, 2.6, 2.7, 2.8, 3.5_

  - [ ] 5.2 Verify duplication test now passes
    - **Property 1: Expected Behavior** - No Task Duplication
    - **IMPORTANT**: Re-run the SAME test from task 1 (Test 1.3) - do NOT write a new test
    - Run duplication test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms no duplicate tasks are created)
    - _Requirements: 2.6, 2.7, 2.8_

- [ ] 6. Verify all preservation tests still pass
  - **Property 2: Preservation** - Existing Functionality Unchanged
  - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
  - Run all preservation property tests from step 2
  - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
  - Verify safe_join_chat() error handling unchanged
  - Verify queue operations unchanged
  - Verify task execution and priority order unchanged
  - Verify cleanup of genuinely old tasks unchanged
  - Verify task creation for chats without pending tasks unchanged
  - Verify randomized delay application unchanged
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

- [ ] 7. Checkpoint - Ensure all tests pass
  - Ensure all bug condition tests pass (JoinLogic import, cleanup conflict, duplication)
  - Ensure all preservation tests pass (no regressions)
  - Ask the user if questions arise
