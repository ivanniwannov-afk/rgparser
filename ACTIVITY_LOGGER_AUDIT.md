# Аудит вызовов ActivityLogger в main.py

## Дата аудита
${new Date().toISOString()}

## Обзор
Этот документ содержит полный аудит всех мест в `main.py` где должен вызываться `ActivityLogger` для записи событий в таблицу `activity_logs`.

## Текущее состояние

### Существующие вызовы ActivityLogger

1. **Строка 189**: `await ActivityLogger.log_lead_delivery()` - в callback `on_qualified_lead()`
   - ✅ **ПРАВИЛЬНО**: Логирует доставку лида оператору
   - Компонент: DeliveryBot
   - Уровень: INFO
   - Метаданные: sender_id, chat_title, message_preview

## Отсутствующие вызовы ActivityLogger

### 1. Инициализация системы (метод `run()`)

**Строка 67**: После инициализации базы данных
```python
print("✓ Database initialized")
```
**РЕКОМЕНДАЦИЯ**: Добавить логирование
```python
await ActivityLogger.log(
    component="SystemManager",
    level="INFO",
    message="Database initialized successfully"
)
```

**Строка 77**: После инициализации компонентов
```python
print("✓ All components initialized")
```
**РЕКОМЕНДАЦИЯ**: Добавить логирование
```python
await ActivityLogger.log(
    component="SystemManager",
    level="INFO",
    message="All components initialized successfully",
    metadata={
        "components": ["UserbotPool", "JoinQueue", "LLMVerifier", "DeliveryBot", "MessageParser", "IngestionModule"]
    }
)
```

**Строка 81**: Система готова
```python
print("System is ready!")
```
**РЕКОМЕНДАЦИЯ**: Добавить логирование
```python
await ActivityLogger.log(
    component="SystemManager",
    level="INFO",
    message="System startup complete - ready to process tasks"
)
```

### 2. Завершение работы системы (метод `run()`)

**Строка 87**: Начало graceful shutdown
```python
print("\nShutting down gracefully...")
```
**РЕКОМЕНДАЦИЯ**: Добавить логирование
```python
await ActivityLogger.log(
    component="SystemManager",
    level="INFO",
    message="Graceful shutdown initiated"
)
```

**Строка 100**: Таймаут при завершении задач
```python
print("⚠ Timeout reached, forcing shutdown...")
```
**РЕКОМЕНДАЦИЯ**: Добавить логирование
```python
await ActivityLogger.log(
    component="SystemManager",
    level="WARNING",
    message="Shutdown timeout reached - forcing task cancellation",
    metadata={"active_tasks": len([t for t in self._tasks if not t.done()])}
)
```

**Строка 106**: Завершение работы
```python
print("✓ Shutdown complete")
```
**РЕКОМЕНДАЦИЯ**: Добавить логирование
```python
await ActivityLogger.log(
    component="SystemManager",
    level="INFO",
    message="System shutdown complete"
)
```

### 3. Загрузка userbot сессий (метод `_load_userbot_sessions()`)

**Строка 119**: Директория sessions не найдена
```python
print("  ⚠ sessions/ directory not found, creating it...")
```
**РЕКОМЕНДАЦИЯ**: Добавить логирование
```python
await ActivityLogger.log(
    component="UserbotPoolManager",
    level="WARNING",
    message="Sessions directory not found - created empty directory"
)
```

**Строка 126**: Нет .session файлов
```python
print("  ⚠ No .session files found in sessions/ directory")
```
**РЕКОМЕНДАЦИЯ**: Добавить логирование
```python
await ActivityLogger.log(
    component="UserbotPoolManager",
    level="WARNING",
    message="No userbot session files found in sessions/ directory"
)
```

**Строка 135**: Успешная загрузка userbot
```python
print(f"    ✓ Loaded {session_name} (ID: {userbot_id})")
```
**РЕКОМЕНДАЦИЯ**: Добавить логирование
```python
await ActivityLogger.log(
    component="UserbotPoolManager",
    level="INFO",
    message=f"Userbot session loaded successfully",
    metadata={
        "session_name": session_name,
        "userbot_id": userbot_id
    }
)
```

