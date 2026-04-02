# Production Critical Fixes Bugfix Design

## Overview

This design addresses 12 critical production issues in the Telegram Lead Monitoring System that would cause system failures under load. The bugs span four categories: Event Loop blocking (FloodWait handling, sleep delays), Database state management (dead bots, stuck chats, ghost tasks), SQLite concurrency (database locks, race conditions), and Telegram API limits (RetryAfter, polling, FloodWait notifications). The fix strategy uses event-driven architecture with asyncio.Event for non-blocking waits, asyncio.Lock for database synchronization, proper state cleanup on errors, and robust Telegram API error handling with retry logic.

## Glossary

- **Bug_Condition (C)**: The conditions that trigger each of the 12 bugs - ranging from FloodWait errors to concurrent database writes
- **Property (P)**: The desired behavior when bugs are fixed - non-blocking event loop, clean state management, no database locks, proper API error handling
- **Preservation**: Existing functionality that must remain unchanged - normal task processing, successful joins, single-threaded operations, non-rate-limited API calls
- **Event Loop**: Python's asyncio event loop that must never be blocked by long waits or synchronous operations
- **FloodWait**: Telegram API error requiring wait before retry (can be 60 seconds to 400+ minutes)
- **asyncio.Event**: Synchronization primitive for event-driven wakeup without blocking
- **asyncio.Lock**: Mutual exclusion lock for preventing concurrent database access
- **Race Condition**: Bug where timing of operations causes incorrect behavior (e.g., concurrent INSERT operations)
- **UPSERT**: SQL operation that inserts or updates (INSERT OR REPLACE) to handle duplicates
- **WAL Mode**: Write-Ahead Logging mode for SQLite that improves concurrency
- **RetryAfter**: Telegram API error indicating rate limit with required wait time
- **Polling**: Telegram bot mechanism for receiving callback button presses

## Bug Details

### Bug Condition

The system has 12 distinct bug conditions across 4 categories:

**Category 1: Event Loop Blocking**

Bug 1.1 manifests when the join queue worker retrieves a task that encounters FloodWait (e.g., 400 minutes). The system uses `asyncio.wait_for` with a hard timeout, blocking the worker thread and preventing processing of other tasks with short timers.

Bug 1.2 manifests when a userbot passes antibot protection after joining a chat. The system executes `asyncio.sleep(60)`, freezing the execution thread for 60 seconds.

**Category 2: Database State Management**

Bug 1.3 manifests when a userbot client fails to start (ban/corrupted session). `userbot_pool_manager` returns `None`, but the status remains `ACTIVE`, and the pool continues assigning tasks to this dead bot.

Bug 1.4 manifests when a join task fails with an error. The `assigned_userbot_id` field is not reset to `NULL`, and the chat gets stuck in `pending` status with an assigned bot.

Bug 1.5 manifests when `join_logic.execute_join()` fails to get a client. The function returns `False`, but the chat status is not updated to `error`, and the task disappears without a trace.

**Category 3: SQLite Concurrency**

Bug 1.6 manifests when multiple userbots simultaneously parse messages and attempt to write leads to the database. This causes "database is locked" errors due to concurrent `INSERT` operations.

Bug 1.7 manifests when the system restarts and attempts to insert userbots into the database. This causes `IntegrityError` due to duplicate `session_file` entries from blind `INSERT` operations.

Bug 1.8 manifests when `ingestion_module` creates tasks and searches for chat IDs via `SELECT ... ORDER BY DESC LIMIT 1`. With concurrent parsing, IDs get mixed up due to race conditions.

Bug 1.9 manifests when the system sends captcha notifications. It initializes a full Pyrogram client, causing session file locks.

**Category 4: Telegram API Limits**

Bug 1.10 manifests when `delivery_bot` sends messages and receives `telegram.error.RetryAfter`. Leads are lost in the `except` block because this error is not handled.

Bug 1.11 manifests when `delivery_bot` sends messages with inline buttons. The buttons don't work because the bot doesn't run `start_polling()` to listen for callbacks.

