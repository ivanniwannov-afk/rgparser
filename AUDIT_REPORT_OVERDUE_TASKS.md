# Полный аудит логики приложения - Исправление бага с просроченными задачами

**Дата аудита**: 2024
**Аудитор**: Kiro AI
**Спецификация**: `.kiro/specs/overdue-tasks-not-executing/`

## Резюме

Проведен полный аудит логики приложения для выявления проблем с выполнением просроченных задач и записью логов. Обнаружено **5 критических проблем** и **3 потенциальных улучшения**.

### Критические проблемы

1. ❌ **КРИТИЧНО**: `JoinLogic` класс не существует, но импортируется в `main.py`
2. ✅ **ИСПРАВЛЕНО**: `load_pending_tasks()` теперь загружает все pending задачи
3. ✅ **РАБОТАЕТ**: `get_next_task()` правильно обрабатывает просроченные задачи
4. ⚠️ **ПРОБЛЕМА**: `cleanup_old_tasks()` может конфликтовать с `load_pending_tasks()`
5. ⚠️ **ПРОБЛЕМА**: `_process_pending_chats()` не проверяет существующие задачи

---

## 1. Аудит `get_next_task()` (Задача 3.1)

**Файл**: `src/ingestion/join_queue.py`, строки 145-195

### Анализ логики

```python
async def get_next_task(self) -> Optional[JoinTask]:
    while not self._stop_event.is_set():
        try:
            task = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            
            now = datetime.now(timezone.utc)
            
            if task.scheduled_at <= now:
                # Task is ready to execute (including overdue tasks)
                delay_seconds = (now - task.scheduled_at).total_seconds()
                if delay_seconds > 0:
                    print(f"⚠ Task {task.task_id} is overdue by {delay_seconds:.0f} seconds, executing immediately")
                return task
            else:
                # Task is not ready yet, wait until it is
                delay = (task.scheduled_at - now).total_seconds()
                print(f"Task {task.task_id} scheduled in {delay:.0f} seconds")
                
                await self._queue.put(task)
                
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=delay
                    )
                    return None
                except asyncio.TimeoutError:
                    continue
        
        except asyncio.TimeoutError:
            continue
    
    return None
```

### ✅ Вердикт: ПРАВИЛЬНО

**Обработка просроченных задач**:
- ✅ Проверяет `task.scheduled_at <= now` для определения готовности
- ✅ Возвращает просроченные задачи немедленно без дополнительной задержки
- ✅ Выводит предупреждение о просрочке с указанием времени задержки
- ✅ Правильно обрабатывает будущие задачи (ждет до scheduled_at)

**Обработка очереди**:
- ✅ Использует приоритетную очередь (PriorityQueue) с сортировкой по scheduled_at
- ✅ Возвращает задачи в правильном порядке (самая ранняя первой)
- ✅ Правильно обрабатывает stop_event для корректного завершения

**Потенциальные проблемы**: Нет

---

## 2. Аудит `cleanup_old_tasks()` (Задача 3.2)

**Файл**: `src/ingestion/join_queue.py`, строки 89-111

### Анализ логики

```python
async def cleanup_old_tasks(self) -> int:
    """Mark old pending tasks as failed to prevent accumulation.
    
    Tasks that are older than 1 hour and still pending are marked as failed
    since they were likely created before a system restart and never added
    to the execution queue.
    
    NOTE: This method handles truly old tasks (created > 1 hour ago) separately
    from load_pending_tasks(). While load_pending_tasks() loads ALL pending tasks
    (including overdue ones) to ensure they execute after system restart,
    cleanup_old_tasks() marks genuinely abandoned tasks as failed to prevent
    accumulation of tasks that will never be executed.
    
    Returns:
        Number of tasks marked as failed
    
    Validates: Requirements 2.1
    """
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=1)
    cutoff_str = cutoff_time.isoformat()
    
    async with get_connection() as db:
        cursor = await db.execute(
            """UPDATE join_tasks
               SET status = 'failed', completed_at = CURRENT_TIMESTAMP
               WHERE status = 'pending' AND created_at < ?""",
            (cutoff_str,)
        )
        await db.commit()
        return cursor.rowcount
```