**Строка 137**: Ошибка загрузки userbot
```python
print(f"    ✗ Failed to load {session_file.name}: {e}")
```
**РЕКОМЕНДАЦИЯ**: Добавить логирование
```python
await ActivityLogger.log_error(
    component="UserbotPoolManager",
    error_message=f"Failed to load userbot session: {session_file.name}",
    exception=e
)
```

### 4. Инициализация компонентов (метод `_initialize_components()`)

**Строка 218**: Очистка старых pending задач
```python
if cleaned_tasks > 0:
    print(f"  - Marked {cleaned_tasks} old pending tasks as failed")
```
**РЕКОМЕНДАЦИЯ**: Добавить логирование
```python
await ActivityLogger.log(
    component="JoinQueue",
    level="INFO",
    message=f"Cleaned up old pending tasks",
    metadata={"tasks_marked_failed": cleaned_tasks}
)
```

**Строка 223**: Загрузка pending задач
```python
if loaded_tasks > 0:
    print(f"  - Loaded {loaded_tasks} pending join tasks")
```
**РЕКОМЕНДАЦИЯ**: Добавить логирование
```python
await ActivityLogger.log(
    component="JoinQueue",
    level="INFO",
    message=f"Loaded pending join tasks from database",
    metadata={"tasks_loaded": loaded_tasks}
)
```

### 5. Обработка очереди присоединений (метод `_process_join_queue()`)

**Строка 253**: Начало обработки задачи
```python
# Mark as processing
await self.join_queue.mark_task_processing(task.task_id)
```
**РЕКОМЕНДАЦИЯ**: Добавить логирование ПЕРЕД mark_task_processing
```python
await ActivityLogger.log(
    component="JoinQueue",
    level="INFO",
    message=f"Starting join task execution",
    metadata={
        "task_id": task.task_id,
        "userbot_id": task.userbot_id,
        "chat_id": task.chat_id,
        "scheduled_at": task.scheduled_at.isoformat()
    }
)
```

**Строка 259**: Успешное выполнение задачи
```python
if success:
    await self.join_queue.mark_task_completed(task.task_id)
```
**РЕКОМЕНДАЦИЯ**: Добавить логирование
```python
await ActivityLogger.log(
    component="JoinQueue",
    level="INFO",
    message=f"Join task completed successfully",
    metadata={
        "task_id": task.task_id,
        "userbot_id": task.userbot_id,
        "chat_id": task.chat_id
    }
)
```

**Строка 261**: Неудачное выполнение задачи
```python
else:
    await self.join_queue.mark_task_failed(task.task_id)
```
**РЕКОМЕНДАЦИЯ**: Добавить логирование
```python
await ActivityLogger.log(
    component="JoinQueue",
    level="WARNING",
    message=f"Join task failed",
    metadata={
        "task_id": task.task_id,
        "userbot_id": task.userbot_id,
        "chat_id": task.chat_id
    }
)
```

**Строка 264**: Ошибка при обработке задачи
```python
except Exception as e:
    print(f"Error processing join task {task.task_id}: {e}")
    await self.join_queue.mark_task_failed(task.task_id)
```
**РЕКОМЕНДАЦИЯ**: Добавить логирование
```python
await ActivityLogger.log_error(
    component="JoinQueue",
    error_message=f"Exception while processing join task {task.task_id}",
    exception=e
)
```

### 6. Обработка pending чатов (метод `_process_pending_chats()`)

**Строка 283**: Найдены pending чаты
```python
print(f"Found {len(chat_ids)} pending chat(s), creating join tasks...")
```
**РЕКОМЕНДАЦИЯ**: Добавить логирование
```python
await ActivityLogger.log(
    component="IngestionModule",
    level="INFO",
    message=f"Found pending chats - creating join tasks",
    metadata={
        "pending_chats_count": len(chat_ids),
        "chat_ids": chat_ids
    }
)
```

