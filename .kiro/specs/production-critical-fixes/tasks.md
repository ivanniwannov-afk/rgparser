# Implementation Plan: Production Critical Fixes

## Phase 1: Bug Condition Exploration Tests (BEFORE Fix)

- [x] 1. Write bug condition exploration tests for Event Loop Blocking
  - **Property 1: Bug Condition** - Event Loop Blocking on FloodWait and Antibot Sleep
  - **CRITICAL**: These tests MUST FAIL on unfixed code - failure confirms the bugs exist
  - **DO NOT attempt to fix the tests or the code when they fail**
  - **NOTE**: These tests encode the expected behavior - they will validate the fix when they pass after implementation
  - **GOAL**: Surface counterexamples that demonstrate Event Loop blocking bugs exist
  - **Scoped PBT Approach**: Scope properties to concrete failing cases for reproducibility
  - Test 1.1: FloodWait blocks worker thread
    - Create mock task with FloodWait 24000s (400 minutes)
    - Add new task with 5-second delay while worker is waiting
    - Assert worker processes 5-second task immediately (expected behavior)
    - Run on UNFIXED code - expect FAILURE (worker blocked for 400 minutes)
  - Test 1.2: Antibot sleep blocks thread for 60 seconds
    - Mock antibot detection in join_logic
    - Measure actual sleep duration
    - Assert sleep duration is 2-3 seconds (expected behavior)
    - Run on UNFIXED code - expect FAILURE (sleep is 60 seconds)
  - Document counterexamples found to understand root cause
  - Mark task complete when tests are written, run, and failures are documented
  - _Requirements: 1.1, 1.2, 2.1, 2.2_

- [x] 2. Write bug condition exploration tests for Database State Management
  - **Property 1: Bug Condition** - Dead Bots, Stuck Chats, Ghost Tasks
  - **CRITICAL**: These tests MUST FAIL on unfixed code - failure confirms the bugs exist
  - **DO NOT attempt to fix the tests or the code when they fail**
  - **NOTE**: These tests encode the expected behavior - they will validate the fix when they pass after implementation
  - **GOAL**: Surface counterexamples that demonstrate Database State Management bugs exist
  - **Scoped PBT Approach**: Scope properties to concrete failing cases for reproducibility
  - Test 1.3: Dead bot continues receiving assignments
    - Mock userbot client start failure (returns None)
    - Assert userbot status updated to 'banned' or 'error' (expected behavior)
    - Assert no new task assignments to this bot (expected behavior)
    - Run on UNFIXED code - expect FAILURE (status stays 'active', receives assignments)
  - Test 1.4: Chat stuck with assigned bot after join failure
    - Mock join task failure (ChannelPrivate error)
    - Assert assigned_userbot_id reset to NULL (expected behavior)
    - Assert chat can be reassigned to another bot (expected behavior)
    - Run on UNFIXED code - expect FAILURE (assigned_userbot_id not reset, chat stuck)
  - Test 1.5: Task disappears without chat status update
    - Mock client get failure in execute_join (returns False)
    - Assert chat status updated to 'error' (expected behavior)
    - Assert error message recorded (expected behavior)
    - Run on UNFIXED code - expect FAILURE (chat status unchanged, task vanishes)
  - Document counterexamples found to understand root cause
  - Mark task complete when tests are written, run, and failures are documented
  - _Requirements: 1.3, 1.4, 1.5, 2.3, 2.4, 2.5_