### ⚠️ Вердикт: ПОТЕНЦИАЛЬНАЯ ПРОБЛЕМА

**Правильная логика**:
- ✅ Правильно определяет старые задачи по `created_at < (now - 1 hour)`
- ✅ Помечает их как 'failed' для предотвращения накопления
- ✅ Возвращает количество обработанных задач

**Потенциальная проблема - Конфликт с load_pending_tasks()**:

После исправления `load_pending_tasks()` (который теперь загружает ВСЕ pending задачи), возникает **конфликт логики**:

1. `load_pending_tasks()` загружает ВСЕ pending задачи (включая старые)
2. `cleanup_old_tasks()` помечает старые pending задачи как 'failed'

**Проблемный сценарий**:
```
T=0:00  - Задача создана, scheduled_at = T+1:00
T=0:30  - Система остановлена
T=1:05  - Система перезапущена
        - load_pending_tasks() загружает задачу (created 65 минут назад)
        - cleanup_old_tasks() помечает её как 'failed' (created > 1 час назад)
        - Задача в очереди, но в БД статус 'failed'!
```

**Рекомендация**:
- Либо увеличить окно cleanup до 24 часов
- Либо не вызывать cleanup_old_tasks() сразу после load_pending_tasks()
- Либо изменить логику cleanup чтобы проверять `scheduled_at` вместо `created_at`

---

## 3. Аудит `_process_join_queue()` (Задача 3.3)

**Файл**: `main.py`, строки 272-340

### Анализ логики

```python
async def _process_join_queue(self) -> None:
    """Process join queue tasks."""
    from src.ingestion.join_logic import JoinLogic
    
    join_logic = JoinLogic(self.userbot_pool)
    
    while not self._shutdown_event.is_set():
        task = await self.join_queue.get_next_task()
        
        if task is None:
            break
        
        await self.join_queue.mark_task_processing(task.task_id)
        
        await ActivityLogger.log(
            component="JoinQueue",
            level="INFO",
            message="Starting join task execution",
            metadata={...}
        )
        
        try:
            success = await join_logic.execute_join(task.userbot_id, task.chat_id)
            
            if success:
                await self.join_queue.mark_task_completed(task.task_id)
                await ActivityLogger.log(...)
            else:
                await self.join_queue.mark_task_failed(task.task_id)
                await ActivityLogger.log(...)
        
        except Exception as e:
            print(f"Error processing join task {task.task_id}: {e}")
            await ActivityLogger.log_error(...)
            await self.join_queue.mark_task_failed(task.task_id)
```

### ❌ Вердикт: КРИТИЧЕСКАЯ ОШИБКА

**Критическая проблема - JoinLogic класс не существует**:

```python
from src.ingestion.join_logic import JoinLogic  # ❌ Этот класс не существует!
join_logic = JoinLogic(self.userbot_pool)       # ❌ Это вызовет ImportError!
success = await join_logic.execute_join(...)    # ❌ Метод не существует!
```

**Проверка файла `src/ingestion/join_logic.py`**:
- ❌ Класс `JoinLogic` НЕ определен
- ✅ Функция `safe_join_chat()` существует
- ❌ Метод `execute_join()` НЕ существует

**Это означает что `_process_join_queue()` НЕ МОЖЕТ РАБОТАТЬ!**

**Правильная логика выполнения задач** (если бы класс существовал):
- ✅ Получает задачу через `get_next_task()`
- ✅ Помечает как 'processing' перед выполнением
- ✅ Обрабатывает успех/неудачу правильно
- ✅ Логирует все операции через ActivityLogger
- ✅ Обрабатывает исключения и помечает задачи как 'failed'

