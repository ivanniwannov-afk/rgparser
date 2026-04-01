# Bugfix Requirements Document

## Introduction

During the audit of the overdue tasks bugfix (documented in AUDIT_REPORT_OVERDUE_TASKS.md), three critical issues were discovered that prevent the system from starting and working correctly:

1. **CRITICAL - System cannot start**: Class `JoinLogic` is imported in `main.py` line 274 but does not exist in `src/ingestion/join_logic.py`, causing `ImportError` on system startup
2. **Conflict in cleanup_old_tasks()**: After fixing `load_pending_tasks()` to load ALL pending tasks, `cleanup_old_tasks()` may mark recently loaded tasks as 'failed' if they were created more than 1 hour ago but are only slightly overdue
3. **Task duplication in _process_pending_chats()**: The method doesn't check for existing pending tasks before creating new ones, leading to duplicate tasks for the same chat

These issues must be fixed to restore system functionality and prevent data corruption.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the system starts and `main.py` attempts to import `JoinLogic` from `src/ingestion/join_logic.py` THEN the system crashes with `ImportError: cannot import name 'JoinLogic'` preventing the entire application from running

1.2 WHEN `_process_join_queue()` attempts to instantiate `JoinLogic(self.userbot_pool)` THEN the system fails because the class does not exist

1.3 WHEN `_process_join_queue()` attempts to call `join_logic.execute_join(userbot_id, chat_id)` THEN the system fails because the method does not exist

1.4 WHEN the system restarts after being down for 65 minutes and a task was created 65 minutes ago with scheduled_at in the future THEN `load_pending_tasks()` loads the task into the queue AND `cleanup_old_tasks()` marks it as 'failed' in the database (because created_at > 1 hour ago) creating an inconsistent state where the task is in the queue but marked as failed in the database

1.5 WHEN `cleanup_old_tasks()` runs immediately after `load_pending_tasks()` during system startup THEN recently loaded tasks that are slightly overdue (created > 1 hour ago but scheduled_at is recent) are incorrectly marked as 'failed'

1.6 WHEN `_process_pending_chats()` finds a chat with status='pending' and assigned_userbot_id=NULL THEN it creates a new join task without checking if a pending task already exists for that chat

1.7 WHEN a join task fails and the chat status remains 'pending' but assigned_userbot_id is NOT NULL THEN `_process_pending_chats()` never processes this chat again (because assigned_userbot_id IS NOT NULL) leaving it stuck in pending state forever

1.8 WHEN `_process_pending_chats()` runs every 30 seconds and finds the same pending chat multiple times before the first task executes THEN it creates duplicate tasks for the same chat

### Expected Behavior (Correct)

2.1 WHEN the system starts and `main.py` attempts to import `JoinLogic` THEN the import SHALL succeed without errors

2.2 WHEN `_process_join_queue()` instantiates `JoinLogic(self.userbot_pool)` THEN the class SHALL be created successfully with the pool manager stored

2.3 WHEN `_process_join_queue()` calls `join_logic.execute_join(userbot_id, chat_id)` THEN the method SHALL retrieve the userbot client and chat information from the database, call `safe_join_chat()` with the appropriate parameters, and return a boolean indicating success or failure

2.4 WHEN the system restarts and `load_pending_tasks()` loads tasks into the queue THEN `cleanup_old_tasks()` SHALL NOT mark these recently loaded tasks as 'failed' even if they were created more than 1 hour ago

2.5 WHEN `cleanup_old_tasks()` evaluates whether to mark a task as failed THEN it SHALL use a time window large enough (e.g., 24 hours) to avoid conflicts with `load_pending_tasks()` OR it SHALL check scheduled_at instead of created_at to identify truly abandoned tasks

2.6 WHEN `_process_pending_chats()` finds a chat with status='pending' THEN it SHALL check if a pending join task already exists for that chat before creating a new task

2.7 WHEN `_process_pending_chats()` queries for pending chats THEN it SHALL use a LEFT JOIN with join_tasks to exclude chats that already have pending tasks, preventing duplicate task creation

2.8 WHEN multiple iterations of `_process_pending_chats()` run before a task executes THEN only one task SHALL be created per chat, preventing duplication

### Unchanged Behavior (Regression Prevention)

3.1 WHEN `safe_join_chat()` is called with valid parameters THEN the system SHALL CONTINUE TO attempt to join the chat and handle errors (FloodWait, UserDeactivatedBan, InviteRequestSent, etc.) as it currently does

3.2 WHEN `load_pending_tasks()` is called during system startup THEN the system SHALL CONTINUE TO load ALL pending tasks (including overdue ones) into the queue as currently implemented

3.3 WHEN `get_next_task()` retrieves an overdue task from the queue THEN the system SHALL CONTINUE TO execute it immediately and log the delay as currently implemented

3.4 WHEN `cleanup_old_tasks()` identifies genuinely abandoned tasks (created long ago and never executed) THEN the system SHALL CONTINUE TO mark them as 'failed' to prevent accumulation

3.5 WHEN `_process_pending_chats()` successfully distributes chats and creates tasks THEN the system SHALL CONTINUE TO add the newly created tasks to the join queue as currently implemented

3.6 WHEN `_process_join_queue()` processes a task THEN the system SHALL CONTINUE TO mark it as 'processing', execute the join, mark it as 'completed' or 'failed', and log all operations through ActivityLogger as currently implemented

3.7 WHEN the join queue processes tasks THEN the system SHALL CONTINUE TO respect the scheduled_at timestamp and execute tasks in priority order (earliest scheduled_at first) as currently implemented

3.8 WHEN `enqueue_join_tasks()` creates tasks THEN the system SHALL CONTINUE TO apply randomized delays between join_delay_min and join_delay_max as currently implemented