- [x] 3. Write bug condition exploration tests for SQLite Concurrency
  - **Property 1: Bug Condition** - Database Locks, Race Conditions, Session Locks
  - **CRITICAL**: These tests MUST FAIL on unfixed code - failure confirms the bugs exist
  - **DO NOT attempt to fix the tests or the code when they fail**
  - **NOTE**: These tests encode the expected behavior - they will validate the fix when they pass after implementation
  - **GOAL**: Surface counterexamples that demonstrate SQLite Concurrency bugs exist
  - **Scoped PBT Approach**: Scope properties to concrete failing cases for reproducibility
  - Test 1.6: Concurrent writes cause "database is locked"
    - Simulate 3 userbots writing leads simultaneously
    - Assert all writes succeed without "database is locked" error (expected behavior)
    - Run on UNFIXED code - expect FAILURE (2 writes get "database is locked")
  - Test 1.7: System restart causes IntegrityError on duplicate insert
    - Insert userbot with session_file "test_session"
    - Restart system (simulate by calling add_userbot again)
    - Assert no IntegrityError (expected behavior)
    - Run on UNFIXED code - expect FAILURE (IntegrityError: UNIQUE constraint failed)
  - Test 1.8: Concurrent task creation causes wrong ID retrieval
    - Create 2 tasks concurrently in different coroutines
    - Assert each task gets correct ID via lastrowid (expected behavior)
    - Run on UNFIXED code - expect FAILURE (race condition with SELECT ORDER BY DESC)
  - Test 1.9: Captcha notification locks session file
    - Send captcha notification
    - Attempt to access userbot session file
    - Assert no file lock error (expected behavior)
    - Run on UNFIXED code - expect FAILURE (Pyrogram client locks session file)
  - Document counterexamples found to understand root cause
  - Mark task complete when tests are written, run, and failures are documented
  - _Requirements: 1.6, 1.7, 1.8, 1.9, 2.6, 2.7, 2.8, 2.9_

- [x] 4. Write bug condition exploration tests for Telegram API Limits
  - **Property 1: Bug Condition** - RetryAfter, Missing Polling, Silent FloodWait
  - **CRITICAL**: These tests MUST FAIL on unfixed code - failure confirms the bugs exist
  - **DO NOT attempt to fix the tests or the code when they fail**
  - **NOTE**: These tests encode the expected behavior - they will validate the fix when they pass after implementation
  - **GOAL**: Surface counterexamples that demonstrate Telegram API Limits bugs exist
  - **Scoped PBT Approach**: Scope properties to concrete failing cases for reproducibility
  - Test 1.10: RetryAfter error loses lead
    - Mock telegram.error.RetryAfter(30) in deliver_lead
    - Assert lead delivered after waiting 30 seconds (expected behavior)
    - Run on UNFIXED code - expect FAILURE (lead lost in generic except block)
  - Test 1.11: Inline buttons don't work without polling
    - Send message with inline buttons
    - Simulate button click callback
    - Assert callback received and processed (expected behavior)
    - Run on UNFIXED code - expect FAILURE (no polling, callback never received)
  - Test 1.12: FloodWait logged silently without operator notification
    - Mock FloodWait error in join operation
    - Assert console warning printed (expected behavior)
    - Assert Telegram notification sent to operator (expected behavior)
    - Run on UNFIXED code - expect FAILURE (only database log, no console/Telegram)
  - Document counterexamples found to understand root cause
  - Mark task complete when tests are written, run, and failures are documented
  - _Requirements: 1.10, 1.11, 1.12, 2.10, 2.11, 2.12_

## Phase 2: Preservation Property Tests (BEFORE Fix)

- [x] 5. Write preservation property tests for Event Loop operations (BEFORE implementing fix)
  - **Property 2: Preservation** - Normal Task Processing and Joins
  - **IMPORTANT**: Follow observation-first methodology
  - Observe: Tasks without FloodWait process in priority order by scheduled_at on unfixed code
  - Observe: Userbots joining chats without antibot protection complete without delays on unfixed code
  - Write property-based test: For all tasks without FloodWait, processing order matches scheduled_at priority
  - Write property-based test: For all joins without antibot, completion time is minimal (no extra delays)
  - Verify tests pass on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2_

- [x] 6. Write preservation property tests for Database State Management (BEFORE implementing fix)
  - **Property 2: Preservation** - Successful Operations
  - **IMPORTANT**: Follow observation-first methodology
  - Observe: Userbots that start successfully are marked 'active' and receive assignments on unfixed code
  - Observe: Successful join tasks update chat status to 'active' with chat_id, chat_title, joined_at on unfixed code
  - Observe: Successful client retrieval in execute_join proceeds with join operation on unfixed code
  - Write property-based test: For all successful userbot starts, status is 'active' and assignments occur
  - Write property-based test: For all successful joins, chat status is 'active' with correct metadata
  - Write property-based test: For all successful client gets, join operation executes
  - Verify tests pass on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.3, 3.4, 3.5_