**Строка 310**: Успешное создание задач
```python
print(f"✓ Created join tasks for {len(chat_ids)} chat(s)")
print(f"✓ Добавлено {tasks_added} задач в очередь выполнения")
```
**РЕКОМЕНДАЦИЯ**: Добавить логирование
```python
await ActivityLogger.log(
    component="IngestionModule",
    level="INFO",
    message=f"Join tasks created and enqueued successfully",
    metadata={
        "chats_processed": len(chat_ids),
        "tasks_added_to_queue": tasks_added,
        "distribution": {str(k): len(v) for k, v in distribution.items()}
    }
)
```

**Строка 314**: Ошибка создания задач (ValueError)
```python
except ValueError as e:
    print(f"⚠ Cannot create join tasks: {e}")
```
**РЕКОМЕНДАЦИЯ**: Добавить логирование
```python
await ActivityLogger.log(
    component="IngestionModule",
    level="WARNING",
    message=f"Cannot create join tasks",
    metadata={
        "error": str(e),
        "pending_chats_count": len(chat_ids)
    }
)
```

**Строка 318**: Общая ошибка в процессоре pending чатов
```python
except Exception as e:
    print(f"Error in pending chats processor: {e}")
```
**РЕКОМЕНДАЦИЯ**: Добавить логирование
```python
await ActivityLogger.log_error(
    component="IngestionModule",
    error_message="Error in pending chats processor",
    exception=e
)
```

### 7. Main функция

**Строка 330**: Фатальная ошибка
```python
except Exception as e:
    print(f"Fatal error: {e}")
    sys.exit(1)
```
**РЕКОМЕНДАЦИЯ**: Добавить логирование (но нужно быть осторожным с async в этом контексте)
```python
# Это сложно, так как мы вне async контекста
# Можно попробовать:
try:
    asyncio.run(ActivityLogger.log_error(
        component="SystemManager",
        error_message="Fatal system error",
        exception=e
    ))
except:
    pass  # Если логирование не удалось, просто выходим
```

## Критические места требующие логирования

### Высокий приоритет (КРИТИЧНО)
1. ✅ **Выполнение join задач** (_process_join_queue) - успех/неудача/ошибки
2. ✅ **Создание join задач** (_process_pending_chats) - создание и добавление в очередь
3. ✅ **Загрузка userbot сессий** (_load_userbot_sessions) - успех/неудача загрузки
4. ✅ **Ошибки обработки** - все exception блоки

### Средний приоритет (ВАЖНО)
5. ✅ **Старт/стоп системы** (run) - инициализация и завершение
6. ✅ **Очистка старых задач** (_initialize_components) - количество очищенных задач
7. ✅ **Загрузка pending задач** (_initialize_components) - количество загруженных задач

### Низкий приоритет (ПОЛЕЗНО)
8. ✅ **Инициализация компонентов** - успешная инициализация каждого компонента

## Рекомендации по реализации

### Порядок добавления логирования

1. **Фаза 1**: Добавить логирование в критические места (выполнение задач, ошибки)
2. **Фаза 2**: Добавить логирование в важные места (старт/стоп, загрузка данных)
3. **Фаза 3**: Добавить логирование в полезные места (инициализация компонентов)

### Принципы логирования

- **INFO**: Нормальные операции (старт, стоп, успешное выполнение задач)
- **WARNING**: Проблемы которые не критичны (нет userbot сессий, не удалось создать задачи)
- **ERROR**: Критические ошибки (исключения, неудачи выполнения)

### Метаданные

Всегда включать релевантные метаданные:
- ID задач, userbot, чатов
- Количество обработанных элементов
- Временные метки
- Детали ошибок (тип исключения, сообщение)

## Итоговая статистика

- **Всего мест требующих логирования**: 18
- **Существующих вызовов**: 1
- **Отсутствующих вызовов**: 17
- **Критических мест**: 4
- **Важных мест**: 3
- **Полезных мест**: 11

## Следующие шаги

1. Реализовать логирование в критических местах (задача 2.2, 2.3)
2. Проверить что логи записываются в базу данных (задача 2.4)
3. Добавить обработку ошибок при записи логов (задача 2.5)
4. Протестировать что все логи корректно записываются
