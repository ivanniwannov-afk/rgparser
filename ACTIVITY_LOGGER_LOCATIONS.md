# Конкретные места для добавления ActivityLogger в main.py

## Критические места (ОБЯЗАТЕЛЬНО)

### 1. _process_join_queue() - Выполнение задач присоединения

**Строка 253** - Перед началом обработки задачи:
```python
# Mark as processing
await self.join_queue.mark_task_processing(task.task_id)

# ДОБАВИТЬ:
await ActivityLogger.log(
    component="JoinQueue",
    level="INFO",
    message="Starting join task execution",
    metadata={
        "task_id": task.task_id,
        "userbot_id": task.userbot_id,
        "chat_id": task.chat_id,
        "scheduled_at": task.scheduled_at.isoformat()
    }
)
```

**Строка 259** - После успешного выполнения:
```python
if success:
    await self.join_queue.mark_task_completed(task.task_id)
    # ДОБАВИТЬ:
    await ActivityLogger.log(
        component="JoinQueue",
        level="INFO",
        message="Join task completed successfully",
        metadata={
            "task_id": task.task_id,
            "userbot_id": task.userbot_id,
            "chat_id": task.chat_id
        }
    )
```

**Строка 261** - После неудачного выполнения:
```python
else:
    await self.join_queue.mark_task_failed(task.task_id)
    # ДОБАВИТЬ:
    await ActivityLogger.log(
        component="JoinQueue",
        level="WARNING",
        message="Join task failed",
        metadata={
            "task_id": task.task_id,
            "userbot_id": task.userbot_id,
            "chat_id": task.chat_id
        }
    )
```

**Строка 264** - При ошибке обработки:
```python
except Exception as e:
    print(f"Error processing join task {task.task_id}: {e}")
    # ДОБАВИТЬ:
    await ActivityLogger.log_error(
        component="JoinQueue",
        error_message=f"Exception while processing join task {task.task_id}",
        exception=e
    )
    await self.join_queue.mark_task_failed(task.task_id)
```

### 2. _process_pending_chats() - Создание задач присоединения

**Строка 283** - Когда найдены pending чаты:
```python
print(f"Found {len(chat_ids)} pending chat(s), creating join tasks...")

# ДОБАВИТЬ:
await ActivityLogger.log(
    component="IngestionModule",
    level="INFO",
    message="Found pending chats - creating join tasks",
    metadata={
        "pending_chats_count": len(chat_ids),
        "chat_ids": chat_ids
    }
)
```

**Строка 310** - После успешного создания задач:
```python
print(f"✓ Created join tasks for {len(chat_ids)} chat(s)")
print(f"✓ Добавлено {tasks_added} задач в очередь выполнения")

# ДОБАВИТЬ:
await ActivityLogger.log(
    component="IngestionModule",
    level="INFO",
    message="Join tasks created and enqueued successfully",
    metadata={
        "chats_processed": len(chat_ids),
        "tasks_added_to_queue": tasks_added,
        "distribution": {str(k): len(v) for k, v in distribution.items()}
    }
)
```

**Строка 314** - При ошибке создания задач:
```python
except ValueError as e:
    print(f"⚠ Cannot create join tasks: {e}")
    # ДОБАВИТЬ:
    await ActivityLogger.log(
        component="IngestionModule",
        level="WARNING",
        message="Cannot create join tasks",
        metadata={
            "error": str(e),
            "pending_chats_count": len(chat_ids)
        }
    )
```

**Строка 318** - При общей ошибке:
```python
except Exception as e:
    print(f"Error in pending chats processor: {e}")
    # ДОБАВИТЬ:
    await ActivityLogger.log_error(
        component="IngestionModule",
        error_message="Error in pending chats processor",
        exception=e
    )
```

### 3. _load_userbot_sessions() - Загрузка userbot сессий

**Строка 135** - Успешная загрузка:
```python
print(f"    ✓ Loaded {session_name} (ID: {userbot_id})")

# ДОБАВИТЬ:
await ActivityLogger.log(
    component="UserbotPoolManager",
    level="INFO",
    message="Userbot session loaded successfully",
    metadata={
        "session_name": session_name,
        "userbot_id": userbot_id
    }
)
```

**Строка 137** - Ошибка загрузки:
```python
except Exception as e:
    print(f"    ✗ Failed to load {session_file.name}: {e}")
    # ДОБАВИТЬ:
    await ActivityLogger.log_error(
        component="UserbotPoolManager",
        error_message=f"Failed to load userbot session: {session_file.name}",
        exception=e
    )
```

## Важные места (РЕКОМЕНДУЕТСЯ)

### 4. run() - Старт и стоп системы