- [x] 7. Write preservation property tests for SQLite operations (BEFORE implementing fix)
  - **Property 2: Preservation** - Single-Threaded and Sequential Operations
  - **IMPORTANT**: Follow observation-first methodology
  - Observe: Single userbot writing leads completes without errors on unfixed code
  - Observe: First-time system startup inserting userbots creates records without errors on unfixed code
  - Observe: Sequential task creation correctly links tasks to chats on unfixed code
  - Observe: Non-captcha notifications send through existing mechanisms on unfixed code
  - Write property-based test: For all single-threaded writes, operations succeed without locks
  - Write property-based test: For all first-time inserts, records created without IntegrityError
  - Write property-based test: For all sequential task creates, task-chat linkage is correct
  - Write property-based test: For all non-captcha notifications, delivery succeeds
  - Verify tests pass on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.6, 3.7, 3.8, 3.9_

- [x] 8. Write preservation property tests for Telegram API operations (BEFORE implementing fix)
  - **Property 2: Preservation** - Normal API Calls
  - **IMPORTANT**: Follow observation-first methodology
  - Observe: delivery_bot sending messages without rate limits delivers leads successfully on unfixed code
  - Observe: delivery_bot sending messages without inline buttons delivers correctly on unfixed code
  - Observe: Userbots performing operations without FloodWait complete without delays on unfixed code
  - Write property-based test: For all non-rate-limited sends, leads delivered to operator
  - Write property-based test: For all messages without buttons, delivery is correct
  - Write property-based test: For all operations without FloodWait, no extra delays occur
  - Verify tests pass on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.10, 3.11, 3.12_

## Phase 3: Implementation

- [x] 9. Fix Category 1: Event Loop Blocking Issues

  - [x] 9.1 Implement event-driven wakeup in join_queue.py
    - Add `self._new_task_event = asyncio.Event()` to `__init__` method
    - In `add_task()` method, call `self._new_task_event.set()` after adding task to queue
    - In `get_next_task()` method, replace blocking `asyncio.sleep(delay)` with event-driven wait:
      - Create three tasks: `delay_task = asyncio.create_task(asyncio.sleep(delay))`
      - `stop_task = asyncio.create_task(self._stop_event.wait())`
      - `new_task_task = asyncio.create_task(self._new_task_event.wait())`
      - Use `asyncio.wait({delay_task, stop_task, new_task_task}, return_when=asyncio.FIRST_COMPLETED)`
      - Cancel pending tasks after wait completes
      - If `new_task_task` completed, clear event and continue to re-evaluate queue
    - _Bug_Condition: (input.type == "FloodWait" AND input.wait_time > 60)_
    - _Expected_Behavior: Worker wakes up immediately when new task with shorter delay arrives_
    - _Preservation: Tasks without FloodWait continue processing in priority order_
    - _Requirements: 1.1, 2.1, 3.1_

  - [x] 9.2 Reduce antibot sleep duration in join_logic.py
    - Locate `_handle_antibot_protection()` function
    - Change `await asyncio.sleep(60)` to `await asyncio.sleep(2)`
    - Add comment explaining 2 seconds is sufficient for button click verification
    - _Bug_Condition: (input.type == "AntibotSleep" AND input.duration == 60)_
    - _Expected_Behavior: Antibot sleep is 2-3 seconds instead of 60 seconds_
    - _Preservation: Joins without antibot protection continue without delays_
    - _Requirements: 1.2, 2.2, 3.2_

  - [x] 9.3 Verify Event Loop exploration tests now pass
    - **Property 1: Expected Behavior** - Event Loop Non-Blocking
    - **IMPORTANT**: Re-run the SAME tests from task 1 - do NOT write new tests
    - The tests from task 1 encode the expected behavior
    - When these tests pass, it confirms the expected behavior is satisfied
    - Run bug condition exploration tests from task 1
    - **EXPECTED OUTCOME**: Tests PASS (confirms Event Loop bugs are fixed)
    - _Requirements: 2.1, 2.2_

  - [x] 9.4 Verify Event Loop preservation tests still pass
    - **Property 2: Preservation** - Normal Task Processing and Joins
    - **IMPORTANT**: Re-run the SAME tests from task 5 - do NOT write new tests
    - Run preservation property tests from task 5
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)