Bug 1.12 manifests when a userbot receives FloodWait from Telegram. The error is logged silently, and the system doesn't notify the operator about the ban.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type SystemEvent
  OUTPUT: boolean
  
  RETURN (
    // Event Loop Blocking
    (input.type == "FloodWait" AND input.wait_time > 60) OR
    (input.type == "AntibotSleep" AND input.duration == 60) OR
    
    // Database State Management
    (input.type == "UserbotStartFailed" AND userbot.status == "ACTIVE") OR
    (input.type == "JoinTaskFailed" AND chat.assigned_userbot_id != NULL) OR
    (input.type == "ClientGetFailed" AND chat.status != "error") OR
    
    // SQLite Concurrency
    (input.type == "ConcurrentInsert" AND error == "database is locked") OR
    (input.type == "DuplicateInsert" AND error == "IntegrityError") OR
    (input.type == "RaceConditionSelect" AND method == "ORDER BY DESC LIMIT 1") OR
    (input.type == "SessionFileLock" AND notification_type == "captcha") OR
    
    // Telegram API Limits
    (input.type == "RetryAfterError" AND handled == false) OR
    (input.type == "InlineButtonSent" AND polling == false) OR
    (input.type == "FloodWaitReceived" AND operator_notified == false)
  )
END FUNCTION
```

### Examples


**Event Loop Blocking Examples:**
- Worker gets task with FloodWait 24000s (400 min), blocks for entire duration instead of processing other ready tasks
- Userbot joins chat, detects antibot, sleeps 60s blocking the thread instead of 2-3s

**Database State Management Examples:**
- Userbot session banned, `get_client()` returns `None`, but status stays `active` and receives 5 more task assignments
- Join fails with ChannelPrivate error, chat stays `pending` with `assigned_userbot_id=3`, never retried
- `execute_join()` can't get client, returns `False`, chat status unchanged, task marked `failed` but chat still `pending`

**SQLite Concurrency Examples:**
- 3 userbots parse messages simultaneously, all try `INSERT INTO spam_database`, 2 get "database is locked"
- System restarts, tries `INSERT INTO userbots` for existing session, crashes with `IntegrityError: UNIQUE constraint failed`
- `enqueue_join_tasks()` inserts task, searches `SELECT id ... ORDER BY created_at DESC LIMIT 1`, gets wrong ID due to concurrent insert
- Captcha notification initializes Pyrogram client, locks session file, main userbot can't access it

**Telegram API Limits Examples:**
- `delivery_bot.deliver_lead()` sends message, gets `RetryAfter(30)`, lead lost in generic `except Exception`
- Operator receives lead with "Спам"/"В блок" buttons, clicks button, nothing happens (no polling)
- Userbot gets FloodWait 3600s, logged to activity_logs, operator never sees warning in console or Telegram

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

**Event Loop Operations:**
- Tasks without FloodWait must continue processing in priority order by `scheduled_at`
- Userbots joining chats without antibot protection must continue without additional delays
- Normal asyncio operations must continue working as before

**Database State Management:**
- Userbots that start successfully must continue being marked `active` and receiving task assignments
- Successful join tasks must continue updating chat status to `active` with `chat_id`, `chat_title`, `joined_at`
- Successful client retrieval in `execute_join()` must continue executing the join operation

**SQLite Operations:**
- Single userbot parsing messages and writing leads must continue without errors
- First-time system startup inserting userbots must continue creating records without errors
- Sequential task creation in `ingestion_module` must continue correctly linking tasks to chats
- Non-captcha notifications must continue sending through existing mechanisms

**Telegram API Operations:**
- `delivery_bot` sending messages without rate limits must continue delivering leads to operator
- `delivery_bot` sending messages without inline buttons must continue delivering correctly
- Userbots performing operations without FloodWait must continue without additional delays

**Scope:**
All operations that do NOT involve the 12 specific bug conditions should be completely unaffected by these fixes. This includes normal task processing, successful database operations, non-rate-limited API calls, and standard message delivery.

## Hypothesized Root Cause

Based on the bug descriptions and code analysis, the root causes are:

**Category 1: Event Loop Blocking**

1. **Blocking FloodWait Handling**: `join_queue.get_next_task()` uses `asyncio.wait_for()` with the full delay duration as timeout. When a task has a long FloodWait (400 minutes), the worker blocks for the entire duration instead of being interruptible.
   - Location: `src/ingestion/join_queue.py`, `get_next_task()` method
   - Current implementation waits for `scheduled_at` time using `asyncio.sleep(delay)`
   - No mechanism to wake up early when new tasks with shorter delays arrive

2. **Excessive Antibot Sleep**: `join_logic.py` uses `asyncio.sleep(60)` after detecting antibot protection
   - Location: `src/ingestion/join_logic.py`, `_handle_antibot_protection()` function
   - Line: `await asyncio.sleep(60)` - hardcoded 60-second wait
   - Should be reduced to 2-3 seconds for minimal verification

**Category 2: Database State Management**

3. **No Status Update on Client Start Failure**: `userbot_pool_manager.get_client()` returns `None` on failure but doesn't update database status
   - Location: `src/userbot/userbot_pool_manager.py` (method not shown in code, needs implementation)
   - Missing error handling to mark userbot as `banned` or `error` when client fails to start

4. **No Cleanup on Join Task Failure**: `join_logic.safe_join_chat()` handles errors but doesn't reset `assigned_userbot_id`
   - Location: `src/ingestion/join_logic.py`, error handlers in `safe_join_chat()`
   - Updates chat status to `error` but leaves `assigned_userbot_id` set
   - Should reset to `NULL` to allow reassignment

5. **Missing Status Update in execute_join**: `join_logic.execute_join()` returns `False` on client failure but doesn't update chat status
   - Location: `src/ingestion/join_logic.py`, `execute_join()` method
   - Line: `if not client: return False` - no database update
   - Should call `_update_chat_status()` before returning

**Category 3: SQLite Concurrency**


6. **No Locking on Concurrent Writes**: Multiple userbots write to database simultaneously without synchronization
   - Location: `src/parser/message_parser.py`, `src/delivery/delivery_bot.py`, `src/verifier/llm_verifier.py`
   - All perform `INSERT` operations without locks
   - SQLite WAL mode helps but doesn't eliminate all lock contention
   - Need application-level `asyncio.Lock()` for write operations

7. **Blind INSERT on Restart**: `userbot_pool_manager.add_userbot()` uses `INSERT` without checking for existing records
   - Location: `src/userbot/userbot_pool_manager.py`, `add_userbot()` method
   - Should use `INSERT OR REPLACE` or check existence first
   - Causes `IntegrityError` on duplicate `session_file`

8. **Race Condition in Task ID Retrieval**: `ingestion_module.enqueue_join_tasks()` uses `SELECT ... ORDER BY DESC LIMIT 1` to get task ID
   - Location: `src/ingestion/ingestion_module.py`, `enqueue_join_tasks()` method
   - With concurrent inserts, may retrieve wrong task ID
   - Should use `cursor.lastrowid` immediately after `INSERT`

9. **Full Pyrogram Client for Notifications**: Captcha notifications initialize full Pyrogram client causing session locks
   - Location: `src/ingestion/join_logic.py`, `_send_manual_captcha_notification()` function
   - Uses `Client("notification_bot", bot_token=bot_token)` which locks session files
   - Should use simple HTTP POST via `aiohttp` to Telegram Bot API

**Category 4: Telegram API Limits**

10. **No RetryAfter Handling**: `delivery_bot.deliver_lead()` doesn't catch `telegram.error.RetryAfter`
    - Location: `src/delivery/delivery_bot.py`, `deliver_lead()` method
    - Generic `except Exception` catches it but doesn't retry
    - Should specifically catch `RetryAfter`, wait, and retry

11. **No Polling for Callbacks**: `delivery_bot.start()` doesn't start polling for inline button callbacks
    - Location: `src/delivery/delivery_bot.py`, `start()` method
    - Creates Application but doesn't call `start_polling()` or `run_polling()`
    - Inline buttons sent but callbacks never received

12. **Silent FloodWait Logging**: FloodWait errors logged to database but not displayed to operator
    - Location: `src/ingestion/join_logic.py`, FloodWait exception handler
    - Logs to `activity_logs` table but no console print or Telegram notification
    - Should print warning to console and notify operator via bot

## Correctness Properties

Property 1: Bug Condition - Event Loop Non-Blocking

_For any_ system event where a long wait is required (FloodWait > 60s, antibot protection), the fixed system SHALL use event-driven mechanisms (asyncio.Event) to allow immediate wakeup when higher-priority tasks arrive, and SHALL minimize antibot sleep to 2-3 seconds instead of 60 seconds.

**Validates: Requirements 2.1, 2.2**

Property 2: Bug Condition - Database State Cleanup

_For any_ operation where a userbot fails to start, a join task fails, or a client cannot be retrieved, the fixed system SHALL update database state appropriately (mark userbot as banned/error, reset assigned_userbot_id to NULL, update chat status to error) to prevent stuck states.

**Validates: Requirements 2.3, 2.4, 2.5**

Property 3: Bug Condition - SQLite Concurrency Safety

_For any_ concurrent database write operation (multiple userbots writing leads, system restart inserting userbots, task creation), the fixed system SHALL use asyncio.Lock for write synchronization, UPSERT for duplicate handling, lastrowid for ID retrieval, and HTTP API for notifications to prevent database locks and race conditions.

**Validates: Requirements 2.6, 2.7, 2.8, 2.9**

Property 4: Bug Condition - Telegram API Error Handling

_For any_ Telegram API error (RetryAfter, missing polling, FloodWait), the fixed system SHALL implement retry logic with exponential backoff for RetryAfter, start polling for inline button callbacks, and explicitly notify operators via console and Telegram when FloodWait occurs.

**Validates: Requirements 2.10, 2.11, 2.12**

Property 5: Preservation - Normal Operations Unchanged

_For any_ operation that does NOT involve the 12 bug conditions (normal task processing, successful joins, single-threaded operations, non-rate-limited API calls), the fixed system SHALL produce exactly the same behavior as the original system, preserving all existing functionality.

**Validates: Requirements 3.1-3.12**

## Fix Implementation

### Changes Required

The fixes are organized by category and file:

**File**: `src/ingestion/join_queue.py`

**Function**: `get_next_task()`

**Specific Changes**:
1. **Event-Driven Wakeup**: Replace blocking `asyncio.sleep(delay)` with `asyncio.Event` mechanism
   - Add `self._new_task_event = asyncio.Event()` to `__init__`
   - In `add_task()`, call `self._new_task_event.set()` after adding task
   - In `get_next_task()`, use `asyncio.wait([delay_task, stop_task, new_task_task], return_when=FIRST_COMPLETED)`
   - When `new_task_event` fires, clear it and re-evaluate queue to get higher-priority task

2. **Implementation Pattern**:
```python
# In get_next_task(), replace sleep with:
delay_task = asyncio.create_task(asyncio.sleep(delay))
stop_task = asyncio.create_task(self._stop_event.wait())
new_task_task = asyncio.create_task(self._new_task_event.wait())