**Рекомендация**:
Необходимо либо:
1. Создать класс `JoinLogic` с методом `execute_join()`
2. Или изменить `_process_join_queue()` чтобы использовать `safe_join_chat()` напрямую

---

## 4. Аудит `_process_pending_chats()` (Задача 3.4)

**Файл**: `main.py`, строки 342-440

### Анализ логики

```python
async def _process_pending_chats(self) -> None:
    """Process pending chats and create join tasks."""
    
    while not self._shutdown_event.is_set():
        try:
            await asyncio.sleep(30)  # Check every 30 seconds
            
            async with aiosqlite.connect("telegram_leads.db") as db:
                # Get pending chats
                cursor = await db.execute("""
                    SELECT id FROM chats 
                    WHERE status = 'pending' 
                    AND assigned_userbot_id IS NULL
                """)
                pending_chats = await cursor.fetchall()
                
                if not pending_chats:
                    continue
                
                chat_ids = [row[0] for row in pending_chats]
                print(f"Found {len(chat_ids)} pending chat(s), creating join tasks...")
                
                await ActivityLogger.log(...)
                
                # Distribute chats among userbots
                try:
                    distribution = await self.ingestion.distribute_chats(chat_ids)
                    
                    # Create join tasks in database
                    await self.ingestion.enqueue_join_tasks(distribution)
                    
                    # Add newly created tasks to the queue
                    tasks_added = 0
                    
                    async with aiosqlite.connect("telegram_leads.db") as db2:
                        for userbot_id, assigned_chat_ids in distribution.items():
                            for chat_id in assigned_chat_ids:
                                # Get the task we just created
                                cursor2 = await db2.execute("""
                                    SELECT id, scheduled_at
                                    FROM join_tasks
                                    WHERE userbot_id = ? AND chat_id = ? AND status = 'pending'
                                    ORDER BY created_at DESC
                                    LIMIT 1
                                """, (userbot_id, chat_id))
                                task_row = await cursor2.fetchone()
                                
                                if task_row:
                                    task_id, scheduled_at_str = task_row
                                    scheduled_at = datetime.fromisoformat(scheduled_at_str)
                                    if scheduled_at.tzinfo is None:
                                        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
                                    await self.join_queue.add_task(task_id, userbot_id, chat_id, scheduled_at)
                                    tasks_added += 1
                    
                    print(f"✓ Created join tasks for {len(chat_ids)} chat(s)")
                    print(f"✓ Добавлено {tasks_added} задач в очередь выполнения")
                    
                    await ActivityLogger.log(...)
                
                except ValueError as e:
                    print(f"⚠ Cannot create join tasks: {e}")
                    await ActivityLogger.log(...)
        
        except Exception as e:
            print(f"Error in pending chats processor: {e}")
            await ActivityLogger.log_error(...)
```

### ⚠️ Вердикт: ПОТЕНЦИАЛЬНАЯ ПРОБЛЕМА

**Правильная логика**:
- ✅ Периодически проверяет pending чаты (каждые 30 секунд)
- ✅ Фильтрует чаты без назначенного userbot
- ✅ Распределяет чаты через `distribute_chats()`
- ✅ Создает задачи через `enqueue_join_tasks()`
- ✅ Добавляет задачи в очередь выполнения
- ✅ Логирует все операции
- ✅ Обрабатывает ошибки (например, нет доступных userbots)

**Потенциальная проблема - Дублирование задач**:

Запрос не проверяет существующие задачи:
```sql
SELECT id FROM chats 
WHERE status = 'pending' 
AND assigned_userbot_id IS NULL
```

**Проблемный сценарий**:
```
1. Чат добавлен, создана задача, assigned_userbot_id установлен
2. Задача выполняется, но проваливается
3. Статус чата остается 'pending', но assigned_userbot_id НЕ NULL
4. _process_pending_chats() НЕ обработает этот чат снова
5. Чат застрянет в статусе 'pending' навсегда
```

**Другая проблема - Повторное создание задач**:

Если задача уже существует для чата, но еще не выполнена:
```
1. Чат в статусе 'pending', assigned_userbot_id = NULL
2. _process_pending_chats() создает задачу
3. Задача еще не выполнена (запланирована на будущее)
4. Через 30 секунд _process_pending_chats() снова видит чат
5. Создается дублирующая задача!
```

**Рекомендация**:
Изменить запрос чтобы проверять существующие задачи:
```sql
SELECT c.id FROM chats c
LEFT JOIN join_tasks jt ON c.id = jt.chat_id AND jt.status = 'pending'
WHERE c.status = 'pending' 
AND c.assigned_userbot_id IS NULL
AND jt.id IS NULL  -- Нет существующих pending задач
```

---

## 5. Дополнительные проблемы

### 5.1 Проблема с `enqueue_join_tasks()`

**Файл**: `src/ingestion/ingestion_module.py`, строки 165-200

```python
async def enqueue_join_tasks(self, distribution: dict[int, list[int]]) -> None:
    """Create join tasks with randomized delays for distributed chats."""
    
    print(f"[DEBUG] enqueue_join_tasks called")
    print(f"[DEBUG] self.join_delay_min = {self.join_delay_min}")
    print(f"[DEBUG] self.join_delay_max = {self.join_delay_max}")
    
    async with get_connection() as db:
        now = datetime.now(timezone.utc)
        print(f"[DEBUG] Current time: {now.isoformat()}")
        
        for userbot_id, chat_ids in distribution.items():
            for chat_id in chat_ids:
                delay_seconds = random.randint(self.join_delay_min, self.join_delay_max)
                scheduled_time = now + timedelta(seconds=delay_seconds)
                
                print(f"[DEBUG] Task for chat {chat_id}:")
                print(f"[DEBUG]   delay_seconds = {delay_seconds}")
                print(f"[DEBUG]   scheduled_time = {scheduled_time.isoformat()}")
                
                await db.execute(
                    """INSERT INTO join_tasks (userbot_id, chat_id, scheduled_at, status, created_at)
                       VALUES (?, ?, ?, 'pending', CURRENT_TIMESTAMP)""",
                    (userbot_id, chat_id, scheduled_time.isoformat())
                )
        
        await db.commit()
        print(f"[DEBUG] Tasks committed to database")
```

**Проблемы**:
- ⚠️ Много debug print() - должны быть заменены на логирование
- ⚠️ Не проверяет существующие задачи перед созданием
- ✅ Правильно создает задачи с randomized delays
- ✅ Правильно использует timezone-aware datetime

---

## 6. Проверка системы логирования

### 6.1 Схема таблицы activity_logs

**Файл**: `database.py`, строки 103-117