**Строка 81** - Система готова:
```python
print("System is ready!")

# ДОБАВИТЬ:
await ActivityLogger.log(
    component="SystemManager",
    level="INFO",
    message="System startup complete - ready to process tasks"
)
```

**Строка 87** - Начало shutdown:
```python
print("\nShutting down gracefully...")

# ДОБАВИТЬ:
await ActivityLogger.log(
    component="SystemManager",
    level="INFO",
    message="Graceful shutdown initiated"
)
```

**Строка 100** - Таймаут shutdown:
```python
print("⚠ Timeout reached, forcing shutdown...")

# ДОБАВИТЬ:
await ActivityLogger.log(
    component="SystemManager",
    level="WARNING",
    message="Shutdown timeout reached - forcing task cancellation",
    metadata={"active_tasks": len([t for t in self._tasks if not t.done()])}
)
```

**Строка 106** - Завершение shutdown:
```python
print("✓ Shutdown complete")

# ДОБАВИТЬ:
await ActivityLogger.log(
    component="SystemManager",
    level="INFO",
    message="System shutdown complete"
)
```

### 5. _initialize_components() - Загрузка данных

**Строка 218** - Очистка старых задач:
```python
if cleaned_tasks > 0:
    print(f"  - Marked {cleaned_tasks} old pending tasks as failed")
    # ДОБАВИТЬ:
    await ActivityLogger.log(
        component="JoinQueue",
        level="INFO",
        message="Cleaned up old pending tasks",
        metadata={"tasks_marked_failed": cleaned_tasks}
    )
```

**Строка 223** - Загрузка pending задач:
```python
if loaded_tasks > 0:
    print(f"  - Loaded {loaded_tasks} pending join tasks")
    # ДОБАВИТЬ:
    await ActivityLogger.log(
        component="JoinQueue",
        level="INFO",
        message="Loaded pending join tasks from database",
        metadata={"tasks_loaded": loaded_tasks}
    )
```

## Полезные места (ОПЦИОНАЛЬНО)

### 6. _load_userbot_sessions() - Предупреждения

**Строка 119** - Нет директории sessions:
```python
print("  ⚠ sessions/ directory not found, creating it...")

# ДОБАВИТЬ:
await ActivityLogger.log(
    component="UserbotPoolManager",
    level="WARNING",
    message="Sessions directory not found - created empty directory"
)
```

**Строка 126** - Нет .session файлов:
```python
print("  ⚠ No .session files found in sessions/ directory")

# ДОБАВИТЬ:
await ActivityLogger.log(
    component="UserbotPoolManager",
    level="WARNING",
    message="No userbot session files found in sessions/ directory"
)
```

### 7. run() - Инициализация

**Строка 67** - База данных инициализирована:
```python
print("✓ Database initialized")

# ДОБАВИТЬ:
await ActivityLogger.log(
    component="SystemManager",
    level="INFO",
    message="Database initialized successfully"
)
```

**Строка 77** - Компоненты инициализированы:
```python
print("✓ All components initialized")

# ДОБАВИТЬ:
await ActivityLogger.log(
    component="SystemManager",
    level="INFO",
    message="All components initialized successfully",
    metadata={
        "components": ["UserbotPool", "JoinQueue", "LLMVerifier", "DeliveryBot", "MessageParser", "IngestionModule"]
    }
)
```

## Приоритеты реализации

### Фаза 1 (КРИТИЧНО - сделать сейчас)
1. ✅ Логирование выполнения join задач (_process_join_queue)
2. ✅ Логирование создания join задач (_process_pending_chats)
3. ✅ Логирование ошибок во всех exception блоках

### Фаза 2 (ВАЖНО - сделать следующим)
4. ✅ Логирование загрузки userbot сессий
5. ✅ Логирование старта/стопа системы
6. ✅ Логирование загрузки pending задач

### Фаза 3 (ПОЛЕЗНО - сделать если есть время)
7. ✅ Логирование инициализации компонентов
8. ✅ Логирование предупреждений (нет сессий и т.д.)

## Проверка после добавления

После добавления логирования проверить:

1. **Запустить систему** и проверить что логи записываются:
```sql
SELECT * FROM activity_logs ORDER BY created_at DESC LIMIT 20;
```

2. **Создать задачу присоединения** и проверить логи выполнения:
```sql
SELECT * FROM activity_logs WHERE component = 'JoinQueue' ORDER BY created_at DESC;
```

3. **Проверить логи ошибок**:
```sql
SELECT * FROM activity_logs WHERE level = 'ERROR' ORDER BY created_at DESC;
```

4. **Проверить логи всех компонентов**:
```sql
SELECT component, COUNT(*) as log_count 
FROM activity_logs 
GROUP BY component 
ORDER BY log_count DESC;
```