done, pending = await asyncio.wait(
    {delay_task, stop_task, new_task_task},
    return_when=asyncio.FIRST_COMPLETED
)

# Cancel pending tasks
for task in pending:
    task.cancel()

# Check which completed
if new_task_task in done:
    self._new_task_event.clear()
    continue  # Re-evaluate queue
```

**File**: `src/ingestion/join_logic.py`

**Function**: `_handle_antibot_protection()`

**Specific Changes**:

1. **Reduce Antibot Sleep**: Change `await asyncio.sleep(60)` to `await asyncio.sleep(2)`
   - Line: After clicking antibot button
   - Rationale: 2 seconds is sufficient to verify button click success

**File**: `src/userbot/userbot_pool_manager.py`

**Function**: `get_client()` (needs implementation)

**Specific Changes**:
1. **Add get_client Method**: Implement method to retrieve Pyrogram client for a userbot
   - Try to start client with `await client.start()`
   - On failure (ban, invalid session), update database: `UPDATE userbots SET status = 'banned' WHERE id = ?`
   - Return `None` on failure, client on success

2. **Implementation Pattern**:
```python
async def get_client(self, userbot_id: int) -> Optional[Client]:
    if userbot_id not in self._userbots:
        return None
    
    userbot = self._userbots[userbot_id]
    
    try:
        client = Client(userbot.session_file)
        await client.start()
        return client
    except Exception as e:
        # Mark as banned/error
        async with database.get_connection() as db:
            await db.execute(
                "UPDATE userbots SET status = 'banned' WHERE id = ?",
                (userbot_id,)
            )
            await db.commit()
        
        userbot.status = UserbotStatus.BANNED
        return None