- [x] 10. Fix Category 2: Database State Management Issues

  - [x] 10.1 Implement get_client method in userbot_pool_manager.py
    - Add `async def get_client(self, userbot_id: int) -> Optional[Client]` method
    - Check if userbot_id exists in self._userbots, return None if not
    - Try to start Pyrogram client with `await client.start()`
    - On exception (ban, invalid session):
      - Execute `UPDATE userbots SET status = 'banned' WHERE id = ?`
      - Update in-memory userbot status to BANNED
      - Return None
    - On success, return client
    - _Bug_Condition: (input.type == "UserbotStartFailed" AND userbot.status == "ACTIVE")_
    - _Expected_Behavior: Userbot marked 'banned' when client fails to start_
    - _Preservation: Successful starts continue marking userbot 'active'_
    - _Requirements: 1.3, 2.3, 3.3_

  - [x] 10.2 Add reset_userbot_assignment parameter to _update_chat_status in join_logic.py
    - Modify `_update_chat_status()` function signature to include `reset_userbot_assignment: bool = False`
    - When `reset_userbot_assignment=True`, include `assigned_userbot_id = NULL` in UPDATE query
    - Update all error handlers in `safe_join_chat()` to call with `reset_userbot_assignment=True`:
      - FloodWait handler
      - UserDeactivatedBan handler
      - InviteRequestSent handler
      - ChannelPrivate/UsernameInvalid handlers
    - _Bug_Condition: (input.type == "JoinTaskFailed" AND chat.assigned_userbot_id != NULL)_
    - _Expected_Behavior: assigned_userbot_id reset to NULL on join failure_
    - _Preservation: Successful joins continue updating status to 'active'_
    - _Requirements: 1.4, 2.4, 3.4_

  - [x] 10.3 Update chat status on client failure in execute_join
    - Locate the `if not client:` check in `execute_join()` method
    - Before `return False`, add call to `_update_chat_status()`:
      - `await _update_chat_status(chat_id, "error", error_message="Failed to get userbot client", reset_userbot_assignment=True)`
    - _Bug_Condition: (input.type == "ClientGetFailed" AND chat.status != "error")_
    - _Expected_Behavior: Chat status updated to 'error' when client get fails_
    - _Preservation: Successful client gets continue executing join operation_
    - _Requirements: 1.5, 2.5, 3.5_

  - [x] 10.4 Verify Database State Management exploration tests now pass
    - **Property 1: Expected Behavior** - Database State Cleanup
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - The tests from task 2 encode the expected behavior
    - When these tests pass, it confirms the expected behavior is satisfied
    - Run bug condition exploration tests from task 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms Database State Management bugs are fixed)
    - _Requirements: 2.3, 2.4, 2.5_

  - [x] 10.5 Verify Database State Management preservation tests still pass
    - **Property 2: Preservation** - Successful Operations
    - **IMPORTANT**: Re-run the SAME tests from task 6 - do NOT write new tests
    - Run preservation property tests from task 6
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)