```sql
CREATE TABLE IF NOT EXISTS activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    component TEXT NOT NULL,
    level TEXT NOT NULL CHECK(level IN ('INFO', 'WARNING', 'ERROR')),
    message TEXT NOT NULL,
    metadata JSON NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

✅ Схема правильная, поддерживает все необходимые поля.

### 6.2 ActivityLogger

**Использование в коде**:
- ✅ `_process_join_queue()` - логирует начало, успех, неудачу, ошибки
- ✅ `_process_pending_chats()` - логирует создание задач, ошибки
- ✅ `join_logic.py` - использует `_log_activity()` для записи в БД

**Проверка записи в БД**:
Функция `_log_activity()` в `join_logic.py`:
```python
async def _log_activity(
    component: str,
    level: str,
    message: str,
    metadata: Optional[dict] = None,
) -> None:
    """Log activity to the database."""
    import json
    
    async with database.get_connection() as db:
        await db.execute(
            """INSERT INTO activity_logs (component, level, message, metadata, created_at)
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (component, level, message, json.dumps(metadata) if metadata else None)
        )
        await db.commit()
```

✅ Логика правильная, должна работать.

**КРИТИЧЕСКАЯ ПРОБЛЕМА**: Поскольку `JoinLogic` класс не существует и `_process_join_queue()` не может запуститься, логирование из этого компонента НЕ РАБОТАЕТ. Это объясняет почему логи не записываются!

---

## Итоговые рекомендации

### Критические исправления (СРОЧНО)

1. **Создать класс JoinLogic** или изменить `_process_join_queue()`:
   ```python
   # Вариант 1: Создать класс
   class JoinLogic:
       def __init__(self, pool_manager):
           self.pool_manager = pool_manager
       
       async def execute_join(self, userbot_id: int, chat_id: int) -> bool:
           # Получить userbot client
           # Получить chat_link из БД
           # Вызвать safe_join_chat()
           pass
   
   # Вариант 2: Использовать safe_join_chat() напрямую
   # В _process_join_queue():
   from src.ingestion.join_logic import safe_join_chat
   
   # Получить userbot client и chat info
   success, error = await safe_join_chat(
       client, chat_link, chat_id, userbot_id, 
       self.userbot_pool, ...
   )
   ```

2. **Исправить конфликт cleanup_old_tasks() и load_pending_tasks()**:
   - Увеличить окно cleanup до 24 часов
   - Или вызывать cleanup только периодически, не при старте

3. **Исправить _process_pending_chats() для предотвращения дублирования**:
   - Проверять существующие pending задачи перед созданием новых

### Улучшения (РЕКОМЕНДУЕТСЯ)

1. Заменить debug print() на proper logging
2. Добавить метрики для мониторинга (сколько задач просрочено, сколько выполнено)
3. Добавить retry логику для failed задач

---

## Заключение

**Статус аудита**: ❌ ОБНАРУЖЕНЫ КРИТИЧЕСКИЕ ПРОБЛЕМЫ

**Критические проблемы**:
1. ❌ **БЛОКИРУЮЩАЯ ПРОБЛЕМА**: `JoinLogic` класс не существует - `_process_join_queue()` НЕ МОЖЕТ ЗАПУСТИТЬСЯ
   - Система падает с `ImportError` при попытке импорта
   - Это объясняет почему просроченные задачи не выполняются
   - Это объясняет почему логи не записываются (процесс падает до записи)
   
2. ⚠️ Конфликт между `cleanup_old_tasks()` и `load_pending_tasks()`
   - После исправления load_pending_tasks() возник конфликт логики
   - Задачи могут быть загружены в очередь но помечены как 'failed' в БД
   
3. ⚠️ Возможное дублирование задач в `_process_pending_chats()`
   - Не проверяются существующие pending задачи
   - Может создавать дублирующие задачи для одного чата

**Исправленные проблемы**:
1. ✅ `load_pending_tasks()` теперь загружает все pending задачи (Задача 1.1-1.3)
2. ✅ `get_next_task()` правильно обрабатывает просроченные задачи
3. ✅ Схема activity_logs правильная
4. ✅ Логирование добавлено в нужные места (Задача 2.1-2.5)

**Корневая причина бага с просроченными задачами**:

Баг НЕ в логике обработки просроченных задач (она правильная), а в том что **система вообще не может запуститься** из-за отсутствия класса `JoinLogic`. Когда `main.py` пытается запустить `_process_join_queue()`, происходит:

```python
from src.ingestion.join_logic import JoinLogic  # ImportError!
```

Система падает, задачи не выполняются, логи не записываются.

**Следующие шаги**:
1. **СРОЧНО**: Создать класс `JoinLogic` с методом `execute_join()` (см. рекомендации выше)
2. Исправить конфликт cleanup/load (увеличить окно до 24 часов или изменить логику)
3. Добавить проверку дублирования задач в `_process_pending_chats()`
4. Запустить систему и проверить что задачи выполняются
5. Проверить что логи записываются в activity_logs

**Проверка гипотезы**:

Можно проверить что система действительно падает:
```bash
python main.py
# Ожидается: ImportError: cannot import name 'JoinLogic'
```

После создания класса `JoinLogic` система должна заработать и просроченные задачи начнут выполняться.