```

**File**: `src/ingestion/join_logic.py`

**Function**: `safe_join_chat()` error handlers

**Specific Changes**:
1. **Reset assigned_userbot_id on Error**: In all error handlers, add database update to reset assignment
   - Add to FloodWait handler: `UPDATE chats SET assigned_userbot_id = NULL WHERE id = ?`
   - Add to UserDeactivatedBan handler: `UPDATE chats SET assigned_userbot_id = NULL WHERE id = ?`
   - Add to InviteRequestSent handler: `UPDATE chats SET assigned_userbot_id = NULL WHERE id = ?`
   - Add to ChannelPrivate/UsernameInvalid handlers: `UPDATE chats SET assigned_userbot_id = NULL WHERE id = ?`

2. **Update _update_chat_status**: Add optional parameter `reset_userbot_assignment: bool = False`
   - When `True`, include `assigned_userbot_id = NULL` in UPDATE query

**File**: `src/ingestion/join_logic.py`

**Function**: `execute_join()`

**Specific Changes**:
1. **Update Status on Client Failure**: Before returning `False`, update chat status
```python
if not client:
    await _update_chat_status(
        chat_id,
        "error",
        error_message="Failed to get userbot client",
        reset_userbot_assignment=True
    )
    return False
```

**File**: `src/parser/message_parser.py`, `src/delivery/delivery_bot.py`, `src/verifier/llm_verifier.py`

**Module-Level**: Add shared database write lock

**Specific Changes**:
1. **Create Shared Lock**: In `database.py`, add module-level lock
```python
# In database.py
_db_write_lock = asyncio.Lock()