- [x] 11. Fix Category 3: SQLite Concurrency Issues

  - [x] 11.1 Create shared database write lock in database.py
    - Add module-level variable: `_db_write_lock = asyncio.Lock()`
    - Add function: `def get_write_lock() -> asyncio.Lock: return _db_write_lock`
    - Export get_write_lock in module's public API
    - _Bug_Condition: (input.type == "ConcurrentInsert" AND error == "database is locked")_
    - _Expected_Behavior: Concurrent writes synchronized with asyncio.Lock_
    - _Preservation: Single-threaded writes continue without errors_
    - _Requirements: 1.6, 2.6, 3.6_

  - [x] 11.2 Wrap database writes with lock in message_parser.py
    - Import `from database import get_write_lock`
    - In `deduplicate()` method, wrap INSERT into message_hashes with lock:
      - `async with get_write_lock():`
      - `    async with get_connection() as db:`
      - `        await db.execute("INSERT INTO message_hashes ...")`
      - `        await db.commit()`
    - _Bug_Condition: (input.type == "ConcurrentInsert" AND error == "database is locked")_
    - _Expected_Behavior: No "database is locked" errors on concurrent writes_
    - _Preservation: Single userbot writes continue without errors_
    - _Requirements: 1.6, 2.6, 3.6_

  - [x] 11.3 Wrap database writes with lock in delivery_bot.py
    - Import `from database import get_write_lock`
    - In `handle_spam_feedback()`, wrap INSERT into spam_database with lock
    - In `handle_block_feedback()`, wrap INSERT into blocklist with lock
    - Use same pattern as 11.2
    - _Bug_Condition: (input.type == "ConcurrentInsert" AND error == "database is locked")_
    - _Expected_Behavior: No "database is locked" errors on concurrent writes_
    - _Preservation: Single-threaded writes continue without errors_
    - _Requirements: 1.6, 2.6, 3.6_

  - [x] 11.4 Wrap database writes with lock in llm_verifier.py
    - Import `from database import get_write_lock`
    - In spam cache update logic, wrap INSERT into spam_database with lock
    - Use same pattern as 11.2
    - _Bug_Condition: (input.type == "ConcurrentInsert" AND error == "database is locked")_
    - _Expected_Behavior: No "database is locked" errors on concurrent writes_
    - _Preservation: Single-threaded writes continue without errors_
    - _Requirements: 1.6, 2.6, 3.6_

  - [x] 11.5 Use UPSERT in userbot_pool_manager.py add_userbot method
    - Locate `add_userbot()` method
    - Replace `INSERT INTO userbots` with `INSERT OR REPLACE INTO userbots`
    - Keep all column names and values the same
    - Alternative: Check existence first with SELECT, then INSERT only if not exists
    - _Bug_Condition: (input.type == "DuplicateInsert" AND error == "IntegrityError")_
    - _Expected_Behavior: No IntegrityError on system restart with existing userbots_
    - _Preservation: First-time inserts continue creating records without errors_
    - _Requirements: 1.7, 2.7, 3.7_

  - [x] 11.6 Use lastrowid in ingestion_module.py enqueue_join_tasks method
    - Locate `enqueue_join_tasks()` method
    - Find the INSERT INTO join_tasks statement
    - After INSERT, capture: `task_id = cursor.lastrowid`
    - Remove the SELECT query: `SELECT id FROM join_tasks ... ORDER BY created_at DESC LIMIT 1`
    - Use captured task_id for subsequent operations
    - _Bug_Condition: (input.type == "RaceConditionSelect" AND method == "ORDER BY DESC LIMIT 1")_
    - _Expected_Behavior: Correct task ID retrieved via lastrowid_
    - _Preservation: Sequential task creation continues correctly linking tasks to chats_
    - _Requirements: 1.8, 2.8, 3.8_

  - [x] 11.7 Replace Pyrogram with HTTP in join_logic.py _send_manual_captcha_notification
    - Import `import aiohttp`
    - Remove Pyrogram Client import and initialization
    - Replace client-based notification with HTTP POST:
      - `url = f"https://api.telegram.org/bot{bot_token}/sendMessage"`
      - `payload = {"chat_id": operator_chat_id, "text": message}`
      - `async with aiohttp.ClientSession() as session:`
      - `    async with session.post(url, json=payload) as response:`
      - `        if response.status != 200: logger.error(...)`
    - _Bug_Condition: (input.type == "SessionFileLock" AND notification_type == "captcha")_
    - _Expected_Behavior: No session file locks when sending notifications_
    - _Preservation: Non-captcha notifications continue through existing mechanisms_
    - _Requirements: 1.9, 2.9, 3.9_

  - [x] 11.8 Verify SQLite Concurrency exploration tests now pass
    - **Property 1: Expected Behavior** - SQLite Concurrency Safety
    - **IMPORTANT**: Re-run the SAME tests from task 3 - do NOT write new tests
    - The tests from task 3 encode the expected behavior
    - When these tests pass, it confirms the expected behavior is satisfied
    - Run bug condition exploration tests from task 3
    - **EXPECTED OUTCOME**: Tests PASS (confirms SQLite Concurrency bugs are fixed)
    - _Requirements: 2.6, 2.7, 2.8, 2.9_

  - [x] 11.9 Verify SQLite Concurrency preservation tests still pass
    - **Property 2: Preservation** - Single-Threaded and Sequential Operations
    - **IMPORTANT**: Re-run the SAME tests from task 7 - do NOT write new tests
    - Run preservation property tests from task 7
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)

- [x] 12. Fix Category 4: Telegram API Limits Issues

  - [x] 12.1 Add RetryAfter handling in delivery_bot.py deliver_lead method
    - Import `from telegram.error import RetryAfter`
    - Import `import asyncio`
    - Wrap `send_message` call in try-except with retry logic:
      - `max_retries = 3`
      - `for attempt in range(max_retries):`
      - `    try: await self._bot.send_message(...); break`
      - `    except RetryAfter as e:`
      - `        if attempt < max_retries - 1:`
      - `            wait_time = e.retry_after + 1`
      - `            logger.warning(f"RetryAfter {wait_time}s, waiting...")`
      - `            await asyncio.sleep(wait_time)`
      - `        else: logger.error(f"Failed after {max_retries} retries"); raise`
    - _Bug_Condition: (input.type == "RetryAfterError" AND handled == false)_
    - _Expected_Behavior: Lead delivered after RetryAfter wait_
    - _Preservation: Non-rate-limited sends continue delivering leads_
    - _Requirements: 1.10, 2.10, 3.10_

  - [x] 12.2 Start polling in delivery_bot.py start method
    - Locate `start()` method
    - After application initialization, add polling:
      - `asyncio.create_task(self._app.updater.start_polling())`
      - Or use `await self._app.run_polling()` if blocking is acceptable
    - Add comment explaining polling is needed for inline button callbacks
    - _Bug_Condition: (input.type == "InlineButtonSent" AND polling == false)_
    - _Expected_Behavior: Inline button callbacks received and processed_
    - _Preservation: Messages without buttons continue delivering correctly_
    - _Requirements: 1.11, 2.11, 3.11_

  - [x] 12.3 Add console warning for FloodWait in join_logic.py
    - Locate FloodWait exception handler in `safe_join_chat()`
    - Add console print after catching FloodWait:
      - `print(f"🚨 FloodWait: userbot {userbot_id} must wait {e.value} seconds ({e.value/60:.1f} minutes)")`
    - Keep existing activity_logs database logging
    - _Bug_Condition: (input.type == "FloodWaitReceived" AND operator_notified == false)_
    - _Expected_Behavior: Console warning printed on FloodWait_
    - _Preservation: Operations without FloodWait continue without delays_
    - _Requirements: 1.12, 2.12, 3.12_

  - [x] 12.4 Add Telegram notification for FloodWait in join_logic.py
    - Create new function `_send_floodwait_notification(bot_token, operator_chat_id, userbot_id, wait_seconds)`
    - Implementation:
      - Query database for userbot session_file
      - Build message: `f"⚠️ FloodWait: {session_file}\nОжидание: {wait_seconds} секунд ({wait_seconds/60:.1f} минут)"`
      - Send via HTTP POST to Telegram Bot API using aiohttp
      - `url = f"https://api.telegram.org/bot{bot_token}/sendMessage"`
      - `payload = {"chat_id": operator_chat_id, "text": message}`
    - Call this function in FloodWait handler after marking userbot unavailable
    - _Bug_Condition: (input.type == "FloodWaitReceived" AND operator_notified == false)_
    - _Expected_Behavior: Telegram notification sent to operator on FloodWait_
    - _Preservation: Operations without FloodWait continue without delays_
    - _Requirements: 1.12, 2.12, 3.12_

  - [x] 12.5 Verify Telegram API Limits exploration tests now pass
    - **Property 1: Expected Behavior** - Telegram API Error Handling
    - **IMPORTANT**: Re-run the SAME tests from task 4 - do NOT write new tests
    - The tests from task 4 encode the expected behavior
    - When these tests pass, it confirms the expected behavior is satisfied
    - Run bug condition exploration tests from task 4
    - **EXPECTED OUTCOME**: Tests PASS (confirms Telegram API Limits bugs are fixed)
    - _Requirements: 2.10, 2.11, 2.12_

  - [x] 12.6 Verify Telegram API Limits preservation tests still pass
    - **Property 2: Preservation** - Normal API Calls
    - **IMPORTANT**: Re-run the SAME tests from task 8 - do NOT write new tests
    - Run preservation property tests from task 8
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)

## Phase 4: Final Validation

- [x] 13. Checkpoint - Ensure all tests pass
  - Run all bug condition exploration tests (tasks 1-4) - all should PASS
  - Run all preservation property tests (tasks 5-8) - all should PASS
  - Verify no regressions in existing functionality
  - Confirm all 12 critical bugs are fixed
  - Ask the user if questions arise or if additional validation is needed