def get_write_lock() -> asyncio.Lock:
    return _db_write_lock
```

2. **Wrap Write Operations**: In each file, wrap database writes with lock
```python
from database import get_write_lock

async with get_write_lock():
    async with get_connection() as db:
        await db.execute("INSERT INTO ...")
        await db.commit()
```

3. **Apply to Locations**:
   - `message_parser.py`: `deduplicate()` method - INSERT into message_hashes
   - `delivery_bot.py`: `handle_spam_feedback()`, `handle_block_feedback()` - INSERT into spam_database, blocklist
   - `llm_verifier.py`: spam cache update - INSERT into spam_database

**File**: `src/userbot/userbot_pool_manager.py`

**Function**: `add_userbot()`

**Specific Changes**:
1. **Use UPSERT**: Replace `INSERT` with `INSERT OR REPLACE`
```python
await db.execute(
    """INSERT OR REPLACE INTO userbots 
       (session_file, status, joins_today, joins_reset_at, created_at, updated_at)
       VALUES (?, ?, 0, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
    (session_file, UserbotStatus.ACTIVE.value, next_reset.isoformat())
)
```

2. **Alternative**: Check existence first
```python
cursor = await db.execute(
    "SELECT id FROM userbots WHERE session_file = ?",
    (session_file,)
)
existing = await cursor.fetchone()

if existing:
    userbot_id = existing[0]
else:
    cursor = await db.execute("INSERT INTO userbots ...")
    userbot_id = cursor.lastrowid
```

**File**: `src/ingestion/ingestion_module.py`

**Function**: `enqueue_join_tasks()`

**Specific Changes**:
1. **Use lastrowid**: Replace `SELECT ... ORDER BY DESC LIMIT 1` with `cursor.lastrowid`
```python
# Current (buggy):
cursor = await db.execute(
    "SELECT id FROM join_tasks WHERE ... ORDER BY created_at DESC LIMIT 1"
)
task_id = (await cursor.fetchone())[0]

# Fixed:
cursor = await db.execute(
    "INSERT INTO join_tasks ..."
)
task_id = cursor.lastrowid
```

2. **Remove SELECT Query**: Delete the entire SELECT query and use lastrowid immediately after INSERT

**File**: `src/ingestion/join_logic.py`

**Function**: `_send_manual_captcha_notification()`

**Specific Changes**:
1. **Replace Pyrogram with HTTP**: Use `aiohttp` to send notification via Bot API
```python
import aiohttp

async def _send_manual_captcha_notification(...):
    message = f"⚠️ Требуется ручная капча! Чат: {chat_link}\nЮзербот: {session_file}"
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": operator_chat_id,
        "text": message
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            if response.status != 200:
                logger.error(f"Failed to send notification: {await response.text()}")
```

2. **Remove Pyrogram Import**: Delete `from pyrogram import Client as BotClient` and client initialization

**File**: `src/delivery/delivery_bot.py`

**Function**: `deliver_lead()`

**Specific Changes**:

1. **Add RetryAfter Handling**: Wrap send_message in try-except with retry logic
```python
from telegram.error import RetryAfter
import asyncio

max_retries = 3
for attempt in range(max_retries):
    try:
        await self._bot.send_message(
            chat_id=self.operator_chat_id,
            text=message_text,
            reply_markup=keyboard
        )
        break  # Success
    except RetryAfter as e:
        if attempt < max_retries - 1:
            wait_time = e.retry_after + 1  # Add 1 second buffer
            logger.warning(f"RetryAfter {wait_time}s, waiting...")
            await asyncio.sleep(wait_time)
        else:
            logger.error(f"Failed after {max_retries} retries")
            raise
```

**File**: `src/delivery/delivery_bot.py`

**Function**: `start()`

**Specific Changes**:
1. **Start Polling**: Add polling initialization after application setup
```python
async def start(self) -> None:
    # ... existing initialization ...
    
    # Start polling in background
    asyncio.create_task(self._app.updater.start_polling())
    
    # Or use run_polling() if blocking is acceptable
    # await self._app.run_polling()
```

2. **Alternative**: Use webhook mode if polling conflicts with other operations

**File**: `src/ingestion/join_logic.py`

**Function**: FloodWait exception handler in `safe_join_chat()`

**Specific Changes**:
1. **Add Console Warning**: Print explicit warning to console
```python
except FloodWait as e:
    # Add console warning
    print(f"🚨 FloodWait: userbot {userbot_id} must wait {e.value} seconds ({e.value/60:.1f} minutes)")
    
    # ... existing code ...
```

2. **Add Telegram Notification**: Send notification to operator
```python
# After marking unavailable
if delivery_bot_token and operator_chat_id:
    await _send_floodwait_notification(
        delivery_bot_token,
        operator_chat_id,
        userbot_id,
        e.value
    )
```

3. **Implement Notification Function**:
```python
async def _send_floodwait_notification(
    bot_token: str,
    operator_chat_id: int,
    userbot_id: int,
    wait_seconds: int
) -> None:
    import aiohttp
    
    # Get userbot session file
    async with database.get_connection() as db:
        cursor = await db.execute(
            "SELECT session_file FROM userbots WHERE id = ?",
            (userbot_id,)
        )
        row = await cursor.fetchone()
        session_file = row[0] if row else f"userbot-{userbot_id}"
    
    message = (
        f"⚠️ FloodWait: {session_file}\n"
        f"Ожидание: {wait_seconds} секунд ({wait_seconds/60:.1f} минут)"
    )
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": operator_chat_id, "text": message}
    
    async with aiohttp.ClientSession() as session:
        await session.post(url, json=payload)
```

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bugs on unfixed code through exploratory testing, then verify the fixes work correctly and preserve existing behavior through fix checking and preservation checking.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the 12 bugs BEFORE implementing fixes. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that simulate each bug condition and observe failures on UNFIXED code to understand root causes.

**Test Cases**:

1. **Event Loop Blocking - FloodWait**: Create mock task with 400-minute FloodWait, add task with 5-second delay, verify worker blocked (will fail on unfixed code)

2. **Event Loop Blocking - Antibot Sleep**: Mock antibot detection, verify 60-second sleep blocks thread (will fail on unfixed code)

3. **Database State - Dead Bot**: Mock client start failure, verify status stays `active` (will fail on unfixed code)

4. **Database State - Stuck Chat**: Mock join failure, verify `assigned_userbot_id` not reset (will fail on unfixed code)

5. **Database State - Ghost Task**: Mock client get failure, verify chat status unchanged (will fail on unfixed code)

6. **SQLite Concurrency - Locked Database**: Simulate 3 concurrent INSERT operations, verify "database is locked" error (will fail on unfixed code)

7. **SQLite Concurrency - Duplicate Insert**: Restart system with existing userbots, verify IntegrityError (will fail on unfixed code)

8. **SQLite Concurrency - Race Condition**: Create tasks concurrently, verify wrong ID retrieved (will fail on unfixed code)

9. **SQLite Concurrency - Session Lock**: Send captcha notification, verify session file locked (will fail on unfixed code)

10. **Telegram API - RetryAfter**: Mock RetryAfter error, verify lead lost (will fail on unfixed code)

11. **Telegram API - No Polling**: Send inline buttons, click button, verify no callback received (will fail on unfixed code)

12. **Telegram API - Silent FloodWait**: Mock FloodWait, verify no console output or Telegram notification (will fail on unfixed code)

**Expected Counterexamples**:
- Worker blocked for 400 minutes instead of processing 5-second task
- Thread frozen for 60 seconds instead of 2-3 seconds
- Dead bot continues receiving task assignments
- Chat stuck in `pending` with assigned bot after failure
- Task disappears without chat status update
- "database is locked" errors on concurrent writes
- IntegrityError on duplicate session_file
- Wrong task ID retrieved due to race condition
- Session file locked by notification client
- Lead lost on RetryAfter error
- Inline button callbacks not received
- FloodWait logged silently without operator notification

### Fix Checking

**Goal**: Verify that for all inputs where the bug conditions hold, the fixed system produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := fixedSystem(input)
  ASSERT expectedBehavior(result)
END FOR
```

**Test Cases**:

1. **Event Loop Non-Blocking**: Verify worker wakes up immediately when new task arrives during FloodWait wait
2. **Antibot Sleep Reduced**: Verify antibot sleep is 2-3 seconds instead of 60 seconds
3. **Dead Bot Marked**: Verify userbot marked `banned` when client fails to start
4. **Stuck Chat Reset**: Verify `assigned_userbot_id` reset to NULL on join failure
5. **Ghost Task Status**: Verify chat status updated to `error` when client get fails
6. **Database Lock Prevention**: Verify no "database is locked" errors with concurrent writes
7. **Duplicate Handling**: Verify no IntegrityError on system restart with existing userbots
8. **Race Condition Fix**: Verify correct task ID retrieved with concurrent inserts
9. **Session Lock Avoidance**: Verify no session file locks when sending notifications
10. **RetryAfter Retry**: Verify lead delivered after RetryAfter wait
11. **Polling Active**: Verify inline button callbacks received
12. **FloodWait Notification**: Verify console warning and Telegram notification on FloodWait

### Preservation Checking

**Goal**: Verify that for all inputs where the bug conditions do NOT hold, the fixed system produces the same result as the original system.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT originalSystem(input) = fixedSystem(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for normal operations, then write property-based tests capturing that behavior.

**Test Cases**:

1. **Normal Task Processing**: Observe that tasks without FloodWait process in priority order, verify this continues after fix
2. **Successful Joins**: Observe that successful joins update status correctly, verify this continues after fix
3. **Single-Threaded Writes**: Observe that single userbot writes work without errors, verify this continues after fix
4. **Non-Rate-Limited API**: Observe that normal API calls work without delays, verify this continues after fix
5. **Active Bot Assignment**: Observe that active bots receive task assignments, verify this continues after fix
6. **Sequential Operations**: Observe that sequential database operations work correctly, verify this continues after fix

### Unit Tests

- Test event-driven wakeup mechanism with asyncio.Event
- Test antibot sleep duration (2-3 seconds)
- Test userbot status updates on client failure
- Test assigned_userbot_id reset on join failure
- Test chat status update on client get failure
- Test database write lock acquisition and release
- Test UPSERT handling of duplicate userbots
- Test lastrowid retrieval after INSERT
- Test HTTP notification sending without session locks
- Test RetryAfter retry logic with exponential backoff
- Test polling initialization and callback handling
- Test FloodWait console and Telegram notifications

### Property-Based Tests

- Generate random task schedules with varying FloodWait durations, verify non-blocking behavior
- Generate random join outcomes (success/failure), verify correct state management
- Generate random concurrent write patterns, verify no database locks
- Generate random API error scenarios, verify proper error handling
- Generate random normal operations, verify preservation of existing behavior

### Integration Tests

- Test full join queue workflow with FloodWait and new task arrival
- Test full join process with antibot protection
- Test full userbot lifecycle from start failure to task redistribution
- Test full chat lifecycle from assignment to join failure to reassignment
- Test full concurrent operation scenario with multiple userbots parsing and writing
- Test full system restart with existing userbots and tasks
- Test full notification flow with captcha and FloodWait alerts
- Test full lead delivery with RetryAfter and inline button callbacks
